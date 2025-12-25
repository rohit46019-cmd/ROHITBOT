# ROHITBOT# 🤖 **Auto Download Telegram Bot**

## 📌 **Project Overview**
A private Telegram bot that automatically monitors websites for new videos/PDFs, downloads them, and sends to specified Telegram groups with auto-delete functionality.

## 🚀 **Features**

### **Core Features**
- ✅ **Auto Website Monitoring**: Checks websites at regular intervals
- ✅ **Multi-Format Support**: Downloads videos (MP4, AVI, MKV) and PDFs
- ✅ **Group-Specific Folders**: Sends files to different groups in organized folders
- ✅ **Backlog Download**: Downloads existing content from past dates
- ✅ **Auto-Deletion**: Commands and status messages auto-delete after configurable time
- ✅ **Private Bot**: Only owner can use, others are ignored
- ✅ **Render.com Optimized**: Ready for deployment with all fixes

### **Advanced Features**
- 📁 **Smart Organization**: Files organized by date/type/category
- 🔒 **Security**: Owner-only access with intrusion logging
- 🗑️ **Storage Management**: Automatic cleanup of temp files
- ⚡ **Large File Support**: Splits files >50MB for Telegram limits
- 📊 **Progress Tracking**: Real-time download status
- 🔄 **Error Recovery**: Auto-retry failed downloads

## 📂 **File Structure**
```
telegram-auto-download-bot/
├── main.py                 # Main bot application
├── requirements.txt        # Python dependencies
├── Procfile               # Render process definitions
├── runtime.txt            # Python version
├── .env                   # Environment variables (template)
├── data/                  # Database and persistent data
├── tmp/                   # Temporary download files
├── logs/                  # Application logs
└── README.md              # This file
```

## ⚙️ **Environment Variables**

### **Required Variables**
| Variable | Description | Example |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram Bot Token from @BotFather | `123456:ABC-DEF1234` |
| `OWNER_ID` | Your Telegram User ID | `123456789` |
| `PORT` | Port for web server (Render auto-sets) | `10000` |
| `RENDER` | Set to `true` on Render | `true` |
| `RENDER_EXTERNAL_URL` | Your Render app URL | `https://your-bot.onrender.com` |

### **Optional Variables**
| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_DELETE_TIME` | `5` | Seconds before bot messages auto-delete |
| `CHECK_INTERVAL` | `1800` | Seconds between website checks (30 min) |
| `MAX_FILE_SIZE` | `2000000000` | Max file size in bytes (2GB) |
| `TEMP_CLEANUP_INTERVAL` | `3600` | Seconds between temp cleanups (1 hour) |
| `WEBHOOK_URL` | Auto-generated | Webhook URL for Telegram |
| `WEBHOOK_PORT` | Same as PORT | Port for webhook |

### **Example .env file**
```env
# Required
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
OWNER_ID=123456789

# Render Specific
PORT=10000
RENDER=true
RENDER_EXTERNAL_URL=https://your-bot.onrender.com

# Bot Configuration
AUTO_DELETE_TIME=5
CHECK_INTERVAL=1800
MAX_FILE_SIZE=2000000000

