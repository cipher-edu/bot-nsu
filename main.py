import asyncio
import os
import re
import random
import string
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from io import BytesIO

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)
from telegram.error import TelegramError

import asyncpg
from asyncpg import Pool
from dotenv import load_dotenv

# Load .env file if present (helpful for local development)
load_dotenv()
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
# Allow either a full DATABASE_URL or build it from DB_* variables
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    db_user = os.getenv('DB_USER', 'botuser')
    db_password = os.getenv('DB_PASSWORD', 'password')
    db_host = os.getenv('DB_HOST', 'postgres')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'telegram_bot')
    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]

# Reklama kanali (a'zolik tekshirilmaydi, faqat ko'rsatiladi)
ADVERTISING_CHANNEL = "@Otkir_Rahmat"
ADVERTISING_CHANNEL_NAME = "Otkir Rahmat"

# Conversation states
SUBSCRIPTION, PHONE, CAPTCHA, MENU = range(4)
POLL_TITLE, POLL_DESCRIPTION, POLL_IMAGE, POLL_CANDIDATES, POLL_CONFIRM = range(5, 10)
CHANNEL_ADD = 20

# Global database pool
db_pool: Optional[Pool] = None


# ================= DATABASE FUNCTIONS =================

async def init_db(app=None):
    """Initialize database connection and create tables"""
    global db_pool
    
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20,
        command_timeout=60
    )
    
    async with db_pool.acquire() as conn:
        # Users table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                phone_number VARCHAR(20) UNIQUE,
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                is_verified BOOLEAN DEFAULT FALSE,
                is_banned BOOLEAN DEFAULT FALSE,
                registered_at TIMESTAMP DEFAULT NOW(),
                last_activity TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Channels table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT UNIQUE NOT NULL,
                channel_username VARCHAR(255),
                channel_title VARCHAR(255),
                is_required BOOLEAN DEFAULT TRUE,
                added_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Polls table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                id SERIAL PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                image_file_id VARCHAR(255),
                created_by BIGINT REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT NOW(),
                is_active BOOLEAN DEFAULT TRUE,
                ends_at TIMESTAMP,
                total_votes INTEGER DEFAULT 0
            )
        ''')
        
        # Poll candidates table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS poll_candidates (
                id SERIAL PRIMARY KEY,
                poll_id INTEGER REFERENCES polls(id) ON DELETE CASCADE,
                candidate_name VARCHAR(255) NOT NULL,
                votes INTEGER DEFAULT 0,
                UNIQUE(poll_id, candidate_name)
            )
        ''')
        
        # Votes table (to prevent multiple votes)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id SERIAL PRIMARY KEY,
                poll_id INTEGER REFERENCES polls(id) ON DELETE CASCADE,
                user_id BIGINT REFERENCES users(user_id),
                candidate_id INTEGER REFERENCES poll_candidates(id) ON DELETE CASCADE,
                voted_at TIMESTAMP DEFAULT NOW(),
                ip_hash VARCHAR(64),
                UNIQUE(poll_id, user_id)
            )
        ''')
        
        # Captcha sessions table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS captcha_sessions (
                user_id BIGINT PRIMARY KEY,
                captcha_answer VARCHAR(10),
                attempts INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Anti-fraud table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fraud_detection (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                action_type VARCHAR(50),
                suspicious_score INTEGER DEFAULT 0,
                details JSONB,
                detected_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Poll shares table (for sharing polls to channels)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS poll_shares (
                id SERIAL PRIMARY KEY,
                poll_id INTEGER REFERENCES polls(id) ON DELETE CASCADE,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                shared_by BIGINT REFERENCES users(user_id),
                shared_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Create indexes
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_number)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_votes_poll ON votes(poll_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_votes_user ON votes(user_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_polls_active ON polls(is_active)')


async def get_user(user_id: int):
    """Get user from database"""
    async with db_pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)


async def create_user(user_id: int, username: str, phone: str, first_name: str, last_name: str):
    """Create new user"""
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, username, phone_number, first_name, last_name, is_verified)
            VALUES ($1, $2, $3, $4, $5, FALSE)
            ON CONFLICT (user_id) DO UPDATE SET
                username = $2,
                phone_number = $3,
                first_name = $4,
                last_name = $5
        ''', user_id, username, phone, first_name, last_name)


async def verify_user(user_id: int):
    """Mark user as verified"""
    async with db_pool.acquire() as conn:
        await conn.execute('UPDATE users SET is_verified = TRUE WHERE user_id = $1', user_id)


async def get_channels():
    """Get all channels"""
    async with db_pool.acquire() as conn:
        return await conn.fetch('SELECT * FROM channels ORDER BY added_at DESC')


async def add_channel(channel_id: int, username: str, title: str, is_required: bool = True):
    """Add channel to database"""
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO channels (channel_id, channel_username, channel_title, is_required)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (channel_id) DO UPDATE SET
                channel_username = $2,
                channel_title = $3,
                is_required = $4
        ''', channel_id, username, title, is_required)


async def remove_channel(channel_id: int):
    """Remove channel from database"""
    async with db_pool.acquire() as conn:
        await conn.execute('DELETE FROM channels WHERE id = $1', channel_id)


# ================= CAPTCHA SYSTEM =================

def generate_captcha():
    """Generate advanced math captcha - Senior level"""
    captcha_type = random.choice(['basic', 'medium', 'advanced'])
    
    if captcha_type == 'basic':
        # Basic arithmetic
        num1 = random.randint(1, 20)
        num2 = random.randint(1, 20)
        operation = random.choice(['+', '-', '*'])
        
        if operation == '+':
            answer = num1 + num2
            question = f"❓ {num1} + {num2} = ?"
        elif operation == '-':
            # Ensure positive result
            if num1 < num2:
                num1, num2 = num2, num1
            answer = num1 - num2
            question = f"❓ {num1} - {num2} = ?"
        else:  # multiplication
            num1 = random.randint(2, 10)
            num2 = random.randint(2, 10)
            answer = num1 * num2
            question = f"❓ {num1} × {num2} = ?"
    
    elif captcha_type == 'medium':
        # Two operations
        num1 = random.randint(1, 15)
        num2 = random.randint(1, 15)
        num3 = random.randint(1, 10)
        
        choice = random.choice([1, 2, 3])
        if choice == 1:
            # (a + b) - c
            answer = (num1 + num2) - num3
            question = f"❓ ({num1} + {num2}) - {num3} = ?"
        elif choice == 2:
            # (a - b) + c
            if num1 < num2:
                num1, num2 = num2, num1
            answer = (num1 - num2) + num3
            question = f"❓ ({num1} - {num2}) + {num3} = ?"
        else:
            # a * b + c
            num1 = random.randint(2, 8)
            num2 = random.randint(2, 8)
            answer = num1 * num2 + num3
            question = f"❓ {num1} × {num2} + {num3} = ?"
    
    else:  # advanced
        # Word problems or sequences
        choice = random.choice([1, 2, 3])
        
        if choice == 1:
            # Simple sequence
            start = random.randint(2, 10)
            step = random.randint(2, 5)
            nums = [start + i * step for i in range(4)]
            answer = nums[-1] + step
            question = f"❓ Ketma-ketlikni davom ettiring:\n{nums[0]}, {nums[1]}, {nums[2]}, {nums[3]}, ?"
        
        elif choice == 2:
            # Count objects
            count = random.randint(5, 15)
            objects = random.choice(['🍎', '⚽', '📚', '🌟', '💎'])
            answer = count
            question = f"❓ Nechta {objects} bor?\n" + (objects * count)
        
        else:
            # Simple division
            num2 = random.randint(2, 10)
            answer = random.randint(2, 15)
            num1 = num2 * answer
            question = f"❓ {num1} ÷ {num2} = ?"
    
    return question, str(answer)


async def save_captcha(user_id: int, answer: str):
    """Save captcha answer"""
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO captcha_sessions (user_id, captcha_answer, attempts)
            VALUES ($1, $2, 0)
            ON CONFLICT (user_id) DO UPDATE SET
                captcha_answer = $2,
                attempts = 0,
                created_at = NOW()
        ''', user_id, answer)


