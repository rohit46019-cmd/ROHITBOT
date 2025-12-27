#!/usr/bin/env python3
"""
Telegram Bot - File Downloader & Sender
Fixed Version - Commands will work now
"""

import os
import sys
import logging
import asyncio
import time
import sqlite3
from pathlib import Path
from threading import Thread
from datetime import datetime
from urllib.parse import urlparse, urljoin

# Third party imports
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, jsonify
import threading

# Load environment variables
load_dotenv()

# =================== CONFIGURATION ===================
class Config:
    # Telegram Bot Token
    BOT_TOKEN = os.environ.get('BOT_TOKEN')
    
    # Bot Owner ID
    OWNER_ID = int(os.environ.get('OWNER_ID', 123456789))
    
    # Render Specific Settings
    PORT = int(os.environ.get('PORT', 10000))
    IS_RENDER = os.environ.get('RENDER', 'false').lower() == 'true'
    
    # Get Render external URL
    RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
    if RENDER_EXTERNAL_URL:
        # FIX: Use correct webhook URL format
        WEBHOOK_URL = f"{RENDER_EXTERNAL_URL.rstrip('/')}/webhook"
    else:
        WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')
    
    # Bot Settings
    AUTO_DELETE_TIME = 10
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (Telegram limit for bots)
    
    # Paths
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / 'data'
    TEMP_DIR = BASE_DIR / 'temp_files'
    
    # Create directories
    DATA_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)
    
    # Database path
    DB_PATH = DATA_DIR / 'bot_database.db'
    
    # Logging directory
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

