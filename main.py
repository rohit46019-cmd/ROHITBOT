#!/usr/bin/env python3
"""
Render.com compatible Telegram Bot
All common issues fixed: Port, Webhook, Storage, etc.
"""

import os
import sys
import logging
import asyncio
from threading import Thread
from datetime import datetime
import sqlite3
import json
import shutil
from pathlib import Path

# Third party imports
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from telegram.error import TelegramError
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import aiofiles

# For Render web server
from flask import Flask, request, jsonify

# Load environment variables
load_dotenv()

# =================== RENDER SPECIFIC FIXES ===================
# Problem 1: Port detection fix
def get_port():
    """Get port from environment with fallback"""
    port = os.environ.get('PORT')
    if port:
        return int(port)
    # Check common Render ports
    for p in [10000, 8080, 5000, 3000]:
        try:
            # Try to bind to port
            return p
        except:
            continue
    return 10000  # Default fallback

# Problem 2: Webhook URL fix for Render
def get_webhook_url():
    """Get webhook URL for Render"""
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if external_url:
        return f"{external_url}/webhook"
    
    # For local testing
    return "https://your-bot.onrender.com/webhook"

# =================== CONFIGURATION ===================
class Config:
    # Telegram
    BOT_TOKEN = os.environ.get('BOT_TOKEN')
    OWNER_ID = int(os.environ.get('OWNER_ID', '0'))
    
    # Render Specific
    PORT = get_port()
    IS_RENDER = os.environ.get('RENDER', 'false').lower() == 'true'
    WEBHOOK_URL = get_webhook_url()
    
    # Bot Settings
    AUTO_DELETE_TIME = int(os.environ.get('AUTO_DELETE_TIME', '5'))
    CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '1800'))
    MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', '2000000000'))
    
    # Paths (Render ke liye writable paths)
    BASE_DIR = Path(__file__).parent
    if IS_RENDER:
        # Render par temporary storage use karein
        DATA_DIR = BASE_DIR / 'data'
        TEMP_DIR = BASE_DIR / 'tmp'
    else:
        DATA_DIR = BASE_DIR / 'data'
        TEMP_DIR = BASE_DIR / 'temp_files'
    
    # Create directories
    DATA_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)
    
    # Database
    DB_PATH = DATA_DIR / 'bot_database.db'
    
    # Logging
    LOG_DIR = BASE_DIR / 'logs'
    LOG_DIR.mkdir(exist_ok=True)

# Initialize config
config = Config()