async def verify_captcha(user_id: int, user_answer: str):
    """Verify captcha answer"""
    async with db_pool.acquire() as conn:
        session = await conn.fetchrow(
            'SELECT * FROM captcha_sessions WHERE user_id = $1',
            user_id
        )
        
        if not session:
            return False, 0
        
        attempts = session['attempts'] + 1
        await conn.execute(
            'UPDATE captcha_sessions SET attempts = $1 WHERE user_id = $2',
            attempts, user_id
        )
        
        if session['captcha_answer'] == user_answer.strip():
            await conn.execute('DELETE FROM captcha_sessions WHERE user_id = $1', user_id)
            return True, attempts
        
        return False, attempts


# ================= SUBSCRIPTION CHECK =================

async def check_subscriptions(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is subscribed to all required channels"""
    channels = await get_channels()
    
    not_subscribed = []
    
    for channel in channels:
        # Faqat majburiy kanallarni tekshirish
        if not channel.get('is_required', True):
            continue
            
        try:
            member = await context.bot.get_chat_member(channel['channel_id'], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                not_subscribed.append(channel)
        except TelegramError:
            not_subscribed.append(channel)
    
    return not_subscribed


async def get_subscription_keyboard(channels: List):
    """Create keyboard with subscription links"""
    keyboard = []
    
    # Majburiy kanallar
    for channel in channels:
        if channel['channel_username']:
            url = f"https://t.me/{channel['channel_username']}"
        else:
            url = f"https://t.me/c/{str(channel['channel_id'])[4:]}"
        
        keyboard.append([InlineKeyboardButton(
            f"📢 {channel['channel_title']}", 
            url=url
        )])
    
    # Reklama kanali (majburiy emas)
    keyboard.append([InlineKeyboardButton(
        f"⭐️ {ADVERTISING_CHANNEL_NAME}",
        url=f"https://t.me/{ADVERTISING_CHANNEL.replace('@', '')}"
    )])
    
    keyboard.append([InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_subscription")])
    
    return InlineKeyboardMarkup(keyboard)


# ================= BOT HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler - Senior level with proper flow"""
    user = update.effective_user
    
    # Get user from database
    db_user = await get_user(user.id)
    
    # ==================== FULLY REGISTERED USER ====================
    if db_user and db_user['is_verified']:
        # Check if user is banned
        if db_user['is_banned']:
            await update.message.reply_text(
                "🚫 Siz bloklangansiz!\n\n"
                "Sabab: Qoidalarni buzganlik.\n"
                "Ma'lumot uchun: @support"
            )
            return ConversationHandler.END
        
        # Update last activity
        async with db_pool.acquire() as conn:
            await conn.execute(
                'UPDATE users SET last_activity = NOW() WHERE user_id = $1',
                user.id
            )
        
        # Check subscriptions (ALWAYS CHECK EVEN FOR VERIFIED USERS)
        not_subscribed = await check_subscriptions(user.id, context)
        
        if not_subscribed:
            keyboard = await get_subscription_keyboard(not_subscribed)
            await update.message.reply_text(
                "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
                "📢 Barcha kanallarga obuna bo'lgandan keyin 'Obunani tekshirish' tugmasini bosing.",
                reply_markup=keyboard
            )
            return SUBSCRIPTION
        
        # User is verified and subscribed - show main menu
        await update.message.reply_text(
            f"👋 Xush kelibsiz, {user.first_name}!\n\n"
            f"✅ Siz allaqachon ro'yxatdan o'tgansiz."
        )
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # ==================== NEW USER REGISTRATION ====================
    # Step 1: Check channel subscription FIRST
    channels = await get_channels()
    
    if not channels:
        # No channels configured - go straight to phone
        await update.message.reply_text(
            "👋 Assalomu alaykum! So'rovnoma botiga xush kelibsiz!\n\n"
            "📝 Ro'yxatdan o'tish uchun telefon raqamingizni yuboring.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return PHONE
    
    # Check subscription status
    not_subscribed = await check_subscriptions(user.id, context)
    
    if not_subscribed:
        keyboard = await get_subscription_keyboard(not_subscribed)
        await update.message.reply_text(
            "👋 Assalomu alaykum! So'rovnoma botiga xush kelibsiz!\n\n"
            "📢 Botdan foydalanish uchun avval quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
            "✅ Barcha kanallarga obuna bo'lgandan keyin 'Obunani tekshirish' tugmasini bosing.",
            reply_markup=keyboard
        )
        return SUBSCRIPTION
    
    # User is subscribed but not registered - ask for phone
    await update.message.reply_text(
        "👋 Assalomu alaykum! So'rovnoma botiga xush kelibsiz!\n\n"
        "✅ Kanallarimizga obuna uchun rahmat!\n\n"
        "📝 Endi ro'yxatdan o'tish uchun telefon raqamingizni yuboring.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return PHONE


async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number - Senior level with validation"""
    user = update.effective_user
    
    # Check if contact was sent
    if not update.message.contact:
        await update.message.reply_text(
            "❌ Iltimos, telefon raqamingizni yuborish uchun tugmani bosing!\n\n"
            "⚠️ Raqamni qo'lda kiritish mumkin emas.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
                resize_keyboard=True
            )
        )
        return PHONE
    
    contact = update.message.contact
    phone = contact.phone_number
    
    # Validate that the contact belongs to the user
    if contact.user_id != user.id:
        await update.message.reply_text(
            "❌ Iltimos, o'zingizning telefon raqamingizni yuboring!\n\n"
            "⚠️ Boshqa odamning raqamini yuborib bo'lmaydi.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
                resize_keyboard=True
            )
        )
        return PHONE
    
    # Check if phone number already exists
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow(
            'SELECT user_id FROM users WHERE phone_number = $1 AND user_id != $2',
            phone, user.id
        )
        
        if existing:
            await update.message.reply_text(
                "❌ Bu telefon raqam allaqachon ro'yxatdan o'tgan!\n\n"
                "Agar bu sizning raqamingiz bo'lsa, @support ga murojaat qiling.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
    
    # Save user to database (not verified yet)
    await create_user(
        user.id,
        user.username or "",
        phone,
        user.first_name or "",
        user.last_name or ""
    )
    
    # Log fraud detection
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO fraud_detection (user_id, action_type, details)
            VALUES ($1, 'PHONE_REGISTERED', $2::jsonb)
        ''', user.id, f'{{"phone": "{phone}", "username": "{user.username or "none"}"}}')
    
    # Generate captcha
    question, answer = generate_captcha()
    await save_captcha(user.id, answer)
    
    await update.message.reply_text(
        f"✅ Telefon raqam qabul qilindi: {phone}\n\n"
        f"🤖 Endi siz robot emasligingizni tasdiqlang:\n\n"
        f"❓ {question}\n\n"
        f"💡 Javobni faqat raqam bilan yozing (misol: 42)",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return CAPTCHA


async def captcha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle captcha verification - Senior level with security"""
    user = update.effective_user
    user_answer = update.message.text.strip()
    
    # Validate input
    if not user_answer.isdigit() and not (user_answer.startswith('-') and user_answer[1:].isdigit()):
        await update.message.reply_text(
            "❌ Iltimos, faqat raqam kiriting!\n\n"
            "💡 Misol: 42 yoki -5\n\n"
            "Qaytadan urinib ko'ring:"
        )
        return CAPTCHA
    
    # Verify captcha
    is_correct, attempts = await verify_captcha(user.id, user_answer)
    
    if is_correct:
        # Mark user as verified
        await verify_user(user.id)
        
        # Log successful verification
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO fraud_detection (user_id, action_type, suspicious_score, details)
                VALUES ($1, 'CAPTCHA_PASSED', 0, $2::jsonb)
            ''', user.id, f'{{"attempts": {attempts}}}')
        
        # Double check subscriptions before allowing access
        not_subscribed = await check_subscriptions(user.id, context)
        
        if not_subscribed:
            keyboard = await get_subscription_keyboard(not_subscribed)
            await update.message.reply_text(
                "✅ Tasdiqlash muvaffaqiyatli!\n\n"
                "⚠️ Lekin botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:",
                reply_markup=keyboard
            )
            return SUBSCRIPTION
        
        # Success - show welcome message
        await update.message.reply_text(
            "🎉 Tabriklaymiz! Ro'yxatdan o'tish muvaffaqiyatli yakunlandi!\n\n"
            "✅ Telefon raqam tasdiqlandi\n"
            "✅ Robot emasligingiz tasdiqlandi\n"
            "✅ Kanallarimizga obuna bo'lgansiz\n\n"
            "Endi botdan to'liq foydalanishingiz mumkin!"
        )
        
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Failed attempt
    if attempts >= 3:
        # Log suspicious activity
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO fraud_detection (user_id, action_type, suspicious_score, details)
                VALUES ($1, 'CAPTCHA_FAILED_MAX', 80, $2::jsonb)
            ''', user.id, f'{{"attempts": {attempts}, "answer": "{user_answer}"}}')
        
        # Delete captcha session
        async with db_pool.acquire() as conn:
            await conn.execute('DELETE FROM captcha_sessions WHERE user_id = $1', user.id)
        
        await update.message.reply_text(
            "❌ Siz 3 marta noto'g'ri javob berdingiz.\n\n"
            "🔒 Xavfsizlik sabablari uchun ro'yxatdan o'tish bekor qilindi.\n\n"
            "🔄 Qaytadan urinish uchun /start buyrug'ini yuboring."
        )
        return ConversationHandler.END
    
    # Log failed attempt
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO fraud_detection (user_id, action_type, suspicious_score, details)
            VALUES ($1, 'CAPTCHA_FAILED', 20, $2::jsonb)
        ''', user.id, f'{{"attempts": {attempts}, "answer": "{user_answer}"}}')
    
    # Generate new captcha for retry
    question, answer = generate_captcha()
    await save_captcha(user.id, answer)
    
    await update.message.reply_text(
        f"❌ Noto'g'ri javob! (Urinish: {attempts}/3)\n\n"
        f"💡 Yangi savol:\n"
        f"❓ {question}\n\n"
        f"Iltimos, qaytadan urinib ko'ring:"
    )
    
    return CAPTCHA


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check subscription callback - Senior level with proper flow"""
    query = update.callback_query
    await query.answer("Tekshirilmoqda...")
    
    user_id = query.from_user.id
    user = query.from_user
    
    # Check subscriptions
    not_subscribed = await check_subscriptions(user_id, context)
    
    if not_subscribed:
        keyboard = await get_subscription_keyboard(not_subscribed)
        channel_names = ", ".join([ch['channel_title'] for ch in not_subscribed])
        
        await query.edit_message_text(
            f"⚠️ Siz hali barcha kanallarga obuna bo'lmadingiz!\n\n"
            f"❌ Obuna bo'lmagan kanallar:\n{channel_names}\n\n"
            f"📢 Iltimos, barcha kanallarga obuna bo'ling va qaytadan tekshiring:",
            reply_markup=keyboard
        )
        return SUBSCRIPTION
    
    # All channels subscribed
    db_user = await get_user(user_id)
    
    # If user is already verified, just show menu
    if db_user and db_user['is_verified']:
        await query.edit_message_text("✅ Barcha obunalar tasdiqlandi!")
        await show_main_menu(query, context)
        return ConversationHandler.END
    
    # User subscribed but not registered yet - ask for phone
    await query.edit_message_text(
        "✅ Barcha obunalar tasdiqlandi!\n\n"
        "📝 Endi ro'yxatdan o'tish uchun telefon raqamingizni yuboring."
    )
    
    await context.bot.send_message(
        chat_id=user_id,
        text="📱 Telefon raqamingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    
    return PHONE


async def show_main_menu(source, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu. Accepts either an Update or a CallbackQuery object as `source`."""
    # Build keyboard
    keyboard = [
        [InlineKeyboardButton("📊 Faol so'rovnomalar", callback_data="view_polls")],
        [InlineKeyboardButton("📈 Mening ovozlarim", callback_data="my_votes")],
        [InlineKeyboardButton("ℹ️ Yordam", callback_data="help")]
    ]

    # Determine user_id and send the message depending on the type of `source`
    user_id = None
    try:
        # If it's an Update
        if hasattr(source, 'effective_user') or hasattr(source, 'message') or hasattr(source, 'callback_query'):
            update = source
            user_id = update.effective_user.id if update.effective_user else (update.message.from_user.id if update.message else None)
            text = "🏠 Asosiy menyu:\n\nKerakli bo'limni tanlang:"

            if user_id in ADMIN_IDS:
                keyboard.insert(0, [InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])

            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            elif hasattr(update, 'callback_query') and update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                # Fallback: try to reply via context.bot to the user
                if user_id:
                    await context.bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        # If `source` is a CallbackQuery object (passed directly), handle it here
        try:
            query = source
            user_id = query.from_user.id
            text = "🏠 Asosiy menyu:\n\nKerakli bo'limni tanlang:"
            if user_id in ADMIN_IDS:
                keyboard.insert(0, [InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
            if query.message:
                await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await context.bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            # give up silently; callers will handle further flow
            return


# ================= ADMIN PANEL =================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Sizda admin huquqi yo'q!", show_alert=True)
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ So'rovnoma yaratish", callback_data="create_poll")],
        [InlineKeyboardButton("📋 So'rovnomalar ro'yxati", callback_data="admin_polls")],
        [InlineKeyboardButton("📢 Kanallar boshqaruvi", callback_data="manage_channels")],
        [InlineKeyboardButton("👥 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        "👑 Admin Panel\n\nKerakli bo'limni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage channels"""
    query = update.callback_query
    await query.answer()
    
    channels = await get_channels()
    
    text = "📢 Kanallar boshqaruvi\n\n"
    keyboard = []
    
    if channels:
        text += "Ro'yxatdagi kanallar:\n\n"
        for channel in channels:
            required_status = "✅ Majburiy" if channel.get('is_required', True) else "⭐️ Ixtiyoriy"
            text += f"• {channel['channel_title']} ({required_status})\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {channel['channel_title']}", 
                    callback_data=f"remove_channel_{channel['id']}"
                )
            ])
        text += "\n"
        
        # Show advertising channel
        text += f"⭐️ Reklama kanali: {ADVERTISING_CHANNEL_NAME}\n"
        text += "(Ushbu kanal foydalanuvchilarga ko'rsatiladi, lekin a'zolik tekshirilmaydi)\n\n"
    
    text += "Yangi kanal qo'shish uchun 'Kanal qo'shish' tugmasini bosing."
    
    keyboard.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_channel")])
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding channel"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📢 Kanal qo'shish\n\n"
        "Kanalni botga admin qilib qo'shing, keyin kanal username yoki ID sini yuboring.\n"
        "Misol: @mychannel yoki -1001234567890\n\n"
        "Bekor qilish uchun /cancel"
    )
    
    return CHANNEL_ADD


async def add_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle channel addition"""
    text = update.message.text.strip()
    
    try:
        # Try to get chat info
        chat = await context.bot.get_chat(text)
        
        await add_channel(chat.id, chat.username or "", chat.title or "")
        
        await update.message.reply_text(
            f"✅ Kanal muvaffaqiyatli qo'shildi!\n\n"
            f"📢 {chat.title}\n"
            f"🆔 {chat.id}"
        )
        
        await show_main_menu(update, context)
        return MENU
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Xatolik yuz berdi!\n\n"
            f"Iltimos, botni kanalga admin qilib qo'shganingizni tekshiring.\n"
            f"Xatolik: {str(e)}"
        )
        return CHANNEL_ADD


async def remove_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove channel callback"""
    query = update.callback_query
    await query.answer()
    
    channel_id = int(query.data.split('_')[-1])
    
    await remove_channel(channel_id)
    await query.answer("✅ Kanal o'chirildi!", show_alert=True)
    
    await manage_channels(update, context)


# ================= POLL CREATION =================

async def create_poll_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start poll creation"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📝 So'rovnoma yaratish\n\n"
        "So'rovnoma sarlavhasini kiriting:\n"
        "(Misol: Eng faol xodim)"
    )
    
    return POLL_TITLE


async def poll_title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle poll title"""
    context.user_data['poll_title'] = update.message.text
    
    await update.message.reply_text(
        "✅ Sarlavha qabul qilindi!\n\n"
        "Endi so'rovnoma tavsifini kiriting:"
    )
    
    return POLL_DESCRIPTION


async def poll_description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle poll description"""
    context.user_data['poll_description'] = update.message.text
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ O'tkazib yuborish", callback_data="skip_image")]
    ])
    
    await update.message.reply_text(
        "✅ Tavsif qabul qilindi!\n\n"
        "So'rovnoma uchun rasm yuboring (ixtiyoriy):",
        reply_markup=keyboard
    )
    
    return POLL_IMAGE


async def poll_image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle poll image"""
    if update.message.photo:
        context.user_data['poll_image'] = update.message.photo[-1].file_id
    
    await update.message.reply_text(
        "✅ Rasm qabul qilindi!\n\n"
        "Endi nomzodlar ro'yxatini kiriting (har qatorga bitta nom):\n\n"
        "Misol:\n"
        "Alisher Navoiy\n"
        "Mirzo Ulug'bek\n"
        "Zahiriddin Muhammad Bobur"
    )
    
    return POLL_CANDIDATES


async def skip_image_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip image upload"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✅ Rasm o'tkazib yuborildi!\n\n"
        "Endi nomzodlar ro'yxatini kiriting (har qatorga bitta nom):\n\n"
        "Misol:\n"
        "Alisher Navoiy\n"
        "Mirzo Ulug'bek\n"
        "Zahiriddin Muhammad Bobur"
    )
    
    return POLL_CANDIDATES


async def poll_candidates_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle poll candidates"""
    candidates = [line.strip() for line in update.message.text.split('\n') if line.strip()]
    
    if len(candidates) < 2:
        await update.message.reply_text(
            "❌ Kamida 2 ta nomzod kiritishingiz kerak!\n"
            "Iltimos, qaytadan kiriting:"
        )
        return POLL_CANDIDATES
    
    context.user_data['poll_candidates'] = candidates
    
    # Show confirmation
    text = "📊 So'rovnoma ma'lumotlari:\n\n"
    text += f"📝 Sarlavha: {context.user_data['poll_title']}\n"
    text += f"📄 Tavsif: {context.user_data['poll_description']}\n"
    has_image_text = "Ha" if context.user_data.get('poll_image') else "Yo'q"
    text += f"🖼️ Rasm: {has_image_text}\n"
    text += f"👥 Nomzodlar soni: {len(candidates)}\n\n"
    text += "Nomzodlar:\n"
    for i, candidate in enumerate(candidates, 1):
        text += f"{i}. {candidate}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm_poll")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_poll")]
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard)
    
    return POLL_CONFIRM


async def confirm_poll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and create poll"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = query.from_user
    
    # Ensure user exists in database (important for admins who didn't register)
    async with db_pool.acquire() as conn:
        # Check if user exists
        existing_user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
        
        if not existing_user:
            # Create user record for admin
            await conn.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, is_verified)
                VALUES ($1, $2, $3, $4, TRUE)
                ON CONFLICT (user_id) DO NOTHING
            ''', user_id, user.username or '', user.first_name or '', user.last_name or '')
        
        # Now create the poll
        poll_id = await conn.fetchval('''
            INSERT INTO polls (title, description, image_file_id, created_by)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        ''', 
            context.user_data['poll_title'],
            context.user_data['poll_description'],
            context.user_data.get('poll_image'),
            user_id
        )
        
        # Add candidates
        for candidate in context.user_data['poll_candidates']:
            await conn.execute('''
                INSERT INTO poll_candidates (poll_id, candidate_name)
                VALUES ($1, $2)
            ''', poll_id, candidate)
    
    # Store poll_id for sharing
    context.user_data['created_poll_id'] = poll_id
    
    # Keyboard with share option
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Kanallarga ulashish", callback_data=f"share_poll_{poll_id}")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await query.edit_message_text(
        f"✅ So'rovnoma muvaffaqiyatli yaratildi!\n\n"
        f"So'rovnoma ID: {poll_id}\n\n"
        f"Foydalanuvchilar endi ovoz berishlari mumkin.\n\n"
        f"So'rovnomani kanallarga ulashishni xohlaysizmi?",
        reply_markup=keyboard
    )
    
    return MENU


