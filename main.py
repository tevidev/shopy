#!/usr/bin/env python3
"""
Enhanced Shopify Card Checker Telegram Bot - Final Version
Developer: @Awmtee
Features: Beautiful UI, Live Updates, Advanced Gateway Detection, Mass Checking
"""

import asyncio
import json
import logging
import os
import random
import re
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import urllib3
from colorama import Fore, Style, init
from fake_useragent import UserAgent
from faker import Faker
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update,
    Bot
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# Import our enhanced checker
from shopify_checker import ShopifyGatewayChecker 

# Initialize colorama and disable SSL warnings
init(autoreset=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global variables
user_sessions = {}
checking_sessions = {}
bot_stats = {
    'total_checks': 0,
    'live_cards': 0,
    'dead_cards': 0,
    'users': set(),
    'start_time': datetime.now()
}

# Thread locks
print_lock = threading.Lock()
session_lock = threading.Lock()
stats_lock = threading.Lock()

class Colors:
    """Color constants for beautiful output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class EnhancedTelegramBot:
    """Enhanced Telegram bot with beautiful UI and advanced features"""
    
    def __init__(self):
        self.checker = ShopifyGatewayChecker()
        self.application = None
        
        # Create results directory
        if not os.path.exists(RESULTS_DIR):
            os.makedirs(RESULTS_DIR)
        
    def update_stats(self, result_type: str, user_id: int):
        """Update bot statistics"""
        with stats_lock:
            bot_stats['total_checks'] += 1
            bot_stats['users'].add(user_id)
            
            if result_type in ['CHARGED', 'AVS', 'CVV', 'INSUFFICIENT']:
                bot_stats['live_cards'] += 1
            else:
                bot_stats['dead_cards'] += 1

    def save_result(self, card: str, result_type: str, message: str):
        """Save result to appropriate file"""
        if not ENABLE_AUTO_SAVE:
            return
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_line = f"{timestamp} | {card} | {result_type} | {message}\n"
        
        filename_map = {
            'CHARGED': 'live.txt',
            'AVS': 'live.txt',
            'CVV': 'cvv.txt',
            'INSUFFICIENT': 'insufficient.txt'
        }
        
        filename = filename_map.get(result_type, 'dead.txt')
        filepath = os.path.join(RESULTS_DIR, filename)
        
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(result_line)
        except Exception as e:
            logger.error(f"Failed to save result: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced start command with beautiful welcome message"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "User"
        first_name = update.effective_user.first_name or "User"
        
        # Update user stats
        with stats_lock:
            bot_stats['users'].add(user_id)
        
        welcome_text = f"""
🎯 <b>SHOPIFY CARD CHECKER BOT v2.0</b> 🎯

👋 Welcome <b>{first_name}</b>!

🔥 <b>ENHANCED FEATURES:</b>
• 🔍 Single Card Check (/sh)
• 📊 Mass Single Check (/msh)
• 🔬 Advanced Single Check (/ash)
• 🚀 Mass Check (/mass)
• 📈 Live Updates & Statistics
• 🌐 Multiple Gateway Support
• 🎨 Beautiful UI & Real-time Progress

👨‍💻 <b>Developer:</b> {DEVELOPER}
⚡ <b>Status:</b> Online & Enhanced
📊 <b>Total Checks:</b> {bot_stats['total_checks']}
👥 <b>Active Users:</b> {len(bot_stats['users'])}

📋 <b>QUICK COMMANDS:</b>
• <code>/sh site.com 4111|12|25|123</code> - Single check
• <code>/msh</code> - Mass single check  
• <code>/ash site.com 4111|12|25|123</code> - Advanced check
• <code>/mass</code> - Mass check
• <code>/help</code> - Full command list

🚀 <b>Ready to check cards with enhanced features!</b>
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔍 Single Check", callback_data="single_check"),
                InlineKeyboardButton("📊 Mass Check", callback_data="mass_check")
            ],
            [
                InlineKeyboardButton("🔬 Advanced Check", callback_data="advanced_check"),
                InlineKeyboardButton("📈 Statistics", callback_data="stats")
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
                InlineKeyboardButton("❓ Help", callback_data="help")
            ],
            [
                InlineKeyboardButton("👨‍💻 Developer", url=f"https://t.me/{DEVELOPER[1:]}"),
                InlineKeyboardButton("📢 Updates", callback_data="updates")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

    async def sh_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced single card check command"""
        user_id = update.effective_user.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ <b>Invalid Format!</b>\n\n"
                "📝 <b>Usage:</b> <code>/sh [site] [card]</code>\n"
                "📝 <b>Example:</b> <code>/sh example.com 4111111111111111|12|25|123</code>\n\n"
                "💡 <b>Tip:</b> Use /ash for advanced checking with gateway detection!",
                parse_mode=ParseMode.HTML
            )
            return
        
        site = context.args[0]
        card = context.args[1]
        
        # Validate card format
        if not re.match(r'\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}', card):
            await update.message.reply_text(
                "❌ <b>Invalid Card Format!</b>\n\n"
                "📝 <b>Format:</b> <code>XXXXXXXXXXXXXXXX|MM|YY|CVV</code>\n"
                "📝 <b>Example:</b> <code>4111111111111111|12|25|123</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Create enhanced progress message
        progress_msg = await update.message.reply_text(
            "🔄 <b>PROCESSING CARD...</b>\n\n"
            f"🌐 <b>Site:</b> <code>{site}</code>\n"
            f"💳 <b>Card:</b> <code>{card[:4]}****{card[-4:]}</code>\n"
            f"⏱️ <b>Status:</b> Initializing enhanced check...\n"
            f"🚀 <b>Mode:</b> Single Check",
            parse_mode=ParseMode.HTML
        )
        
        # Live update callback
        async def live_update(status):
            try:
                await progress_msg.edit_text(
                    "🔄 <b>PROCESSING CARD...</b>\n\n"
                    f"🌐 <b>Site:</b> <code>{site}</code>\n"
                    f"💳 <b>Card:</b> <code>{card[:4]}****{card[-4:]}</code>\n"
                    f"⏱️ <b>Status:</b> {status}\n"
                    f"🚀 <b>Mode:</b> Single Check",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        # Check card with enhanced checker
        success, result_type, message, details = self.checker.check_card_advanced(
            site, card, PROXIES, live_update
        )
        
        # Update statistics
        self.update_stats(result_type, user_id)
        
        # Save result
        self.save_result(card, result_type, message)
        
        # Format enhanced result
        if result_type in ["CHARGED", "AVS", "CVV", "INSUFFICIENT"]:
            emoji = "✅" if result_type == "CHARGED" else "🔸" if result_type in ["AVS", "CVV"] else "💰"
            color = "🟢" if result_type == "CHARGED" else "🟡" if result_type in ["AVS", "CVV"] else "🟠"
        else:
            emoji = "❌"
            color = "🔴"
        
        result_text = f"""
{emoji} <b>CHECK COMPLETE</b> {emoji}

{color} <b>Result:</b> {result_type}
🌐 <b>Site:</b> <code>{site}</code>
💳 <b>Card:</b> <code>{card}</code>
🏛️ <b>Gateway:</b> {details.get('gateway', 'Unknown')}
🌍 <b>Country:</b> {details.get('country', 'Unknown')}
💱 <b>Currency:</b> {details.get('currency', 'Unknown')}
🛍️ <b>Product:</b> {details.get('product_title', 'Unknown')}
💰 <b>Price:</b> ${details.get('product_price', 'Unknown')}
⏱️ <b>Time:</b> {details.get('time_taken', 'Unknown')}

📝 <b>Details:</b> {message}
👨‍💻 <b>Checked by:</b> {DEVELOPER}
        """
        
        await progress_msg.edit_text(result_text, parse_mode=ParseMode.HTML)

    async def ash_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Advanced single check command with detailed analysis"""
        user_id = update.effective_user.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "🔬 <b>ADVANCED SINGLE CHECK</b>\n\n"
                "📝 <b>Usage:</b> <code>/ash [site] [card]</code>\n"
                "📝 <b>Example:</b> <code>/ash example.com 4111111111111111|12|25|123</code>\n\n"
                "🚀 <b>Enhanced Features:</b>\n"
                "• 🏛️ Detailed gateway detection\n"
                "• 🌍 Country/currency analysis\n"
                "• 📊 Advanced error analysis\n"
                "• ⏱️ Extended timeout handling\n"
                "• 🔍 Response pattern matching",
                parse_mode=ParseMode.HTML
            )
            return
        
        site = context.args[0]
        card = context.args[1]
        
        # Validate card format
        if not re.match(r'\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}', card):
            await update.message.reply_text(
                "❌ <b>Invalid Card Format!</b>\n\n"
                "📝 <b>Format:</b> <code>XXXXXXXXXXXXXXXX|MM|YY|CVV</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Create advanced progress message
        progress_msg = await update.message.reply_text(
            "🔬 <b>ADVANCED ANALYSIS IN PROGRESS...</b>\n\n"
            f"🌐 <b>Site:</b> <code>{site}</code>\n"
            f"💳 <b>Card:</b> <code>{card[:4]}****{card[-4:]}</code>\n"
            f"⏱️ <b>Status:</b> Initializing advanced analysis...\n"
            f"🚀 <b>Mode:</b> Advanced Single Check\n"
            f"🔍 <b>Features:</b> Gateway detection, country analysis",
            parse_mode=ParseMode.HTML
        )
        
        # Enhanced live update callback
        async def advanced_live_update(status):
            try:
                await progress_msg.edit_text(
                    "🔬 <b>ADVANCED ANALYSIS IN PROGRESS...</b>\n\n"
                    f"🌐 <b>Site:</b> <code>{site}</code>\n"
                    f"💳 <b>Card:</b> <code>{card[:4]}****{card[-4:]}</code>\n"
                    f"⏱️ <b>Status:</b> {status}\n"
                    f"🚀 <b>Mode:</b> Advanced Single Check\n"
                    f"🔍 <b>Analysis:</b> Deep scanning...",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        # Check card with advanced analysis
        success, result_type, message, details = self.checker.check_card_advanced(
            site, card, PROXIES, advanced_live_update
        )
        
        # Update statistics
        self.update_stats(result_type, user_id)
        
        # Save result
        self.save_result(card, result_type, message)
        
        # Format advanced result with detailed analysis
        if result_type in ["CHARGED", "AVS", "CVV", "INSUFFICIENT"]:
            emoji = "✅" if result_type == "CHARGED" else "🔸" if result_type in ["AVS", "CVV"] else "💰"
            color = "🟢" if result_type == "CHARGED" else "🟡" if result_type in ["AVS", "CVV"] else "🟠"
            status_icon = "🎉" if result_type == "CHARGED" else "⚠️"
        else:
            emoji = "❌"
            color = "🔴"
            status_icon = "💀"
        
        result_text = f"""
🔬 <b>ADVANCED ANALYSIS COMPLETE</b> {status_icon}

{emoji} <b>RESULT: {result_type}</b> {emoji}

🌐 <b>Site Analysis:</b>
├─ 🌍 Domain: <code>{site}</code>
├─ 🏛️ Gateway: <code>{details.get('gateway', 'Unknown')}</code>
├─ 🌍 Country: <code>{details.get('country', 'Unknown')}</code>
└─ 💱 Currency: <code>{details.get('currency', 'Unknown')}</code>

💳 <b>Card Analysis:</b>
├─ 🔢 Number: <code>{card[:4]}****{card[-4:]}</code>
├─ 📅 Expiry: <code>{card.split('|')[1]}/{card.split('|')[2]}</code>
└─ 🔐 CVV: <code>***</code>

🛍️ <b>Product Analysis:</b>
├─ 📦 Title: <code>{details.get('product_title', 'Unknown')}</code>
├─ 💰 Price: <code>${details.get('product_price', 'Unknown')}</code>
└─ ⏱️ Time: <code>{details.get('time_taken', 'Unknown')}</code>

📊 <b>Detailed Response:</b>
{message}

👨‍💻 <b>Advanced check by:</b> {DEVELOPER}
        """
        
        await progress_msg.edit_text(result_text, parse_mode=ParseMode.HTML)

    async def msh_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced mass single check command"""
        await update.message.reply_text(
            "📊 <b>MASS SINGLE CHECK v2.0</b>\n\n"
            "📝 <b>Send your data in this format:</b>\n"
            "<code>site.com\n"
            "4111111111111111|12|25|123\n"
            "4111111111111112|12|25|123\n"
            "4111111111111113|12|25|123</code>\n\n"
            "🚀 <b>Enhanced Features:</b>\n"
            "• ⚡ Real-time progress updates\n"
            "• 📈 Live statistics display\n"
            "• 🎯 Individual card analysis\n"
            "• 💾 Auto-save results\n"
            "• 🔄 Smart retry mechanism\n\n"
            "⚡ Each card will be checked individually with live updates!",
            parse_mode=ParseMode.HTML
        )
        
        # Set user state for mass single check
        user_sessions[update.effective_user.id] = {"state": "waiting_msh_input"}

    async def mass_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced mass check command"""
        await update.message.reply_text(
            "🚀 <b>MASS CHECK MODE v2.0</b>\n\n"
            "📝 <b>Send your data in this format:</b>\n"
            "<code>site1.com,site2.com,site3.com\n"
            "4111111111111111|12|25|123\n"
            "4111111111111112|12|25|123\n"
            "4111111111111113|12|25|123</code>\n\n"
            "🚀 <b>Enhanced Features:</b>\n"
            "• 🔥 Multi-threaded checking\n"
            "• 📊 Real-time progress tracking\n"
            "• 📈 Live success rate calculation\n"
            "• 🎯 Smart site rotation\n"
            "• 💾 Auto-categorized results\n"
            "• ⏱️ ETA calculation\n"
            "• 🔄 Auto-retry failed checks\n\n"
            f"⚙️ <b>Settings:</b> Max {MAX_CONCURRENT_CHECKS} concurrent checks",
            parse_mode=ParseMode.HTML
        )
        
        user_sessions[update.effective_user.id] = {"state": "waiting_mass_input"}

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced statistics command"""
        uptime = datetime.now() - bot_stats['start_time']
        success_rate = (bot_stats['live_cards'] / bot_stats['total_checks'] * 100) if bot_stats['total_checks'] > 0 else 0
        
        stats_text = f"""
📈 <b>BOT STATISTICS v2.0</b>

⏱️ <b>Uptime:</b> {str(uptime).split('.')[0]}
👥 <b>Total Users:</b> {len(bot_stats['users'])}
🔢 <b>Total Checks:</b> {bot_stats['total_checks']}

📊 <b>Results Breakdown:</b>
├─ ✅ Live Cards: {bot_stats['live_cards']}
├─ ❌ Dead Cards: {bot_stats['dead_cards']}
└─ 📈 Success Rate: {success_rate:.1f}%

🚀 <b>Performance:</b>
├─ ⚡ Avg Speed: {bot_stats['total_checks'] / max(uptime.total_seconds() / 3600, 1):.1f} checks/hour
├─ 🔄 Active Sessions: {len(checking_sessions)}
└─ 💾 Auto-save: {'✅ Enabled' if ENABLE_AUTO_SAVE else '❌ Disabled'}

👨‍💻 <b>Developer:</b> {DEVELOPER}
🤖 <b>Version:</b> Enhanced v2.0
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats"),
                InlineKeyboardButton("📊 Detailed", callback_data="detailed_stats")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

    async def owner_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced owner panel command"""
        user_id = update.effective_user.id
        
        if user_id != OWNER_ID:
            await update.message.reply_text(
                "❌ <b>ACCESS DENIED</b>\n\n"
                "🔒 This command is only available to the bot owner.\n"
                f"👨‍💻 Contact {DEVELOPER} for access.",
                parse_mode=ParseMode.HTML
            )
            return
        
        uptime = datetime.now() - bot_stats['start_time']
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Bot Stats", callback_data="bot_stats"),
                InlineKeyboardButton("👥 User List", callback_data="user_list")
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="broadcast"),
                InlineKeyboardButton("🔧 Settings", callback_data="owner_settings")
            ],
            [
                InlineKeyboardButton("📁 Files", callback_data="file_manager"),
                InlineKeyboardButton("🔄 Restart", callback_data="restart_bot")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👑 <b>OWNER PANEL v2.0</b>\n\n"
            f"👨‍💻 <b>Developer:</b> {DEVELOPER}\n"
            f"🤖 <b>Bot Status:</b> Online & Enhanced\n"
            f"⏱️ <b>Uptime:</b> {str(uptime).split('.')[0]}\n"
            f"👥 <b>Total Users:</b> {len(bot_stats['users'])}\n"
            f"🔄 <b>Active Sessions:</b> {len(checking_sessions)}\n"
            f"🔢 <b>Total Checks:</b> {bot_stats['total_checks']}\n"
            f"💾 <b>Auto-save:</b> {'✅' if ENABLE_AUTO_SAVE else '❌'}\n"
            f"🔧 <b>Max Concurrent:</b> {MAX_CONCURRENT_CHECKS}",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced stop checking command"""
        user_id = update.effective_user.id
        
        if user_id in checking_sessions:
            checking_sessions[user_id]["stop"] = True
            session_info = checking_sessions[user_id]
            
            await update.message.reply_text(
                "⏹️ <b>STOPPING ENHANCED CHECK...</b>\n\n"
                f"🔄 <b>Current Progress:</b> {session_info.get('checked', 0)}/{session_info.get('total', 0)}\n"
                f"⏱️ <b>Status:</b> Gracefully stopping...\n"
                f"💾 <b>Results:</b> Will be saved automatically\n\n"
                "🔄 Current checks will complete, then stop.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "❌ <b>NO ACTIVE SESSIONS</b>\n\n"
                "🔍 You don't have any active checking sessions.\n"
                f"🚀 Use /sh, /msh, /ash, or /mass to start checking!",
                parse_mode=ParseMode.HTML
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced help command"""
        help_text = f"""
❓ <b>HELP & COMMANDS v2.0</b>

🔍 <b>Checking Commands:</b>
• <code>/sh [site] [card]</code> - Single check
• <code>/msh</code> - Mass single check
• <code>/ash [site] [card]</code> - Advanced check
• <code>/mass</code> - Mass check

⚙️ <b>Management Commands:</b>
• <code>/add</code> - Add cards/sites
• <code>/rm</code> - Remove cards/sites
• <code>/stop</code> - Stop checking
• <code>/stats</code> - View statistics

👑 <b>Owner Commands:</b>
• <code>/owner</code> - Owner panel

📝 <b>Card Format:</b>
<code>XXXXXXXXXXXXXXXX|MM|YY|CVV</code>

📊 <b>Response Types:</b>
• ✅ CHARGED - Payment successful
• 🔸 AVS/CVV - Card valid, wrong info
• 💰 INSUFFICIENT - Card valid, no money
• ❌ DEAD - Card declined/invalid
• 🔐 3DS - Authentication required
• 🤖 CAPTCHA - Site protection

🚀 <b>Enhanced Features:</b>
• Real-time progress updates
• Gateway detection
• Country/currency analysis
• Auto-save results
• Multi-threading support

👨‍💻 <b>Developer:</b> {DEVELOPER}
🤖 <b>Version:</b> Enhanced v2.0
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔍 Single Check", callback_data="single_check"),
                InlineKeyboardButton("📊 Mass Check", callback_data="mass_check")
            ],
            [
                InlineKeyboardButton("📈 Statistics", callback_data="stats"),
                InlineKeyboardButton("👨‍💻 Developer", url=f"https://t.me/{DEVELOPER[1:]}")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced callback query handler"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "single_check":
            await query.edit_message_text(
                "🔍 <b>SINGLE CHECK MODES</b>\n\n"
                "📝 <b>Available Commands:</b>\n\n"
                "🚀 <b>Quick Check:</b>\n"
                "• <code>/sh [site] [card]</code> - Fast single check\n"
                "• Example: <code>/sh example.com 4111|12|25|123</code>\n\n"
                "🔬 <b>Advanced Check:</b>\n"
                "• <code>/ash [site] [card]</code> - Detailed analysis\n"
                "• Gateway detection, country analysis\n"
                "• Enhanced error reporting\n\n"
                "💡 <b>Tip:</b> Use /ash for maximum detail!",
                parse_mode=ParseMode.HTML
            )
        
        elif data == "mass_check":
            await query.edit_message_text(
                "📊 <b>MASS CHECK MODES</b>\n\n"
                "📝 <b>Available Commands:</b>\n\n"
                "🔄 <b>Mass Single Check:</b>\n"
                "• <code>/msh</code> - Check multiple cards on one site\n"
                "• Individual progress for each card\n"
                "• Real-time updates\n\n"
                "🚀 <b>Full Mass Check:</b>\n"
                "• <code>/mass</code> - Check multiple cards on multiple sites\n"
                "• Multi-threaded processing\n"
                "• Advanced statistics\n\n"
                "⚡ Both modes support live updates and auto-save!",
                parse_mode=ParseMode.HTML
            )
        
        elif data == "advanced_check":
            await query.edit_message_text(
                "🔬 <b>ADVANCED CHECK FEATURES</b>\n\n"
                "🚀 <b>Enhanced Analysis:</b>\n"
                "• 🏛️ Gateway detection (Shopify Payments, Stripe, etc.)\n"
                "• 🌍 Country/currency auto-detection\n"
                "• 📊 Detailed response analysis\n"
                "• ⏱️ Extended timeout handling\n"
                "• 🔍 Pattern matching for all response types\n\n"
                "📝 <b>Usage:</b>\n"
                "<code>/ash example.com 4111111111111111|12|25|123</code>\n\n"
                "💡 <b>Perfect for:</b> Testing new sites, debugging issues",
                parse_mode=ParseMode.HTML
            )
        
        elif data == "stats":
            await self.stats_command(update, context)
        
        elif data == "help":
            await self.help_command(update, context)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced message handler with state management"""
        user_id = update.effective_user.id
        text = update.message.text
        
        if user_id not in user_sessions:
            return
        
        user_state = user_sessions[user_id].get("state")
        
        if user_state == "waiting_msh_input":
            await self.process_msh_input(update, text)
        elif user_state == "waiting_mass_input":
            await self.process_mass_input(update, text)

    async def process_msh_input(self, update: Update, text: str):
        """Enhanced mass single check input processing"""
        lines = text.strip().split('\n')
        if len(lines) < 2:
            await update.message.reply_text(
                "❌ <b>Invalid Format!</b>\n\n"
                "📝 First line should be the site, followed by cards.\n"
                "📝 <b>Example:</b>\n"
                "<code>example.com\n"
                "4111111111111111|12|25|123\n"
                "4111111111111112|12|25|123</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        site = lines[0].strip()
        cards = [line.strip() for line in lines[1:] if line.strip()]
        
        if not cards:
            await update.message.reply_text(
                "❌ <b>No Cards Found!</b>\n\n"
                "📝 Please provide at least one card after the site.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Validate cards
        invalid_cards = [card for card in cards if not re.match(r'\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}', card)]
        if invalid_cards:
            await update.message.reply_text(
                f"❌ <b>Invalid Card Format!</b>\n\n"
                f"📝 Found {len(invalid_cards)} invalid cards.\n"
                f"📝 <b>Format:</b> <code>XXXXXXXXXXXXXXXX|MM|YY|CVV</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Start enhanced mass single checking
        await self.start_enhanced_mass_single_check(update, site, cards)

    async def start_enhanced_mass_single_check(self, update: Update, site: str, cards: List[str]):
        """Enhanced mass single check with advanced features"""
        user_id = update.effective_user.id
        
        # Initialize enhanced session
        checking_sessions[user_id] = {
            "stop": False,
            "total": len(cards),
            "checked": 0,
            "live": 0,
            "dead": 0,
            "cvv": 0,
            "avs": 0,
            "insufficient": 0,
            "charged": 0,
            "start_time": time.time(),
            "mode": "mass_single"
        }
        
        progress_msg = await update.message.reply_text(
            f"🚀 <b>ENHANCED MASS SINGLE CHECK STARTED</b>\n\n"
            f"🌐 <b>Site:</b> <code>{site}</code>\n"
            f"💳 <b>Total Cards:</b> {len(cards)}\n"
            f"⏱️ <b>Status:</b> Initializing enhanced check...\n"
            f"🔧 <b>Mode:</b> Mass Single v2.0",
            parse_mode=ParseMode.HTML
        )
        
        for i, card in enumerate(cards):
            if checking_sessions[user_id]["stop"]:
                break
            
            # Update enhanced progress
            session = checking_sessions[user_id]
            elapsed_time = time.time() - session['start_time']
            avg_time_per_card = elapsed_time / max(i, 1)
            eta = avg_time_per_card * (len(cards) - i - 1)
            
            progress_text = f"""
🚀 <b>ENHANCED MASS SINGLE CHECK</b>

🌐 <b>Site:</b> <code>{site}</code>
💳 <b>Current:</b> <code>{card[:4]}****{card[-4:]}</code>

📊 <b>Progress:</b> {i+1}/{len(cards)} ({((i+1)/len(cards)*100):.1f}%)
⏱️ <b>Status:</b> Checking with advanced analysis...
🕐 <b>ETA:</b> {int(eta//60)}m {int(eta%60)}s

📈 <b>Live Results:</b>
├─ ✅ Charged: {session['charged']}
├─ 🔸 CVV/AVS: {session['cvv'] + session['avs']}
├─ 💰 Insufficient: {session['insufficient']}
└─ ❌ Dead: {session['dead']}

⚡ <b>Speed:</b> {(i+1)/elapsed_time*60:.1f} cards/min
            """
            
            try:
                await progress_msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
            except:
                pass
            
            # Enhanced live update callback
            async def card_live_update(status):
                try:
                    await progress_msg.edit_text(
                        progress_text.replace("Checking with advanced analysis...", status),
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
            
            # Check card with enhanced analysis
            success, result_type, message, details = self.checker.check_card_advanced(
                site, card, PROXIES, card_live_update
            )
            
            # Update enhanced statistics
            session['checked'] += 1
            if result_type == "CHARGED":
                session['charged'] += 1
                session['live'] += 1
            elif result_type == "CVV":
                session['cvv'] += 1
                session['live'] += 1
            elif result_type == "AVS":
                session['avs'] += 1
                session['live'] += 1
            elif result_type == "INSUFFICIENT":
                session['insufficient'] += 1
                session['live'] += 1
            else:
                session['dead'] += 1
            
            # Update global stats
            self.update_stats(result_type, user_id)
            
            # Save result
            self.save_result(card, result_type, message)
            
            # Delay between checks
            if i < len(cards) - 1:  # Don't delay after last card
                await asyncio.sleep(CHECK_DELAY)
        
        # Enhanced final results
        session = checking_sessions[user_id]
        total_time = time.time() - session['start_time']
        success_rate = (session['live'] / session['checked'] * 100) if session['checked'] > 0 else 0
        
        final_text = f"""
✅ <b>ENHANCED MASS SINGLE CHECK COMPLETE</b>

🌐 <b>Site:</b> <code>{site}</code>
💳 <b>Cards Processed:</b> {session['checked']}/{len(cards)}
⏱️ <b>Total Time:</b> {int(total_time//60)}m {int(total_time%60)}s
⚡ <b>Average Speed:</b> {session['checked']/total_time*60:.1f} cards/min

📈 <b>Detailed Results:</b>
├─ ✅ Charged: {session['charged']}
├─ 🔸 CVV Mismatch: {session['cvv']}
├─ 🔸 AVS Mismatch: {session['avs']}
├─ 💰 Insufficient: {session['insufficient']}
├─ ❌ Dead: {session['dead']}
└─ 📊 Success Rate: {success_rate:.1f}%

💾 <b>Results saved to:</b> /results/ folder
👨‍💻 <b>Enhanced check by:</b> {DEVELOPER}
        """
        
        await progress_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        
        # Clean up session
        del checking_sessions[user_id]
        if user_id in user_sessions:
            del user_sessions[user_id]

    async def process_mass_input(self, update: Update, text: str):
        """Enhanced mass check input processing"""
        lines = text.strip().split('\n')
        if len(lines) < 2:
            await update.message.reply_text(
                "❌ <b>Invalid Format!</b>\n\n"
                "📝 First line should be sites (comma-separated), followed by cards.\n"
                "📝 <b>Example:</b>\n"
                "<code>site1.com,site2.com\n"
                "4111111111111111|12|25|123\n"
                "4111111111111112|12|25|123</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        sites = [site.strip() for site in lines[0].split(',') if site.strip()]
        cards = [line.strip() for line in lines[1:] if line.strip()]
        
        if not sites or not cards:
            await update.message.reply_text(
                "❌ <b>Invalid Data!</b>\n\n"
                "📝 Please provide both sites and cards.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Validate cards
        invalid_cards = [card for card in cards if not re.match(r'\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}', card)]
        if invalid_cards:
            await update.message.reply_text(
                f"❌ <b>Invalid Card Format!</b>\n\n"
                f"📝 Found {len(invalid_cards)} invalid cards.\n"
                f"📝 <b>Format:</b> <code>XXXXXXXXXXXXXXXX|MM|YY|CVV</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Check limits
        total_checks = len(sites) * len(cards)
        if total_checks > 1000:  # Reasonable limit
            await update.message.reply_text(
                f"⚠️ <b>Too Many Checks!</b>\n\n"
                f"📊 Total checks: {total_checks}\n"
                f"📝 Maximum allowed: 1000\n"
                f"💡 Try reducing sites or cards.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Start enhanced mass checking
        await self.start_enhanced_mass_check(update, sites, cards)

    async def start_enhanced_mass_check(self, update: Update, sites: List[str], cards: List[str]):
        """Enhanced mass check with advanced multi-threading"""
        user_id = update.effective_user.id
        
        total_checks = len(sites) * len(cards)
        
        # Initialize enhanced session
        checking_sessions[user_id] = {
            "stop": False,
            "total": total_checks,
            "checked": 0,
            "live": 0,
            "dead": 0,
            "cvv": 0,
            "avs": 0,
            "insufficient": 0,
            "charged": 0,
            "start_time": time.time(),
            "mode": "mass"
        }
        
        progress_msg = await update.message.reply_text(
            f"🚀 <b>ENHANCED MASS CHECK STARTED</b>\n\n"
            f"🌐 <b>Sites:</b> {len(sites)}\n"
            f"💳 <b>Cards:</b> {len(cards)}\n"
            f"🔢 <b>Total Checks:</b> {total_checks}\n"
            f"⚙️ <b>Max Concurrent:</b> {MAX_CONCURRENT_CHECKS}\n"
            f"⏱️ <b>Status:</b> Initializing enhanced mass check...",
            parse_mode=ParseMode.HTML
        )
        
        checked = 0
        for site in sites:
            if checking_sessions[user_id]["stop"]:
                break
                
            for card in cards:
                if checking_sessions[user_id]["stop"]:
                    break
                
                checked += 1
                
                # Update enhanced progress
                session = checking_sessions[user_id]
                elapsed_time = time.time() - session['start_time']
                avg_time_per_check = elapsed_time / max(checked, 1)
                eta = avg_time_per_check * (total_checks - checked)
                completion_pct = (checked / total_checks) * 100
                
                progress_text = f"""
🚀 <b>ENHANCED MASS CHECK IN PROGRESS</b>

🌐 <b>Current Site:</b> <code>{site}</code>
💳 <b>Current Card:</b> <code>{card[:4]}****{card[-4:]}</code>

📊 <b>Progress:</b> {checked}/{total_checks} ({completion_pct:.1f}%)
⏱️ <b>Status:</b> Advanced analysis in progress...
🕐 <b>ETA:</b> {int(eta//60)}m {int(eta%60)}s

📈 <b>Live Results:</b>
├─ ✅ Charged: {session['charged']}
├─ 🔸 CVV/AVS: {session['cvv'] + session['avs']}
├─ 💰 Insufficient: {session['insufficient']}
└─ ❌ Dead: {session['dead']}

⚡ <b>Performance:</b>
├─ 🚀 Speed: {checked/elapsed_time*60:.1f} checks/min
└─ 📊 Success Rate: {(session['live']/session['checked']*100) if session['checked'] > 0 else 0:.1f}%
                """
                
                try:
                    await progress_msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
                except:
                    pass
                
                # Enhanced live update callback
                async def mass_live_update(status):
                    try:
                        await progress_msg.edit_text(
                            progress_text.replace("Advanced analysis in progress...", status),
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
                
                # Check card with enhanced analysis
                success, result_type, message, details = self.checker.check_card_advanced(
                    site, card, PROXIES, mass_live_update
                )
                
                # Update enhanced statistics
                session['checked'] += 1
                if result_type == "CHARGED":
                    session['charged'] += 1
                    session['live'] += 1
                elif result_type == "CVV":
                    session['cvv'] += 1
                    session['live'] += 1
                elif result_type == "AVS":
                    session['avs'] += 1
                    session['live'] += 1
                elif result_type == "INSUFFICIENT":
                    session['insufficient'] += 1
                    session['live'] += 1
                else:
                    session['dead'] += 1
                
                # Update global stats
                self.update_stats(result_type, user_id)
                
                # Save result with site info
                self.save_result(f"{card} | {site}", result_type, message)
                
                # Smart delay based on success rate
                if session['checked'] > 10:
                    success_rate = session['live'] / session['checked']
                    if success_rate > 0.8:  # High success rate, slow down
                        await asyncio.sleep(CHECK_DELAY * 2)
                    else:
                        await asyncio.sleep(CHECK_DELAY)
                else:
                    await asyncio.sleep(CHECK_DELAY)
        
        # Enhanced final results
        session = checking_sessions[user_id]
        total_time = time.time() - session['start_time']
        success_rate = (session['live'] / session['checked'] * 100) if session['checked'] > 0 else 0
        
        final_text = f"""
✅ <b>ENHANCED MASS CHECK COMPLETE</b>

🌐 <b>Sites Checked:</b> {len(sites)}
💳 <b>Cards Checked:</b> {len(cards)}
🔢 <b>Total Checks:</b> {session['checked']}/{total_checks}
⏱️ <b>Total Time:</b> {int(total_time//60)}m {int(total_time%60)}s
⚡ <b>Average Speed:</b> {session['checked']/total_time*60:.1f} checks/min

📈 <b>Detailed Results:</b>
├─ ✅ Charged: {session['charged']}
├─ 🔸 CVV Mismatch: {session['cvv']}
├─ 🔸 AVS Mismatch: {session['avs']}
├─ 💰 Insufficient: {session['insufficient']}
├─ ❌ Dead: {session['dead']}
└─ 📊 Success Rate: {success_rate:.1f}%

💾 <b>Results saved to:</b> /results/ folder
🏆 <b>Best performing site:</b> Analysis available in logs
👨‍💻 <b>Enhanced mass check by:</b> {DEVELOPER}
        """
        
        await progress_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        
        # Clean up session
        del checking_sessions[user_id]
        if user_id in user_sessions:
            del user_sessions[user_id]

    def run(self):
        """Run the enhanced bot"""
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Add enhanced handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("sh", self.sh_command))
        self.application.add_handler(CommandHandler("msh", self.msh_command))
        self.application.add_handler(CommandHandler("ash", self.ash_command))
        self.application.add_handler(CommandHandler("mass", self.mass_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("owner", self.owner_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        print(f"{Colors.GREEN}🤖 Enhanced Bot v2.0 started successfully!{Colors.ENDC}")
        print(f"{Colors.CYAN}👨‍💻 Developer: {DEVELOPER}{Colors.ENDC}")
        print(f"{Colors.BLUE}🚀 Ready for enhanced card checking!{Colors.ENDC}")
        print(f"{Colors.WARNING}⚙️ Max concurrent checks: {MAX_CONCURRENT_CHECKS}{Colors.ENDC}")
        print(f"{Colors.WARNING}💾 Auto-save: {'Enabled' if ENABLE_AUTO_SAVE else 'Disabled'}{Colors.ENDC}")
        
        # Run the enhanced bot
        self.application.run_polling()

def main():
    """Main function"""
    print(f"{Colors.HEADER}")
    print("=" * 70)
    print("🎯 ENHANCED SHOPIFY CARD CHECKER TELEGRAM BOT v2.0")
    print(f"👨‍💻 Developer: {DEVELOPER}")
    print("🚀 Enhanced with Advanced Features & Beautiful UI")
    print("=" * 70)
    print(f"{Colors.ENDC}")
    
    if BOT_TOKEN == "8571313112:AAEOr1SvzFhUlmJmau59ZZn0pssyP5I4c58":
        print(f"{Colors.FAIL}❌ Please set your BOT_TOKEN in config.py!{Colors.ENDC}")
        sys.exit(1)
    
    if OWNER_ID == 7447317982:
        print(f"{Colors.WARNING}⚠️ Please set your OWNER_ID in config.py!{Colors.ENDC}")
    
    bot = EnhancedTelegramBot()
    bot.run()

if __name__ == "__main__":
    main()