# Advanced
TEMP_CLEANUP_INTERVAL=3600
LOG_LEVEL=INFO
```

## 🛠️ **Setup Instructions**

### **Local Development**
```bash
# 1. Clone repository
git clone https://github.com/yourusername/telegram-auto-download-bot.git
cd telegram-auto-download-bot

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 5. Run bot
python main.py
```

### **Render.com Deployment**
1. **Push to GitHub**: Upload all files to a GitHub repository
2. **Create Render Service**:
   - Go to [render.com](https://render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
3. **Configure**:
   - **Name**: `telegram-bot` (or your choice)
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
4. **Set Environment Variables** in Render dashboard:
   - `BOT_TOKEN`: Your bot token
   - `OWNER_ID`: Your Telegram ID
   - `RENDER`: `true`
5. **Deploy**: Click "Create Web Service"

## 🤖 **Bot Commands**

### **Basic Commands**
| Command | Description | Usage |
|---------|-------------|-------|
| `/start` | Initialize bot | `/start` |
| `/help` | Show help message | `/help` |
| `/myid` | Get your user ID | `/myid` |
| `/groupid` | Get group ID | `/groupid` |
| `/status` | Bot status | `/status` |

### **Website Management**
| Command | Description | Usage |
|---------|-------------|-------|
| `/addsite` | Add new website | `/addsite <url> <folder> <types>` |
| `/listsites` | List all websites | `/listsites` |
| `/editsite` | Edit website | `/editsite <id> <setting> <value>` |
| `/removesite` | Remove website | `/removesite <id>` |

### **Download Control**
| Command | Description | Usage |
|---------|-------------|-------|
| `/backlog` | Download existing content | `/backlog [website_id]` |
| `/download` | Manual download | `/download <url>` |
| `/pause` | Pause monitoring | `/pause` |
| `/resume` | Resume monitoring | `/resume` |
| `/checknow` | Check now | `/checknow` |

### **System Commands**
| Command | Description | Usage |
|---------|-------------|-------|
| `/cleanup` | Clean temp files | `/cleanup` |
| `/logs` | View logs | `/logs [lines]` |
| `/restart` | Restart bot | `/restart` |
| `/stop` | Stop bot | `/stop` |

## 🔧 **How to Customize**

### **1. Change Check Interval**
```python
# In .env file
CHECK_INTERVAL=900  # 15 minutes in seconds
```

### **2. Add New File Types**
```python
# In main.py, modify is_valid_file function
def is_valid_file(self, url, file_types):
    # Add new extensions here
    allowed_extensions = ['.mp4', '.avi', '.mkv', '.pdf', '.mp3', '.zip']
    return any(url.lower().endswith(ext) for ext in allowed_extensions)
```

### **3. Change Organization Structure**
```python
# Modify create_organized_path function in main.py
def create_organized_path(base_folder, file_date, file_type, file_name):
    # Example: Year/Month/Day/Type/Filename
    return f"{base_folder}/{file_date.year}/{file_date.month:02d}/{file_date.day:02d}/{file_type}/{file_name}"
```

### **4. Add Authentication for Websites**
```python
# In WebsiteMonitor class, add:
def __init__(self):
    self.session = requests.Session()
    self.session.auth = ('username', 'password')  # Basic auth
    # OR for cookies:
    self.session.cookies.update({'session_id': 'your_cookie'})
```

### **5. Customize Telegram Captions**
```python
# In send_file_to_group method
caption = f"""
📁 {file_name}
📅 {current_date}
📦 {file_size_mb} MB
🔗 {website_name}

#AutoDownload #{folder_name}
"""
```

## 🌐 **Website Configuration Examples**

### **1. Simple Directory Listing**
```
Website URL: https://example.com/files/
File Types: mp4,pdf
Folder Name: example_files
Group: @MyGroup
```

### **2. WordPress Blog with Downloads**
```
Website URL: https://blog.com/downloads/
CSS Selector: .download-link
File Types: pdf,docx
Folder Name: blog_docs
```

### **3. Video Sharing Site**
```
Website URL: https://videos.com/channel/
Pattern: *watch?v=*
File Types: mp4
Folder Name: video_channel
```

## 📊 **Database Schema**

### **Websites Table**
```sql
CREATE TABLE websites (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE,
    name TEXT,
    group_id TEXT,
    folder TEXT,
    file_types TEXT,
    check_interval INTEGER,
    last_checked DATETIME,
    created_at DATETIME
);
```

### **Files Table**
```sql
CREATE TABLE downloaded_files (
    id INTEGER PRIMARY KEY,
    website_id INTEGER,
    file_url TEXT UNIQUE,
    file_name TEXT,
    file_size INTEGER,
    downloaded_at DATETIME,
    sent_to_group BOOLEAN
);
```

### **Groups Table**
```sql
CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    group_id TEXT UNIQUE,
    group_name TEXT,
    folder_name TEXT,
    settings TEXT
);
```

## 🔍 **Troubleshooting**

### **Common Issues**

#### **1. Bot Doesn't Start on Render**
```bash
# Check logs for:
- BOT_TOKEN not set: Set in Environment Variables
- PORT not found: Ensure PORT=10000 is set
- Import errors: Check requirements.txt
```

#### **2. Webhook Errors**
```bash
# Solution:
1. Set RENDER_EXTERNAL_URL correctly
2. Run: /setwebhook on @BotFather
3. Wait 5 minutes for propagation
```

#### **3. File Download Fails**
```bash
# Possible causes:
- Website blocking: Add User-Agent in headers
- File too large: Adjust MAX_FILE_SIZE
- Connection timeout: Increase timeout in code
```

#### **4. Storage Full on Render**
```bash
# Free tier has 512MB RAM, 1GB storage
Solutions:
1. Run /cleanup command
2. Reduce temp file retention
3. Delete old logs
```

#### **5. Bot Ignores Commands**
```bash
# Check:
1. OWNER_ID is correct
2. Bot is not in privacy mode
3. Command format is correct
```

### **Debug Commands**
```bash
# Check if bot is running
curl https://your-bot.onrender.com/health