async def cancel_poll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel poll creation"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text("❌ So'rovnoma yaratish bekor qilindi.")
    await show_main_menu(query, context)
    return ConversationHandler.END


# ================= POLL VOTING =================

async def view_polls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View active polls"""
    query = update.callback_query
    await query.answer()
    
    # Obunani tekshirish
    user_id = query.from_user.id
    not_subscribed = await check_subscriptions(user_id, context)
    
    if not_subscribed:
        keyboard = await get_subscription_keyboard(not_subscribed)
        await query.edit_message_text(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
            "Barcha kanallarga obuna bo'lgandan keyin 'Obunani tekshirish' tugmasini bosing.",
            reply_markup=keyboard
        )
        return
    
    async with db_pool.acquire() as conn:
        polls = await conn.fetch('''
            SELECT * FROM polls 
            WHERE is_active = TRUE 
            ORDER BY created_at DESC
        ''')
    
    if not polls:
        await query.edit_message_text(
            "📊 Hozirda faol so'rovnomalar yo'q.\n\n"
            "🔙 Orqaga qaytish uchun:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")
            ]])
        )
        return
    
    keyboard = []
    for poll in polls:
        keyboard.append([
            InlineKeyboardButton(
                f"📊 {poll['title']}", 
                callback_data=f"vote_poll_{poll['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        "📊 Faol so'rovnomalar:\n\nOveriz bermoqchi bo'lgan so'rovnomani tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def vote_poll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show poll for voting"""
    query = update.callback_query
    await query.answer()
    
    poll_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    # Obunani tekshirish
    not_subscribed = await check_subscriptions(user_id, context)
    
    if not_subscribed:
        keyboard = await get_subscription_keyboard(not_subscribed)
        await query.edit_message_text(
            "⚠️ Ovoz berish uchun quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
            "Barcha kanallarga obuna bo'lgandan keyin 'Obunani tekshirish' tugmasini bosing.",
            reply_markup=keyboard
        )
        return
    
    async with db_pool.acquire() as conn:
        # Get poll info
        poll = await conn.fetchrow('SELECT * FROM polls WHERE id = $1', poll_id)
        
        if not poll:
            await query.answer("❌ So'rovnoma topilmadi!", show_alert=True)
            return
        
        # Check if user already voted
        existing_vote = await conn.fetchrow('''
            SELECT * FROM votes WHERE poll_id = $1 AND user_id = $2
        ''', poll_id, user_id)
        
        # Get candidates
        candidates = await conn.fetch('''
            SELECT * FROM poll_candidates WHERE poll_id = $1 ORDER BY id
        ''', poll_id)
    
    text = f"📊 {poll['title']}\n\n"
    text += f"📄 {poll['description']}\n\n"
    
    if existing_vote:
        text += "✅ Siz allaqachon ovoz bergansiz!\n\n"
        text += "📈 Natijalarni ko'rish uchun:\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Natijalarni ko'rish", callback_data=f"poll_results_{poll_id}")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="view_polls")]
        ])
    else:
        text += "👥 Nomzodlar:\n\n"
        text += "Ovoz berish uchun nomzodni tanlang:"
        
        keyboard = []
        for candidate in candidates:
            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {candidate['candidate_name']}", 
                    callback_data=f"cast_vote_{poll_id}_{candidate['id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="view_polls")])
        keyboard = InlineKeyboardMarkup(keyboard)
    
    # Send image if exists
    if poll['image_file_id'] and not existing_vote:
        try:
            await query.message.reply_photo(
                photo=poll['image_file_id'],
                caption=text,
                reply_markup=keyboard
            )
            await query.message.delete()
        except:
            await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await query.edit_message_text(text, reply_markup=keyboard)