# =================== DATABASE ===================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_tables()
    
    def init_tables(self):
        """Initialize database tables"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS websites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                name TEXT,
                chat_id TEXT,
                folder TEXT,
                file_types TEXT,
                last_checked DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloaded_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                website_id INTEGER,
                file_url TEXT UNIQUE,
                file_name TEXT,
                file_size INTEGER,
                sent_to_user BOOLEAN DEFAULT 0,
                downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def add_website(self, url, name, chat_id, folder, file_types):
        """Add a new website to monitor"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO websites 
                (url, name, chat_id, folder, file_types)
                VALUES (?, ?, ?, ?, ?)
            ''', (url, name, str(chat_id), folder, file_types))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Database error adding website: {e}")
            return False
    
    def get_websites(self):
        """Get all websites"""
        self.cursor.execute('SELECT * FROM websites')
        return self.cursor.fetchall()
    
    def get_website_by_url(self, url):
        """Get website by URL"""
        self.cursor.execute('SELECT * FROM websites WHERE url = ?', (url,))
        return self.cursor.fetchone()
    
    def delete_website(self, url):
        """Delete website"""
        try:
            self.cursor.execute('DELETE FROM websites WHERE url = ?', (url,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Database error deleting website: {e}")
            return False
    
    def mark_file_downloaded(self, website_id, file_url, file_name, file_size, sent=False):
        """Mark a file as downloaded"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO downloaded_files 
                (website_id, file_url, file_name, file_size, sent_to_user)
                VALUES (?, ?, ?, ?, ?)
            ''', (website_id, file_url, file_name, file_size, sent))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Database error marking file: {e}")
            return False
    
    def is_file_downloaded(self, file_url):
        """Check if file already downloaded"""
        self.cursor.execute(
            'SELECT 1 FROM downloaded_files WHERE file_url = ?',
            (file_url,)
        )
        return self.cursor.fetchone() is not None
    
    def mark_file_sent(self, file_url):
        """Mark file as sent to user"""
        try:
            self.cursor.execute(
                'UPDATE downloaded_files SET sent_to_user = 1 WHERE file_url = ?',
                (file_url,)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Database error marking file sent: {e}")
            return False
    
    def close(self):
        """Close database connection"""
        self.conn.close()

# Initialize database
db = Database()

# =================== FLASK WEB SERVER ===================
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram File Downloader Bot",
        "timestamp": datetime.now().isoformat(),
        "mode": "webhook" if config.IS_RENDER else "polling"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# =================== BOT HANDLERS ===================
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        msg = await update.message.reply_text("❌ Unauthorized access!")
        await delete_message_after(msg, 5)
        return
    
    welcome_text = """
🤖 *File Downloader Bot*

*मैं ये कर सकता हूं:*
1. Website से files download करना
2. उन्हें Telegram में आपको भेजना
3. Automatic monitoring

*Commands:*
/addsite <url> <file_types> - Website add करें
/listsites - Websites list देखें
/delsite <url> - Website remove करें
/download <url> - Direct file download करें
/status - Bot status
/help - Help देखें

*Example:*
`/addsite https://example.com/pdf pdf,docx`
`/download https://example.com/file.pdf`
    """
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    logger.info(f"Start command received from {user_id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
📚 *File Downloader Bot Help*

*How it works:*
1. Add website with `/addsite`
2. Bot automatic check करेगा
3. New files download करके भेज देगा
4. या direct `/download` command से download करें

*File Types Supported:*
• Videos: mp4, avi, mkv, mov
• Documents: pdf, doc, docx, txt
• Images: jpg, png, gif
• Archives: zip, rar, 7z
• Audio: mp3, wav

*Examples:*
`/addsite https://filesamples.com pdf,docx`
`/download https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf`
`/listsites`
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')
    logger.info(f"Help command received from {update.effective_user.id}")

async def add_site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addsite command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        msg = await update.message.reply_text("❌ Unauthorized access!")
        await delete_message_after(msg, 5)
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/addsite <url> <file_types>`\n"
            "Example: `/addsite https://example.com pdf,docx,mp4`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    file_types = context.args[1]
    chat_id = update.effective_chat.id
    
    # Extract website name
    try:
        parsed = urlparse(url)
        name = parsed.netloc or url[:30]
    except:
        name = url[:30]
    
    # Add to database
    if db.add_website(url, name, chat_id, "downloads", file_types):
        response = f"""
✅ *Website Added!*

*URL:* `{url}`
*File Types:* {file_types}
*Chat ID:* `{chat_id}`

Bot हर 30 minutes में automatic check करेगा और new files भेजेगा।
        """
        logger.info(f"Website added by {user_id}: {url}")
    else:
        response = "❌ Failed to add website."
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def list_sites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listsites command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        msg = await update.message.reply_text("❌ Unauthorized access!")
        await delete_message_after(msg, 5)
        return
    
    websites = db.get_websites()
    
    if not websites:
        await update.message.reply_text("📭 No websites added yet.")
        return
    
    response = "📋 *Your Websites:*\n\n"
    for idx, site in enumerate(websites, 1):
        response += f"*{idx}. {site[2]}*\n"
        response += f"   URL: `{site[1]}`\n"
        response += f"   Types: `{site[5]}`\n"
        response += f"   Chat: `{site[3]}`\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')
    logger.info(f"List sites command from {user_id}")

async def delete_site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delsite command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        msg = await update.message.reply_text("❌ Unauthorized access!")
        await delete_message_after(msg, 5)
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/delsite <url>`", parse_mode='Markdown')
        return
    
    url = context.args[0]
    
    if db.delete_website(url):
        await update.message.reply_text(f"✅ Removed: `{url}`", parse_mode='Markdown')
        logger.info(f"Website deleted by {user_id}: {url}")
    else:
        await update.message.reply_text(f"❌ Not found: `{url}`", parse_mode='Markdown')

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /download command - Direct file download"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        msg = await update.message.reply_text("❌ Unauthorized access!")
        await delete_message_after(msg, 5)
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: `/download <file_url>`\n"
            "Example: `/download https://example.com/file.pdf`",
            parse_mode='Markdown'
        )
        return
    
    file_url = context.args[0]
    chat_id = update.effective_chat.id
    
    # Send processing message
    msg = await update.message.reply_text("⬇️ Downloading file...")
    
    try:
        # Download file
        downloaded = await download_file(file_url)
        
        if downloaded and downloaded['path'].exists():
            # Send file to user
            await send_file_to_user(chat_id, downloaded['path'], downloaded['name'])
            
            # Update message
            await msg.edit_text(
                f"✅ File sent!\n"
                f"Name: {downloaded['name']}\n"
                f"Size: {downloaded['size'] // 1024} KB"
            )
            
            # Cleanup
            downloaded['path'].unlink()
            logger.info(f"File downloaded by {user_id}: {file_url}")
        else:
            await msg.edit_text("❌ Failed to download file.")
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        msg = await update.message.reply_text("❌ Unauthorized access!")
        await delete_message_after(msg, 5)
        return
    
    websites = db.get_websites()
    
    status_text = f"""
📊 *Bot Status*

*Environment:* {'Render.com' if config.IS_RENDER else 'Local'}
*Port:* `{config.PORT}`
*Webhook:* `{config.WEBHOOK_URL if config.WEBHOOK_URL else 'Not set'}`
*Websites:* {len(websites)}
*Temp Files:* {len(list(config.TEMP_DIR.glob('*')))}
*Owner ID:* `{config.OWNER_ID}`
*Max File Size:* {config.MAX_FILE_SIZE // 1024 // 1024} MB
*Mode:* {'Webhook (Render)' if config.IS_RENDER else 'Polling'}
    """
    
    await update.message.reply_text(status_text, parse_mode='Markdown')
    logger.info(f"Status command from {user_id}")

# =================== FILE DOWNLOAD FUNCTIONS ===================
async def download_file(file_url):
    """Download a file from URL"""
    try:
        # Get filename from URL
        filename = file_url.split('/')[-1]
        if '?' in filename:
            filename = filename.split('?')[0]
        
        if not filename:
            filename = f"file_{int(time.time())}.bin"
        
        temp_path = config.TEMP_DIR / filename
        
        # Download file
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(file_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        file_size = int(response.headers.get('content-length', 0))
        
        # Check file size limit
        if file_size > config.MAX_FILE_SIZE:
            logger.warning(f"File too large: {file_size} bytes")
            return None
        
        # Download with progress
        downloaded = 0
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        
        return {
            'path': temp_path,
            'name': filename,
            'size': file_size,
            'url': file_url
        }
        
    except Exception as e:
        logger.error(f"Download error for {file_url}: {e}")
        return None

async def send_file_to_user(chat_id, file_path, caption=""):
    """Send file to Telegram user"""
    try:
        # Check file size (Telegram limits)
        file_size = file_path.stat().st_size
        
        if file_size > config.MAX_FILE_SIZE:
            # Send message instead
            await application.bot.send_message(
                chat_id=chat_id,
                text=f"❌ File too large: {file_size // 1024 // 1024}MB (max {config.MAX_FILE_SIZE // 1024 // 1024}MB)"
            )
            return False
        
        # Determine file type
        ext = file_path.suffix.lower()
        
        with open(file_path, 'rb') as file:
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                await application.bot.send_photo(
                    chat_id=chat_id,
                    photo=file,
                    caption=caption[:1024]
                )
            elif ext in ['.mp4', '.avi', '.mkv', '.mov']:
                await application.bot.send_video(
                    chat_id=chat_id,
                    video=file,
                    caption=caption[:1024],
                    supports_streaming=True
                )
            elif ext in ['.mp3', '.wav', '.ogg']:
                await application.bot.send_audio(
                    chat_id=chat_id,
                    audio=file,
                    caption=caption[:1024]
                )
            else:
                await application.bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    caption=caption[:1024]
                )
        
        logger.info(f"File sent to {chat_id}: {file_path.name}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        return False

class WebsiteScanner:
    """Scan website for downloadable files"""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def find_files_on_page(self, url, file_extensions):
        """Find all files with given extensions on a webpage"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            files = []
            
            # Look for all links
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(url, href)
                
                # Check if it's a file
                for ext in file_extensions:
                    if full_url.lower().endswith(f'.{ext}'):
                        files.append({
                            'url': full_url,
                            'name': link.text.strip() or href.split('/')[-1],
                            'type': ext
                        })
                        break
            
            return files
            
        except Exception as e:
            logger.error(f"Error scanning {url}: {e}")
            return []

async def check_websites():
    """Check all websites for new files and send them"""
    logger.info("Starting website check...")
    websites = db.get_websites()
    
    if not websites:
        return
    
    scanner = WebsiteScanner()
    
    for site in websites:
        try:
            website_id = site[0]
            url = site[1]
            chat_id = int(site[3])
            file_types = site[5].split(',')
            
            logger.info(f"Checking {url} for {file_types}")
            
            # Find files on website
            files = scanner.find_files_on_page(url, file_types)
            
            if files:
                logger.info(f"Found {len(files)} files on {url}")
                
                # Process each file
                for file_info in files:
                    # Check if already downloaded
                    if not db.is_file_downloaded(file_info['url']):
                        # Download file
                        downloaded = await download_file(file_info['url'])
                        
                        if downloaded and downloaded['path'].exists():
                            # Send to user
                            sent = await send_file_to_user(chat_id, downloaded['path'], file_info['name'])
                            
                            # Mark in database
                            db.mark_file_downloaded(
                                website_id,
                                file_info['url'],
                                file_info['name'],
                                downloaded['size'],
                                sent
                            )
                            
                            logger.info(f"Sent {file_info['name']} to {chat_id}")
                            
                            # Cleanup
                            downloaded['path'].unlink()
                            
                            # Delay between files
                            await asyncio.sleep(2)
            
            # Update last checked time
            db.cursor.execute(
                'UPDATE websites SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                (website_id,)
            )
            db.conn.commit()
            
        except Exception as e:
            logger.error(f"Error processing website: {e}")
            continue

# =================== BACKGROUND TASKS ===================
def start_background_scheduler():
    """Start background scheduler"""
    scheduler = BackgroundScheduler()
    
    # Check websites every 30 minutes
    scheduler.add_job(
        lambda: asyncio.run(check_websites()),
        'interval',
        minutes=30,
        id='website_check'
    )
    
    # Keep-alive ping for Render
    if config.IS_RENDER:
        scheduler.add_job(
            keep_alive_ping,
            'interval',
            minutes=5,
            id='keep_alive'
        )
    
    scheduler.start()
    logger.info("Background scheduler started")

def keep_alive_ping():
    """Ping own health endpoint"""
    try:
        if config.IS_RENDER and config.WEBHOOK_URL:
            health_url = config.WEBHOOK_URL.replace('/webhook', '/health')
            response = requests.get(health_url, timeout=5)
            logger.debug(f"Keep-alive ping: {response.status_code}")
    except Exception as e:
        logger.error(f"Keep-alive ping failed: {e}")

# =================== BOT APPLICATION ===================
application = None

def setup_bot():
    """Setup and return bot application"""
    global application
    
    if not config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found!")
        sys.exit(1)
    
    # Create Application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addsite", add_site_command))
    application.add_handler(CommandHandler("listsites", list_sites_command))
    application.add_handler(CommandHandler("delsite", delete_site_command))
    application.add_handler(CommandHandler("download", download_command))
    application.add_handler(CommandHandler("status", status_command))
    
    logger.info("Bot handlers set up successfully")
    return application

def run_flask():
    """Run Flask server"""
    logger.info(f"Starting Flask server on port {config.PORT}")
    app.run(
        host='0.0.0.0',
        port=config.PORT,
        debug=False,
        use_reloader=False
    )

async def setup_webhook():
    """Setup webhook for Render"""
    global application
    
    if not config.WEBHOOK_URL:
        logger.error("WEBHOOK_URL not configured!")
        return False
    
    try:
        # Set webhook
        await application.bot.set_webhook(
            url=config.WEBHOOK_URL,
            drop_pending_updates=True
        )
        
        # Verify webhook info
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"Webhook set: {config.WEBHOOK_URL}")
        logger.info(f"Webhook info: {webhook_info.url}, Pending updates: {webhook_info.pending_update_count}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        return False

async def run_bot_polling():
    """Run bot in polling mode"""
    global application
    
    logger.info("=" * 50)
    logger.info("Starting File Downloader Bot in POLLING mode...")
    logger.info(f"Owner ID: {config.OWNER_ID}")
    
    # Setup bot
    application = setup_bot()
    
    # Start background scheduler
    start_background_scheduler()
    
    # Run polling
    await application.run_polling()

async def run_bot_webhook():
    """Run bot in webhook mode (for Render)"""
    global application
    
    logger.info("=" * 50)
    logger.info("Starting File Downloader Bot in WEBHOOK mode...")
    logger.info(f"Owner ID: {config.OWNER_ID}")
    logger.info(f"Webhook URL: {config.WEBHOOK_URL}")
    
    # Setup bot
    application = setup_bot()
    
    # Start background scheduler
    start_background_scheduler()
    
    # Initialize application
    await application.initialize()
    
    # Setup webhook
    if not await setup_webhook():
        logger.error("Failed to setup webhook, falling back to polling")
        await run_bot_polling()
        return
    
    # Start application
    await application.start()
    
    logger.info("Bot started in webhook mode")
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Flask server started in background thread")
    
    # Keep the bot running
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
    except KeyboardInterrupt:
        logger.info("Bot stopping...")
    finally:
        await application.stop()

# =================== ENTRY POINT ===================
def main():
    """Main entry point"""
    try:
        # Check if BOT_TOKEN is set
        if not config.BOT_TOKEN:
            logger.error("❌ ERROR: BOT_TOKEN environment variable is not set!")
            logger.error("Please set BOT_TOKEN in your environment variables")
            sys.exit(1)
        
        # Check if OWNER_ID is set
        if config.OWNER_ID == 123456789:
            logger.warning("⚠️ WARNING: Using default OWNER_ID (123456789)")
            logger.warning("Set OWNER_ID environment variable to your Telegram user ID")
        
        # Run in appropriate mode
        if config.IS_RENDER and config.WEBHOOK_URL:
            asyncio.run(run_bot_webhook())
        else:
            asyncio.run(run_bot_polling())
            
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