# View recent logs
curl https://your-bot.onrender.com/logs

# Test website connection
curl https://your-bot.onrender.com/test?url=example.com
```

## 📝 **Logging System**

### **Log Files**
- `logs/bot.log` - Main application log
- `logs/errors.log` - Error log
- `logs/downloads.log` - Download history
- `logs/access.log` - User access log

### **Log Levels**
```python
# In .env
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### **View Logs**
```bash
# Via Telegram
/logs 50  # Last 50 lines

# Via API
GET /api/logs?type=bot&lines=100
```

## 🔄 **Update Instructions**

### **Update Bot Code**
```bash
# 1. Pull latest changes
git pull origin main

# 2. Update dependencies
pip install -r requirements.txt

# 3. Restart bot
/restart  # Via Telegram
# OR
systemctl restart bot  # On server
```

### **Update on Render**
```bash
# Just push to GitHub
git add .
git commit -m "Update bot"
git push origin main
# Render auto-deploys
```

## 📞 **Support**

### **Get Help**
1. **Check Logs**: `/logs` command
2. **View Status**: `/status` command
3. **Test Connection**: `/test` command
4. **Reset Bot**: `/reset` command

### **Contact**
- **Telegram**: @YourUsername
- **Issues**: [GitHub Issues](https://github.com/yourusername/repo/issues)
- **Documentation**: [Wiki](https://github.com/yourusername/repo/wiki)

## 📄 **License**
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**
- [python-telegram-bot](https://github.com/python-telegram-bot) for Telegram API wrapper
- [Render.com](https://render.com) for hosting
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for web scraping

---

## 🎯 **Quick Start Summary**

### **For Beginners**
1. Create bot on @BotFather
2. Get your User ID via @userinfobot
3. Deploy to Render.com with one click
4. Use `/addsite` to add first website
5. Use `/backlog` to download existing files

### **For Developers**
```bash
# Clone, configure, deploy
git clone <repo>
cd telegram-auto-download-bot
cp .env.example .env
# Edit .env
pip install -r requirements.txt
python main.py
```

### **Production Ready**
- ✅ Error handling
- ✅ Logging
- ✅ Security
- ✅ Auto-scaling
- ✅ Backup system

---

**⭐ If you like this project, please star it on GitHub!**

**🔄 Last Updated**: March 2024  
**🐍 Python Version**: 3.11+  
**📦 Dependencies**: See requirements.txt  
**🏗️ Architecture**: Async + Flask + SQLite  
**☁️ Hosting**: Render.com (Free tier compatible)

---

**Note**: This bot is designed for personal use. Respect website terms of service and copyright laws. Use responsibly.