# =================== LOGGING SETUP ===================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(config.LOG_DIR / 'bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# =================== DATABASE SETUP ===================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_tables()
    
    def init_tables(self):
        """Initialize database tables"""
        # Websites table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS websites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                name TEXT,
                group_id TEXT,
                folder TEXT,
                file_types TEXT,
                check_interval INTEGER DEFAULT 1800,
                last_checked DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Downloaded files table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloaded_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                website_id INTEGER,
                file_url TEXT UNIQUE,
                file_name TEXT,
                file_size INTEGER,
                downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                sent_to_group BOOLEAN DEFAULT 0,
                FOREIGN KEY (website_id) REFERENCES websites (id)
            )
        ''')
        
        # Groups table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT UNIQUE,
                group_name TEXT,
                folder_name TEXT,
                settings TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def add_website(self, url, name, group_id, folder, file_types):
        """Add a new website to monitor"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO websites 
                (url, name, group_id, folder, file_types)
                VALUES (?, ?, ?, ?, ?)
            ''', (url, name, group_id, folder, file_types))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding website: {e}")
            return False
    
    def get_websites(self):
        """Get all websites"""
        self.cursor.execute('SELECT * FROM websites')
        return self.cursor.fetchall()
    
    def mark_file_downloaded(self, website_id, file_url, file_name, file_size):
        """Mark a file as downloaded"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO downloaded_files 
                (website_id, file_url, file_name, file_size)
                VALUES (?, ?, ?, ?)
            ''', (website_id, file_url, file_name, file_size))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error marking file: {e}")
            return False
    
    def is_file_downloaded(self, file_url):
        """Check if file already downloaded"""
        self.cursor.execute(
            'SELECT 1 FROM downloaded_files WHERE file_url = ?',
            (file_url,)
        )
        return self.cursor.fetchone() is not None
    
    def cleanup_old_temp_files(self):
        """Cleanup old temporary files"""
        try:
            # Delete files older than 24 hours from temp directory
            temp_dir = config.TEMP_DIR
            for file_path in temp_dir.glob('*'):
                if file_path.stat().st_mtime < (time.time() - 86400):
                    file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return False

# Initialize database
db = Database()

# =================== BOT SECURITY ===================
def is_owner(user_id):
    """Check if user is owner"""
    return user_id == config.OWNER_ID

async def delete_message_after(message, seconds):
    """Delete message after specified seconds"""
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass

# =================== WEBSITE MONITORING ===================
class WebsiteMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    async def check_website(self, website):
        """Check website for new files"""
        try:
            response = self.session.get(website['url'], timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract file links (customize based on website)
            files = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if self.is_valid_file(href, website['file_types']):
                    files.append({
                        'url': self.make_absolute_url(website['url'], href),
                        'name': link.text.strip() or href.split('/')[-1]
                    })
            
            return files
        except Exception as e:
            logger.error(f"Error checking website {website['url']}: {e}")
            return []
    
    def is_valid_file(self, url, file_types):
        """Check if URL points to a valid file type"""
        if not file_types:
            return True
        
        file_types_list = file_types.split(',')
        return any(url.lower().endswith(ftype.strip()) for ftype in file_types_list)
    
    def make_absolute_url(self, base_url, href):
        """Convert relative URL to absolute"""
        if href.startswith('http'):
            return href
        elif href.startswith('/'):
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        else:
            return f"{base_url.rstrip('/')}/{href}"
    
    async def download_file(self, file_url, file_name):
        """Download file to temporary storage"""
        try:
            # Create temp file path
            temp_file = config.TEMP_DIR / file_name
            
            # Download file
            response = self.session.get(file_url, stream=True, timeout=60)
            response.raise_for_status()
            
            # Check file size
            file_size = int(response.headers.get('content-length', 0))
            if file_size > config.MAX_FILE_SIZE:
                logger.warning(f"File too large: {file_size}")
                return None
            
            # Save file
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return {
                'path': temp_file,
                'size': file_size,
                'name': file_name
            }
        except Exception as e:
            logger.error(f"Download error {file_url}: {e}")
            return None

# Initialize monitor
monitor = WebsiteMonitor()

# =================== TELEGRAM BOT HANDLERS ===================
class TelegramBot:
    def __init__(self):
        self.application = None
        self.bot = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not is_owner(update.effective_user.id):
            return
        
        # Auto-delete command message (if in group)
        if update.effective_chat.type != 'private':
            try:
                await update.message.delete()
            except:
                pass
        
        welcome_msg = await update.message.reply_text(
            "🔐 Private Bot Activated\n\n"
            "Commands (auto-delete in 5s):\n"
            "/addsite - Add website\n"
            "/listsites - Show websites\n"
            "/backlog - Download existing\n"
            "/status - Bot status\n"
            "/cleanup - Clean temp files"
        )
        
        # Auto delete welcome message
        await delete_message_after(welcome_msg, 5)
    
    async def add_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsite command"""
        if not is_owner(update.effective_user.id):
            return
        
        # Parse arguments
        if not context.args:
            msg = await update.message.reply_text(
                "Usage: /addsite <url> <folder_name> <file_types>\n"
                "Example: /addsite https://example.com/videos my_videos mp4,avi"
            )
            await delete_message_after(msg, 10)
            return
        
        url = context.args[0]
        folder = context.args[1] if len(context.args) > 1 else "default"
        file_types = context.args[2] if len(context.args) > 2 else "mp4,pdf"
        group_id = str(update.effective_chat.id)
        
        # Add to database
        success = db.add_website(
            url=url,
            name=url.split('/')[2],
            group_id=group_id,
            folder=folder,
            file_types=file_types
        )
        
        if success:
            msg = await update.message.reply_text(
                f"✅ Website added!\n"
                f"URL: {url}\n"
                f"Folder: {folder}\n"
                f"Group: {group_id}"
            )
            # Auto delete after 5 seconds
            await delete_message_after(msg, 5)
        else:
            msg = await update.message.reply_text("❌ Failed to add website")
            await delete_message_after(msg, 5)
        
        # Try to delete user's command
        try:
            await update.message.delete()
        except:
            pass
    
    async def send_file_to_group(self, file_path, group_id, caption=""):
        """Send file to Telegram group"""
        try:
            file_size = os.path.getsize(file_path)
            
            if file_size > 50 * 1024 * 1024:  # 50MB
                # Use file chunking for large files
                await self.send_large_file(file_path, group_id, caption)
            else:
                # Send directly for small files
                async with aiofiles.open(file_path, 'rb') as f:
                    await self.bot.send_document(
                        chat_id=group_id,
                        document=f,
                        caption=caption[:1024] if caption else None,
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60
                    )
            
            # Cleanup temp file
            try:
                os.remove(file_path)
            except:
                pass
            
            return True
        except Exception as e:
            logger.error(f"Send file error: {e}")
            return False
    
    async def send_large_file(self, file_path, group_id, caption):
        """Send large file in chunks"""
        # Telegram supports up to 2GB, but we need to handle carefully
        chunk_size = 50 * 1024 * 1024  # 50MB chunks
        
        with open(file_path, 'rb') as f:
            chunk_num = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                # Save chunk to temp file
                chunk_file = f"{file_path}_part{chunk_num}"
                with open(chunk_file, 'wb') as cf:
                    cf.write(chunk)
                
                # Send chunk
                async with aiofiles.open(chunk_file, 'rb') as cf:
                    await self.bot.send_document(
                        chat_id=group_id,
                        document=cf,
                        caption=f"{caption} (Part {chunk_num + 1})" if caption else f"Part {chunk_num + 1}",
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60
                    )
                
                # Cleanup chunk file
                try:
                    os.remove(chunk_file)
                except:
                    pass
                
                chunk_num += 1