async def cast_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cast vote"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    poll_id = int(parts[2])
    candidate_id = int(parts[3])
    user_id = query.from_user.id
    
    async with db_pool.acquire() as conn:
        # Check if already voted
        existing = await conn.fetchrow('''
            SELECT * FROM votes WHERE poll_id = $1 AND user_id = $2
        ''', poll_id, user_id)
        
        if existing:
            await query.answer("❌ Siz allaqachon ovoz bergansiz!", show_alert=True)
            return
        
        # Cast vote
        await conn.execute('''
            INSERT INTO votes (poll_id, user_id, candidate_id)
            VALUES ($1, $2, $3)
        ''', poll_id, user_id, candidate_id)
        
        # Update candidate votes
        await conn.execute('''
            UPDATE poll_candidates SET votes = votes + 1 WHERE id = $1
        ''', candidate_id)
        
        # Update total votes
        await conn.execute('''
            UPDATE polls SET total_votes = total_votes + 1 WHERE id = $1
        ''', poll_id)
        
        candidate = await conn.fetchrow('''
            SELECT candidate_name FROM poll_candidates WHERE id = $1
        ''', candidate_id)
    
    # Notify the user and send results
    await query.answer("✅ Ovozingiz qabul qilindi!", show_alert=True)

    # Prepare keyboard for results
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Natijalarni ko'rish", callback_data=f"poll_results_{poll_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="view_polls")]
    ])

    # Try to edit the original message; if it fails because there's no text, send a reply instead
    try:
        if query.message and getattr(query.message, 'text', None):
            await query.edit_message_text(
                f"✅ Ovozingiz muvaffaqiyatli qabul qilindi!\n\n"
                f"Siz ovoz berdingiz: {candidate['candidate_name']}",
                reply_markup=keyboard
            )
        else:
            # If original message has no editable text (e.g., it's a photo), reply in chat
            if query.message:
                await query.message.reply_text(
                    f"✅ Ovozingiz muvaffaqiyatli qabul qilindi!\n\nSiz ovoz berdingiz: {candidate['candidate_name']}",
                    reply_markup=keyboard
                )
    except Exception:
        # As a fallback, send a direct message to the user
        try:
            await context.bot.send_message(query.from_user.id,
                f"✅ Ovozingiz muvaffaqiyatli qabul qilindi!\n\nSiz ovoz berdingiz: {candidate['candidate_name']}")
        except Exception:
            pass

    # Send a thank-you message (private) and then send the poll results (chart) to the user
    try:
        await context.bot.send_message(user_id, "Rahmat! Sizning ovozingiz uchun tashakkur.")
    except Exception:
        # ignore if cannot send private message
        pass

    # Trigger sending poll results to this user by calling the same logic as poll_results_callback
    # We'll call a helper function to generate and send the chart privately
    try:
        await send_poll_results_to_user(poll_id, user_id, context)
    except Exception:
        # If sending results fails, do nothing
        pass


