#!/usr/bin/env python3
"""
Telegram Bot for Render.com - FIXED VERSION
"""

import os
import sys
import logging
import asyncio
import time
import sqlite3
import json
from pathlib import Path
from threading import Thread, Event
from datetime import datetime
from urllib.parse import urlparse

# Third party imports
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# For Render web server
from flask import Flask, request, jsonify

# Load environment variables
load_dotenv()

# =================== CONFIGURATION ===================
class Config:
    # Telegram Bot Token (Render Environment Variables se)
    BOT_TOKEN = os.environ.get('BOT_TOKEN')
    
    # Bot Owner ID (Your Telegram User ID)
    OWNER_ID = int(os.environ.get('OWNER_ID', '123456789'))
    
    # Render Specific Settings
    PORT = int(os.environ.get('PORT', 10000))
    IS_RENDER = os.environ.get('RENDER', 'false').lower() == 'true'
    
    # Get Render external URL
    RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
    if RENDER_EXTERNAL_URL:
        WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook"
    else:
        WEBHOOK_URL = "https://rohitbot-c2rs.onrender.com/webhook"
    
    # Bot Settings
    AUTO_DELETE_TIME = 5  # seconds
    CHECK_INTERVAL = 1800  # 30 minutes
    MAX_FILE_SIZE = 2000000000  # 2GB
    
    # Paths for Render (temporary storage)
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
        # Websites table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS websites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                name TEXT,
                group_id TEXT,
                folder TEXT,
                file_types TEXT,
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
                FOREIGN KEY (website_id) REFERENCES websites (id)
            )
        ''')
        
        # Bot settings table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT
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
            logger.error(f"Database error marking file: {e}")
            return False
    
    def is_file_downloaded(self, file_url):
        """Check if file already downloaded"""
        self.cursor.execute(
            'SELECT 1 FROM downloaded_files WHERE file_url = ?',
            (file_url,)
        )
        return self.cursor.fetchone() is not None
    
    def cleanup_old_temp_files(self):
        """Cleanup old temporary files from database"""
        try:
            # Delete records older than 7 days
            self.cursor.execute('''
                DELETE FROM downloaded_files 
                WHERE downloaded_at < datetime('now', '-7 days')
            ''')
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Database cleanup error: {e}")
            return False
    
    def close(self):
        """Close database connection"""
        self.conn.close()

# Initialize database
db = Database()

# =================== FLASK WEB SERVER ===================
app = Flask(__name__)
stop_event = Event()

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Telegram Bot",
        "timestamp": datetime.now().isoformat(),
        "owner_id": config.OWNER_ID
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "bot": "running"})

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint - FIXED"""
    if request.method == "POST":
        try:
            # Get the update from Telegram
            update = Update.de_json(request.get_json(), bot)
            
            # Process the update
            application.update_queue.put_nowait(update)
            
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return jsonify({"error": str(e)}), 400
    
    return jsonify({"error": "Method not allowed"}), 405

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
        await update.message.reply_text("❌ Unauthorized access!")
        return
    
    welcome_text = """
🤖 *Website Monitor Bot*

*Available Commands:*
/addsite <url> <folder> <file_types> - Add website to monitor
/listsites - List all monitored websites
/delsite <url> - Remove website
/checknow - Check all websites now
/status - Bot status
/cleanup - Clean temporary files

*Example:*
`/addsite https://example.com/downloads videos mp4,avi,mkv`
    """
    
    msg = await update.message.reply_text(welcome_text, parse_mode='Markdown')
    await delete_message_after(msg, 10)
    
    # Delete user's command
    try:
        await update.message.delete()
    except:
        pass

async def add_site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addsite command"""
    if not is_owner(update.effective_user.id):
        return
    
    if len(context.args) < 3:
        help_text = """
📝 *Usage:*
`/addsite <url> <folder_name> <file_types>`

*Example:*
`/addsite https://example.com/videos my_videos mp4,avi,mkv`
`/addsite https://site.com/documents pdfs pdf,doc,docx`
        """
        msg = await update.message.reply_text(help_text, parse_mode='Markdown')
        await delete_message_after(msg, 10)
        return
    
    url = context.args[0]
    folder = context.args[1]
    file_types = context.args[2]
    group_id = str(update.effective_chat.id)
    
    # Extract website name from URL
    try:
        parsed = urlparse(url)
        name = parsed.netloc
    except:
        name = url
    
    # Add to database
    if db.add_website(url, name, group_id, folder, file_types):
        response = f"""
✅ *Website Added Successfully!*

*URL:* `{url}`
*Name:* {name}
*Folder:* {folder}
*File Types:* {file_types}
*Group ID:* `{group_id}`
        """
    else:
        response = "❌ Failed to add website. It might already exist."
    
    msg = await update.message.reply_text(response, parse_mode='Markdown')
    await delete_message_after(msg, 5)
    
    # Delete command
    try:
        await update.message.delete()
    except:
        pass

async def list_sites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listsites command"""
    if not is_owner(update.effective_user.id):
        return
    
    websites = db.get_websites()
    
    if not websites:
        msg = await update.message.reply_text("📭 No websites are being monitored.")
        await delete_message_after(msg, 5)
        return
    
    response = "📋 *Monitored Websites:*\n\n"
    for site in websites:
        response += f"• *{site[2]}* (`{site[1]}`)\n"
        response += f"  Folder: `{site[4]}` | Types: `{site[5]}`\n\n"
    
    # Split if message is too long
    if len(response) > 4000:
        chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for chunk in chunks:
            msg = await update.message.reply_text(chunk, parse_mode='Markdown')
            await delete_message_after(msg, 10)
    else:
        msg = await update.message.reply_text(response, parse_mode='Markdown')
        await delete_message_after(msg, 10)
    
    # Delete command
    try:
        await update.message.delete()
    except:
        pass

async def delete_site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delsite command"""
    if not is_owner(update.effective_user.id):
        return
    
    if not context.args:
        msg = await update.message.reply_text("Usage: `/delsite <url>`", parse_mode='Markdown')
        await delete_message_after(msg, 5)
        return
    
    url = context.args[0]
    
    if db.delete_website(url):
        msg = await update.message.reply_text(f"✅ Website removed: `{url}`", parse_mode='Markdown')
    else:
        msg = await update.message.reply_text(f"❌ Website not found: `{url}`", parse_mode='Markdown')
    
    await delete_message_after(msg, 5)
    
    # Delete command
    try:
        await update.message.delete()
    except:
        pass

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    if not is_owner(update.effective_user.id):
        return
    
    websites = db.get_websites()
    
    status_text = f"""
📊 *Bot Status*

*Environment:* {'Render.com' if config.IS_RENDER else 'Local'}
*Port:* `{config.PORT}`
*Webhook:* `{config.WEBHOOK_URL}`
*Monitored Websites:* {len(websites)}
*Temp Files:* {len(list(config.TEMP_DIR.glob('*')))}
*Database Size:* {config.DB_PATH.stat().st_size // 1024} KB
    """
    
    msg = await update.message.reply_text(status_text, parse_mode='Markdown')
    await delete_message_after(msg, 10)
    
    # Delete command
    try:
        await update.message.delete()
    except:
        pass

async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cleanup command"""
    if not is_owner(update.effective_user.id):
        return
    
    # Clean temp directory
    files_deleted = 0
    for file_path in config.TEMP_DIR.glob('*'):
        try:
            file_path.unlink()
            files_deleted += 1
        except:
            pass
    
    # Clean database
    db.cleanup_old_temp_files()
    
    msg = await update.message.reply_text(
        f"🧹 Cleanup completed!\n"
        f"Deleted {files_deleted} temporary files."
    )
    await delete_message_after(msg, 5)
    
    # Delete command
    try:
        await update.message.delete()
    except:
        pass

async def check_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /checknow command"""
    if not is_owner(update.effective_user.id):
        return
    
    msg = await update.message.reply_text("🔄 Checking all websites...")
    
    websites = db.get_websites()
    if websites:
        # Trigger background check
        asyncio.create_task(check_all_websites())
        await msg.edit_text(f"✅ Started checking {len(websites)} websites in background.")
    else:
        await msg.edit_text("📭 No websites to check.")
    
    await delete_message_after(msg, 5)
    
    # Delete command
    try:
        await update.message.delete()
    except:
        pass

# =================== WEBSITE MONITORING ===================
class WebsiteMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract_files_from_html(self, html, base_url, file_types):
        """Extract file links from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        files = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Check if it's a file link
            if self.is_file_link(href, file_types):
                file_url = self.make_absolute_url(base_url, href)
                file_name = link.text.strip() or href.split('/')[-1]
                
                files.append({
                    'url': file_url,
                    'name': file_name,
                    'type': href.split('.')[-1].lower() if '.' in href else 'unknown'
                })
        
        return files
    
    def is_file_link(self, url, file_types):
        """Check if URL is a file based on extensions"""
        if not file_types or file_types.lower() == 'all':
            return True
        
        extensions = [ext.strip().lower() for ext in file_types.split(',')]
        url_lower = url.lower()
        
        # Check if URL ends with any of the extensions
        for ext in extensions:
            if url_lower.endswith(f'.{ext}'):
                return True
        
        # Also check for common file patterns
        file_patterns = ['.mp4', '.avi', '.mkv', '.pdf', '.zip', '.rar', '.7z']
        for pattern in file_patterns:
            if pattern in url_lower:
                return True
        
        return False
    
    def make_absolute_url(self, base_url, href):
        """Convert relative URL to absolute"""
        if href.startswith(('http://', 'https://')):
            return href
        elif href.startswith('/'):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        else:
            # Relative URL
            if base_url.endswith('/'):
                return f"{base_url}{href}"
            else:
                return f"{base_url}/{href}"
    
    async def check_website(self, website):
        """Check a single website for new files"""
        try:
            response = self.session.get(website['url'], timeout=30)
            response.raise_for_status()
            
            files = self.extract_files_from_html(
                response.text,
                website['url'],
                website['file_types']
            )
            
            return files
        except Exception as e:
            logger.error(f"Error checking website {website['url']}: {e}")
            return []
    
    async def download_file(self, file_url, file_name):
        """Download file to temporary storage"""
        try:
            # Sanitize file name
            safe_name = "".join(c for c in file_name if c.isalnum() or c in '._- ').strip()
            if not safe_name:
                safe_name = f"file_{int(time.time())}"
            
            temp_path = config.TEMP_DIR / safe_name
            
            # Download with progress
            response = self.session.get(file_url, stream=True, timeout=60)
            response.raise_for_status()
            
            file_size = int(response.headers.get('content-length', 0))
            
            # Check file size limit
            if file_size > config.MAX_FILE_SIZE:
                logger.warning(f"File too large: {file_size} bytes")
                return None
            
            # Download file
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return {
                'path': temp_path,
                'size': file_size,
                'name': safe_name
            }
            
        except Exception as e:
            logger.error(f"Error downloading {file_url}: {e}")
            return None

# Initialize monitor
monitor = WebsiteMonitor()

# =================== BACKGROUND TASKS ===================
def start_background_scheduler():
    """Start background scheduler for periodic tasks"""
    scheduler = BackgroundScheduler()
    
    # Website checking job (every 30 minutes)
    scheduler.add_job(
        lambda: asyncio.run(check_all_websites()),
        'interval',
        minutes=30,
        id='website_check',
        misfire_grace_time=300
    )
    
    # Cleanup job (every 6 hours)
    scheduler.add_job(
        lambda: asyncio.run(cleanup_temp_files()),
        'interval',
        hours=6,
        id='cleanup'
    )
    
    # Keep-alive ping for Render (every 10 minutes)
    if config.IS_RENDER:
        scheduler.add_job(
            keep_alive_ping,
            'interval',
            minutes=10,
            id='keep_alive'
        )
    
    scheduler.start()
    logger.info("Background scheduler started")

async def check_all_websites():
    """Check all websites for new files"""
    logger.info("Starting website check...")
    websites = db.get_websites()
    
    if not websites:
        logger.info("No websites to check")
        return
    
    total_files = 0
    
    for site in websites:
        website_info = {
            'id': site[0],
            'url': site[1],
            'name': site[2],
            'group_id': site[3],
            'folder': site[4],
            'file_types': site[5]
        }
        
        logger.info(f"Checking website: {website_info['name']} ({website_info['url']})")
        
        try:
            files = await monitor.check_website(website_info)
            
            if files:
                logger.info(f"Found {len(files)} files on {website_info['name']}")
                
                # Process each file
                for file_info in files:
                    if not db.is_file_downloaded(file_info['url']):
                        # Download file
                        downloaded = await monitor.download_file(
                            file_info['url'],
                            file_info['name']
                        )
                        
                        if downloaded:
                            logger.info(f"Downloaded: {file_info['name']} ({downloaded['size']} bytes)")
                            
                            # Mark as downloaded in database
                            db.mark_file_downloaded(
                                website_info['id'],
                                file_info['url'],
                                file_info['name'],
                                downloaded['size']
                            )
                            
                            total_files += 1
                            
                            # Clean up temp file
                            try:
                                downloaded['path'].unlink()
                            except:
                                pass
                            
                            # Small delay between files
                            await asyncio.sleep(1)
            
            # Update last checked time
            db.cursor.execute(
                'UPDATE websites SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                (website_info['id'],)
            )
            db.conn.commit()
            
        except Exception as e:
            logger.error(f"Error processing website {website_info['url']}: {e}")
            continue
    
    if total_files > 0:
        logger.info(f"Downloaded {total_files} new files in this check")

async def cleanup_temp_files():
    """Cleanup old temporary files"""
    logger.info("Starting temp file cleanup...")
    
    deleted_count = 0
    current_time = time.time()
    
    for file_path in config.TEMP_DIR.glob('*'):
        try:
            # Delete files older than 1 hour
            if current_time - file_path.stat().st_mtime > 3600:
                file_path.unlink()
                deleted_count += 1
        except Exception as e:
            logger.error(f"Error deleting {file_path}: {e}")
    
    # Clean database records
    db.cleanup_old_temp_files()
    
    logger.info(f"Cleaned up {deleted_count} temporary files")

def keep_alive_ping():
    """Ping own health endpoint to keep Render app awake"""
    try:
        if config.IS_RENDER and config.WEBHOOK_URL:
            health_url = config.WEBHOOK_URL.replace('/webhook', '/health')
            requests.get(health_url, timeout=5)
            logger.debug("Keep-alive ping sent")
    except Exception as e:
        logger.warning(f"Keep-alive ping failed: {e}")

# =================== GLOBAL VARIABLES ===================
application = None
bot = None

# =================== MAIN FUNCTION ===================
def run_flask():
    """Run Flask server"""
    app.run(
        host='0.0.0.0',
        port=config.PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )

async def main():
    """Main function to start the bot"""
    global application, bot
    
    logger.info("=" * 50)
    logger.info("Starting Telegram Bot...")
    logger.info(f"Environment: {'Render.com' if config.IS_RENDER else 'Local'}")
    logger.info(f"Port: {config.PORT}")
    logger.info(f"Webhook URL: {config.WEBHOOK_URL}")
    
    # Check essential configuration
    if not config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found in environment variables!")
        sys.exit(1)
    
    # Create Application
    application = Application.builder().token(config.BOT_TOKEN).build()
    bot = application.bot
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addsite", add_site_command))
    application.add_handler(CommandHandler("listsites", list_sites_command))
    application.add_handler(CommandHandler("delsite", delete_site_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("cleanup", cleanup_command))
    application.add_handler(CommandHandler("checknow", check_now_command))
    
    # Start background scheduler
    start_background_scheduler()
    
    # Configure for Render (webhook) or Local (polling)
    if config.IS_RENDER:
        logger.info("Configuring for Render.com (Webhook mode)...")
        
        # Initialize application
        await application.initialize()
        
        # Set webhook
        await application.bot.set_webhook(
            url=config.WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        logger.info(f"Webhook set to: {config.WEBHOOK_URL}")
        
        # Start application
        await application.start()
        
        # Start Flask server in a separate thread
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info(f"Flask server started on port {config.PORT}")
        
        logger.info("Bot is running on Render.com with webhook!")
        
        # Keep the application running
        while not stop_event.is_set():
            await asyncio.sleep(1)
        
    else:
        logger.info("Configuring for Local (Polling mode)...")
        
        # Start polling
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("Bot is running locally with polling!")
        
        # Keep running
        await asyncio.Event().wait()

# =================== ENTRY POINT ===================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        stop_event.set()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