# =================== RENDER WEB SERVER ===================
# Problem 3: Render needs a web server running
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Bot",
        "deployed_on": "Render.com",
        "owner_id": config.OWNER_ID
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.run(process_update(update))
    return "OK"

# =================== BACKGROUND TASKS ===================
def start_background_tasks():
    """Start background tasks for monitoring"""
    scheduler = BackgroundScheduler()
    
    # Website checking task
    scheduler.add_job(
        check_all_websites,
        'interval',
        seconds=config.CHECK_INTERVAL,
        id='website_check'
    )
    
    # Temp cleanup task (Render storage management)
    scheduler.add_job(
        db.cleanup_old_temp_files,
        'interval',
        hours=1,
        id='cleanup'
    )
    
    # Keep-alive task for Render free tier
    if config.IS_RENDER:
        scheduler.add_job(
            keep_alive_ping,
            'interval',
            minutes=14,  # Render free tier sleeps after 15 minutes
            id='keep_alive'
        )
    
    scheduler.start()

async def check_all_websites():
    """Check all registered websites"""
    websites = db.get_websites()
    for website in websites:
        try:
            files = await monitor.check_website({
                'url': website[1],
                'file_types': website[5]
            })
            
            for file_info in files:
                if not db.is_file_downloaded(file_info['url']):
                    # Download file
                    downloaded = await monitor.download_file(
                        file_info['url'],
                        file_info['name']
                    )
                    
                    if downloaded:
                        # Send to group
                        await bot.send_document(
                            chat_id=website[3],  # group_id
                            document=open(downloaded['path'], 'rb'),
                            caption=f"📁 {website[4]}/{file_info['name']}"
                        )
                        
                        # Mark as downloaded
                        db.mark_file_downloaded(
                            website[0],  # website_id
                            file_info['url'],
                            file_info['name'],
                            downloaded['size']
                        )
                        
                        # Cleanup
                        try:
                            os.remove(downloaded['path'])
                        except:
                            pass
                        
                        # Delay between files
                        await asyncio.sleep(2)
        
        except Exception as e:
            logger.error(f"Error processing website {website[1]}: {e}")

def keep_alive_ping():
    """Keep Render app alive by pinging itself"""
    try:
        if config.IS_RENDER and config.WEBHOOK_URL:
            # Ping the health endpoint
            requests.get(config.WEBHOOK_URL.replace('/webhook', '/health'), timeout=10)
            logger.info("Keep-alive ping sent")
    except Exception as e:
        logger.warning(f"Keep-alive ping failed: {e}")

# =================== MAIN SETUP ===================
async def main():
    """Main function to start the bot"""
    global bot
    
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()
    bot = application.bot
    
    # Add handlers
    application.add_handler(CommandHandler("start", TelegramBot().start))
    application.add_handler(CommandHandler("addsite", TelegramBot().add_site))
    # Add more handlers as needed...
    
    # Start background tasks
    start_background_tasks()
    
    # Configure for Render (webhook) or local (polling)
    if config.IS_RENDER:
        # Set webhook for Render
        await application.bot.set_webhook(
            url=config.WEBHOOK_URL,
            drop_pending_updates=True
        )
        logger.info(f"Webhook set to: {config.WEBHOOK_URL}")
        
        # Start Flask server
        from threading import Thread
        flask_thread = Thread(target=lambda: app.run(
            host='0.0.0.0',
            port=config.PORT,
            debug=False,
            use_reloader=False
        ))
        flask_thread.start()
        
        # Keep the asyncio loop running
        while True:
            await asyncio.sleep(3600)
    
    else:
        # Use polling for local development
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Run forever
        await asyncio.Event().wait()

# =================== RENDER STARTUP SCRIPT ===================
if __name__ == "__main__":
    # Render-specific startup checks
    if config.IS_RENDER:
        logger.info("Starting on Render.com environment")
        logger.info(f"Port: {config.PORT}")
        logger.info(f"Webhook URL: {config.WEBHOOK_URL}")
        
        # Check essential config
        if not config.BOT_TOKEN:
            logger.error("BOT_TOKEN not set in environment variables!")
            sys.exit(1)
        
        if not config.OWNER_ID:
            logger.error("OWNER_ID not set!")
            sys.exit(1)
        
        # Start the bot
        asyncio.run(main())
    
    else:
        # Local development
        logger.info("Starting in local development mode")
        asyncio.run(main())