async def poll_results_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show poll results with bar chart"""
    query = update.callback_query
    await query.answer()
    
    poll_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    # Obunani tekshirish
    not_subscribed = await check_subscriptions(user_id, context)
    
    if not_subscribed:
        keyboard = await get_subscription_keyboard(not_subscribed)
        await query.edit_message_text(
            "⚠️ Natijalarni ko'rish uchun quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
            "Barcha kanallarga obuna bo'lgandan keyin 'Obunani tekshirish' tugmasini bosing.",
            reply_markup=keyboard
        )
        return
    
    async with db_pool.acquire() as conn:
        poll = await conn.fetchrow('SELECT * FROM polls WHERE id = $1', poll_id)
        candidates = await conn.fetch('''
            SELECT * FROM poll_candidates WHERE poll_id = $1 ORDER BY votes DESC
        ''', poll_id)
    
    if not candidates:
        await query.answer("❌ Ma'lumot topilmadi!", show_alert=True)
        return
    
    # Create bar chart (vertikal)
    labels = [c['candidate_name'] for c in candidates]
    votes = [c['votes'] for c in candidates]
    
    # Ranglar
    colors = plt.cm.Set3(range(len(labels)))
    
    # Figure yaratish
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Vertikal bar chart
    bars = ax.bar(range(len(labels)), votes, color=colors, edgecolor='black', linewidth=1.5)
    
    # Har bir ustunning tepasida qiymatni ko'rsatish
    for i, (bar, vote) in enumerate(zip(bars, votes)):
        height = bar.get_height()
        percentage = (vote / poll['total_votes'] * 100) if poll['total_votes'] > 0 else 0
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{vote}\n({percentage:.1f}%)',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    # X o'qida nomzod nomlari
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=10)
    
    # Y o'qi
    ax.set_ylabel('Ovozlar soni', fontsize=12, fontweight='bold')
    ax.set_xlabel('Nomzodlar', fontsize=12, fontweight='bold')
    
    # Sarlavha
    ax.set_title(f"{poll['title']}\nJami ovozlar: {poll['total_votes']}", 
                 fontsize=14, fontweight='bold', pad=20)
    
    # Grid qo'shish
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # Layout sozlash
    plt.tight_layout()
    
    # Save to BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    # Prepare text
    text = f"📊 {poll['title']}\n\n"
    text += f"📈 So'rovnoma natijalari:\n"
    text += f"🔥 Jami ovozlar: {poll['total_votes']}\n\n"
    
    for i, candidate in enumerate(candidates, 1):
        percentage = (candidate['votes'] / poll['total_votes'] * 100) if poll['total_votes'] > 0 else 0
        text += f"{i}. {candidate['candidate_name']}: {candidate['votes']} ovoz ({percentage:.1f}%)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Orqaga", callback_data="view_polls")]
    ])
    
    # Send chart
    try:
        await query.message.reply_photo(
            photo=buf,
            caption=text,
            reply_markup=keyboard
        )
        await query.message.delete()
    except Exception as e:
        await query.edit_message_text(
            text + f"\n\n❌ Grafik yuklashda xatolik: {str(e)}",
            reply_markup=keyboard
        )


# ================= POLL SHARING =================

async def share_poll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start poll sharing process"""
    query = update.callback_query
    await query.answer()
    
    poll_id = int(query.data.split('_')[-1])
    
    # Get all channels
    channels = await get_channels()
    
    if not channels:
        await query.edit_message_text(
            "❌ Ulashish uchun kanallar topilmadi!\n\n"
            "Avval kanallar qo'shing.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")
            ]])
        )
        return
    
    # Create keyboard with channels
    keyboard = []
    for channel in channels:
        keyboard.append([
            InlineKeyboardButton(
                f"📢 {channel['channel_title']}",
                callback_data=f"share_to_channel_{poll_id}_{channel['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("📤 Barchaga ulashish", callback_data=f"share_to_all_{poll_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Bekor qilish", callback_data="admin_panel")])
    
    await query.edit_message_text(
        "📤 So'rovnomani qaysi kanalga ulashmoqchisiz?\n\n"
        "Bitta kanalni tanlang yoki barchaga ulashing:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def share_to_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Share poll to specific channel"""
    query = update.callback_query
    await query.answer("Ulashilmoqda...")
    
    parts = query.data.split('_')
    poll_id = int(parts[3])
    channel_db_id = int(parts[4])
    
    # Get channel info
    async with db_pool.acquire() as conn:
        channel = await conn.fetchrow('SELECT * FROM channels WHERE id = $1', channel_db_id)
    
    if not channel:
        await query.answer("❌ Kanal topilmadi!", show_alert=True)
        return
    
    # Share poll
    success = await send_poll_to_channel(poll_id, channel, query.from_user.id, context)
    
    if success:
        await query.answer("✅ So'rovnoma muvaffaqiyatli ulashildi!", show_alert=True)
        await query.edit_message_text(
            f"✅ So'rovnoma '{channel['channel_title']}' kanaliga ulashildi!\n\n"
            "Yana ulashishni xohlaysizmi?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Boshqa kanalga ulashish", callback_data=f"share_poll_{poll_id}")],
                [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
            ])
        )
    else:
        await query.answer("❌ Xatolik yuz berdi!", show_alert=True)


async def share_to_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Share poll to all channels"""
    query = update.callback_query
    await query.answer("Barcha kanallarga ulashilmoqda...")
    
    poll_id = int(query.data.split('_')[-1])
    
    # Get all channels
    channels = await get_channels()
    
    success_count = 0
    failed_count = 0
    
    for channel in channels:
        success = await send_poll_to_channel(poll_id, channel, query.from_user.id, context)
        if success:
            success_count += 1
        else:
            failed_count += 1
        
        # Small delay to avoid rate limits
        await asyncio.sleep(0.5)
    
    await query.edit_message_text(
        f"📤 Ulashish tugallandi!\n\n"
        f"✅ Muvaffaqiyatli: {success_count}\n"
        f"❌ Xatolik: {failed_count}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")
        ]])
    )


async def send_poll_to_channel(poll_id: int, channel: dict, shared_by: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Send poll post to a channel"""
    try:
        async with db_pool.acquire() as conn:
            # Get poll info
            poll = await conn.fetchrow('SELECT * FROM polls WHERE id = $1', poll_id)
            
            # Get candidates
            candidates = await conn.fetch('''
                SELECT * FROM poll_candidates WHERE poll_id = $1 ORDER BY id
            ''', poll_id)
        
        if not poll or not candidates:
            return False
        
        # Create poll message text
        text = f"📊 {poll['title']}\n\n"
        text += f"📄 {poll['description']}\n\n"
        text += f"👥 Nomzodlar:\n"
        for i, candidate in enumerate(candidates, 1):
            text += f"{i}. {candidate['candidate_name']}\n"
        text += f"\n🗳️ Ovoz berish uchun pastdagi tugmalardan foydalaning!\n"
        text += f"\n⭐️ {ADVERTISING_CHANNEL_NAME}: {ADVERTISING_CHANNEL}"
        
        # Create inline keyboard for voting
        keyboard = []
        for candidate in candidates:
            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {candidate['candidate_name']}",
                    callback_data=f"vote_from_channel_{poll_id}_{candidate['id']}"
                )
            ])
        
        # Add results button
        keyboard.append([
            InlineKeyboardButton("📈 Natijalarni ko'rish", callback_data=f"poll_results_{poll_id}")
        ])
        
        # Add bot link
        bot_info = await context.bot.get_me()
        keyboard.append([
            InlineKeyboardButton("🤖 Botga o'tish", url=f"https://t.me/{bot_info.username}")
        ])
        
        # Send to channel
        if poll['image_file_id']:
            message = await context.bot.send_photo(
                chat_id=channel['channel_id'],
                photo=poll['image_file_id'],
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            message = await context.bot.send_message(
                chat_id=channel['channel_id'],
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        # Save share record
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO poll_shares (poll_id, channel_id, message_id, shared_by)
                VALUES ($1, $2, $3, $4)
            ''', poll_id, channel['channel_id'], message.message_id, shared_by)
        
        return True
        
    except Exception as e:
        print(f"Error sharing poll to channel: {e}")
        return False


async def vote_from_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle vote from channel post"""
    query = update.callback_query
    
    parts = query.data.split('_')
    poll_id = int(parts[3])
    candidate_id = int(parts[4])
    user_id = query.from_user.id
    
    # Check if user is registered and verified
    user = await get_user(user_id)
    
    if not user or not user['is_verified']:
        await query.answer(
            "⚠️ Ovoz berish uchun avval botda ro'yxatdan o'ting!",
            show_alert=True
        )
        
        # Send private message with start link
        bot_info = await context.bot.get_me()
        try:
            await context.bot.send_message(
                user_id,
                f"👋 Assalomu alaykum!\n\n"
                f"So'rovnomada ovoz berish uchun avval ro'yxatdan o'tishingiz kerak.\n\n"
                f"Ro'yxatdan o'tish uchun /start buyrug'ini yuboring.",
            )
        except:
            pass
        
        return
    
    # Check subscriptions
    not_subscribed = await check_subscriptions(user_id, context)
    
    if not_subscribed:
        channel_names = ", ".join([ch['channel_title'] for ch in not_subscribed])
        await query.answer(
            f"⚠️ Ovoz berish uchun quyidagi kanallarga obuna bo'ling: {channel_names}",
            show_alert=True
        )
        return
    
    # Check if already voted
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow('''
            SELECT * FROM votes WHERE poll_id = $1 AND user_id = $2
        ''', poll_id, user_id)
        
        if existing:
            await query.answer("✅ Siz allaqachon ovoz bergansiz!", show_alert=True)
            return
        
        # Cast vote
        await conn.execute('''
            INSERT INTO votes (poll_id, user_id, candidate_id)
            VALUES ($1, $2, $3)
        ''', poll_id, user_id, candidate_id)
        
        # Update candidate votes
        await conn.execute('''
            UPDATE poll_candidates SET votes = votes + 1 WHERE id = $1
        ''', candidate_id)
        
        # Update total votes
        await conn.execute('''
            UPDATE polls SET total_votes = total_votes + 1 WHERE id = $1
        ''', poll_id)
        
        candidate = await conn.fetchrow('''
            SELECT candidate_name FROM poll_candidates WHERE id = $1
        ''', candidate_id)
    
    await query.answer(f"✅ Ovozingiz qabul qilindi: {candidate['candidate_name']}", show_alert=True)
    
    # Send results privately
    try:
        await send_poll_results_to_user(poll_id, user_id, context)
    except:
        pass


# ================= ADDITIONAL HANDLERS =================


async def send_poll_results_to_user(poll_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Generate poll results chart and send it privately to the given user_id."""
    async with db_pool.acquire() as conn:
        poll = await conn.fetchrow('SELECT * FROM polls WHERE id = $1', poll_id)
        candidates = await conn.fetch('''
            SELECT * FROM poll_candidates WHERE poll_id = $1 ORDER BY votes DESC
        ''', poll_id)

    if not poll or not candidates:
        return

    labels = [c['candidate_name'] for c in candidates]
    votes = [c['votes'] for c in candidates]

    # Ranglar
    colors = plt.cm.Set3(range(len(labels)))
    
    # Figure yaratish
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Vertikal bar chart
    bars = ax.bar(range(len(labels)), votes, color=colors, edgecolor='black', linewidth=1.5)
    
    # Har bir ustunning tepasida qiymatni ko'rsatish
    for i, (bar, vote) in enumerate(zip(bars, votes)):
        height = bar.get_height()
        percentage = (vote / poll['total_votes'] * 100) if poll['total_votes'] > 0 else 0
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{vote}\n({percentage:.1f}%)',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    # X o'qida nomzod nomlari
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=10)
    
    # Y o'qi
    ax.set_ylabel('Ovozlar soni', fontsize=12, fontweight='bold')
    ax.set_xlabel('Nomzodlar', fontsize=12, fontweight='bold')
    
    # Sarlavha
    ax.set_title(f"{poll['title']}\nJami ovozlar: {poll['total_votes']}", 
                 fontsize=14, fontweight='bold', pad=20)
    
    # Grid qo'shish
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # Layout sozlash
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()

    text = f"📊 {poll['title']}\n\n"
    text += f"📈 So'rovnoma natijalari:\n"
    text += f"🔥 Jami ovozlar: {poll['total_votes']}\n\n"
    for i, candidate in enumerate(candidates, 1):
        percentage = (candidate['votes'] / poll['total_votes'] * 100) if poll['total_votes'] > 0 else 0
        text += f"{i}. {candidate['candidate_name']}: {candidate['votes']} ovoz ({percentage:.1f}%)\n"

    try:
        await context.bot.send_photo(chat_id=user_id, photo=buf, caption=text)
    except Exception:
        # Ignore errors sending private message (user may block bot)
        pass


async def my_votes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's votes"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Obunani tekshirish
    not_subscribed = await check_subscriptions(user_id, context)
    
    if not_subscribed:
        keyboard = await get_subscription_keyboard(not_subscribed)
        await query.edit_message_text(
            "⚠️ Ovozlaringizni ko'rish uchun quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
            "Barcha kanallarga obuna bo'lgandan keyin 'Obunani tekshirish' tugmasini bosing.",
            reply_markup=keyboard
        )
        return
    
    async with db_pool.acquire() as conn:
        votes = await conn.fetch('''
            SELECT v.voted_at, p.title, pc.candidate_name
            FROM votes v
            JOIN polls p ON v.poll_id = p.id
            JOIN poll_candidates pc ON v.candidate_id = pc.id
            WHERE v.user_id = $1
            ORDER BY v.voted_at DESC
        ''', user_id)
    
    if not votes:
        text = "📊 Siz hali hech qanday so'rovnomada ovoz bermadingiz."
    else:
        text = "📊 Sizning ovozlaringiz:\n\n"
        for vote in votes:
            text += f"• {vote['title']}\n"
            text += f"  👤 {vote['candidate_name']}\n"
            text += f"  🕐 {vote['voted_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin statistics"""
    query = update.callback_query
    await query.answer()
    
    async with db_pool.acquire() as conn:
        total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
        verified_users = await conn.fetchval('SELECT COUNT(*) FROM users WHERE is_verified = TRUE')
        total_polls = await conn.fetchval('SELECT COUNT(*) FROM polls')
        active_polls = await conn.fetchval('SELECT COUNT(*) FROM polls WHERE is_active = TRUE')
        total_votes = await conn.fetchval('SELECT COUNT(*) FROM votes')
        total_channels = await conn.fetchval('SELECT COUNT(*) FROM channels')
    
    text = "📊 Statistika:\n\n"
    text += f"👥 Jami foydalanuvchilar: {total_users}\n"
    text += f"✅ Tasdiqlangan: {verified_users}\n"
    text += f"📊 Jami so'rovnomalar: {total_polls}\n"
    text += f"🟢 Faol so'rovnomalar: {active_polls}\n"
    text += f"🗳️ Jami ovozlar: {total_votes}\n"
    text += f"📢 Kanallar soni: {total_channels}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)


async def admin_polls_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin polls list"""
    query = update.callback_query
    await query.answer()
    
    async with db_pool.acquire() as conn:
        polls = await conn.fetch('''
            SELECT * FROM polls ORDER BY created_at DESC LIMIT 10
        ''')
    
    text = "📋 So'rovnomalar ro'yxati:\n\n"
    keyboard = []
    
    for poll in polls:
        status = "🟢" if poll['is_active'] else "🔴"
        text += f"{status} {poll['title']} (ID: {poll['id']})\n"
        text += f"   📊 {poll['total_votes']} ovoz\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"📊 {poll['title'][:30]}", 
                callback_data=f"admin_poll_{poll['id']}"
            ),
            InlineKeyboardButton(
                "📤", 
                callback_data=f"share_poll_{poll['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_poll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show details for a specific admin poll (from admin_polls_list)"""
    query = update.callback_query
    await query.answer()

    try:
        poll_id = int(query.data.split('_')[-1])
    except Exception:
        await query.answer("❌ Not valid poll id", show_alert=True)
        return

    async with db_pool.acquire() as conn:
        poll = await conn.fetchrow('SELECT * FROM polls WHERE id = $1', poll_id)
        candidates = await conn.fetch('SELECT * FROM poll_candidates WHERE poll_id = $1 ORDER BY votes DESC', poll_id)

    if not poll:
        await query.edit_message_text("❌ So'rovnoma topilmadi.")
        return

    text = f"📋 So'rovnoma: {poll['title']}\n\n"
    text += f"📄 Tavsif: {poll['description'] or '-'}\n"
    active_status = 'Ha' if poll['is_active'] else "Yo'q"
    text += f"🟢 Faol: {active_status}\n"
    text += f"🗳️ Jami ovozlar: {poll['total_votes']}\n\n"
    for i, c in enumerate(candidates, 1):
        text += f"{i}. {c['candidate_name']} — {c['votes']} ovoz\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_polls")]
    ])

    await query.edit_message_text(text, reply_markup=keyboard)


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to main menu"""
    query = update.callback_query
    await query.answer()
    
    await show_main_menu(query, context)
    return MENU


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "ℹ️ Yordam:\n\n"
        "Bu bot orqali siz so'rovnomalarda ishtirok etishingiz mumkin.\n\n"
        "Funksiyalar:\n"
        "• 📊 Faol so'rovnomalarni ko'rish\n"
        "• 🗳️ Ovoz berish\n"
        "• 📈 Natijalarni real vaqtda kuzatish\n"
        "• 📱 Telefon orqali ro'yxatdan o'tish\n"
        "• 🤖 Bot emasligingizni tasdiqlash\n\n"
        "Savol va takliflar uchun: @support"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text(
        "❌ Amal bekor qilindi.\n\n"
        "Qaytadan boshlash uchun /start"
    )
    context.user_data.clear()
    return ConversationHandler.END


# ================= MAIN =================

def main():
    """Main function"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Registration conversation handler
    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SUBSCRIPTION: [
                CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'),
                MessageHandler(filters.ALL, lambda u, c: SUBSCRIPTION)  # Stay in subscription state
            ],
            PHONE: [
                MessageHandler(filters.CONTACT, phone_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)  # Handle text messages too
            ],
            CAPTCHA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, captcha_handler)
            ],
            MENU: [
                CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'),
                CallbackQueryHandler(view_polls, pattern='^view_polls$'),
                CallbackQueryHandler(my_votes, pattern='^my_votes$'),
                CallbackQueryHandler(help_command, pattern='^help$'),
                CallbackQueryHandler(admin_panel, pattern='^admin_panel$'),
                CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'),
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_handler)],
        allow_reentry=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    # Poll creation conversation handler
    poll_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_poll_start, pattern='^create_poll$')],
        states={
            POLL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, poll_title_handler)],
            POLL_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, poll_description_handler)],
            POLL_IMAGE: [
                MessageHandler(filters.PHOTO, poll_image_handler),
                CallbackQueryHandler(skip_image_callback, pattern='^skip_image$')
            ],
            POLL_CANDIDATES: [MessageHandler(filters.TEXT & ~filters.COMMAND, poll_candidates_handler)],
            POLL_CONFIRM: [
                CallbackQueryHandler(confirm_poll_callback, pattern='^confirm_poll$'),
                CallbackQueryHandler(cancel_poll_callback, pattern='^cancel_poll$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_handler)],
        allow_reentry=True,
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    # Channel management conversation handler
    channel_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_channel_start, pattern='^add_channel$')],
        states={
            CHANNEL_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel_handler)],
        allow_reentry=True,
        per_message=False,
        per_chat=True,
        per_user=True,
        map_to_parent={
            MENU: MENU,
            ConversationHandler.END: ConversationHandler.END
        }
    )
    
    # Add handlers
    application.add_handler(reg_conv_handler)
    application.add_handler(poll_conv_handler)
    application.add_handler(channel_conv_handler)
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(manage_channels, pattern='^manage_channels$'))
    application.add_handler(CallbackQueryHandler(remove_channel_callback, pattern='^remove_channel_'))
    application.add_handler(CallbackQueryHandler(vote_poll_callback, pattern='^vote_poll_'))
    application.add_handler(CallbackQueryHandler(cast_vote_callback, pattern='^cast_vote_'))
    application.add_handler(CallbackQueryHandler(poll_results_callback, pattern='^poll_results_'))
    application.add_handler(CallbackQueryHandler(admin_poll_callback, pattern='^admin_poll_'))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    application.add_handler(CallbackQueryHandler(admin_polls_list, pattern='^admin_polls$'))
    
    # Poll sharing handlers
    application.add_handler(CallbackQueryHandler(share_poll_callback, pattern='^share_poll_'))
    application.add_handler(CallbackQueryHandler(share_to_channel_callback, pattern='^share_to_channel_'))
    application.add_handler(CallbackQueryHandler(share_to_all_callback, pattern='^share_to_all_'))
    application.add_handler(CallbackQueryHandler(vote_from_channel_callback, pattern='^vote_from_channel_'))
    
    # Global navigation handlers (ensure buttons work regardless of conversation state)
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'))
    application.add_handler(CallbackQueryHandler(view_polls, pattern='^view_polls$'))
    application.add_handler(CallbackQueryHandler(my_votes, pattern='^my_votes$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    
    # Error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log errors caused by updates"""
        print(f"❌ Xatolik: {context.error}")
        
        # Try to inform the user
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.\n"
                    "/start buyrug'i bilan qaytadan boshlang."
                )
            except Exception:
                pass
    
    application.add_error_handler(error_handler)
    
    # Initialize database and run
    application.post_init = init_db
    
    print("🤖 Bot ishga tushdi!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()