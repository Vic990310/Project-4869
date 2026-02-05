import os
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
DB_PATH = os.path.join(DATA_DIR, 'project4869.db')

def setup_logger(name):
    """
    Sets up a logger that writes to logs/{name}.log and the console.
    """
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Check if handlers are already added to avoid duplicates
    if not logger.handlers:
        # File Handler
        log_file = os.path.join(LOGS_DIR, f"{name}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
    return logger

SBSUB_DATA_URL = "https://www.sbsub.com/data/"
SBSUB_RSS_URL = "https://www.sbsub.com/data/rss/"

# Database Schema
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS magnets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    magnet_link TEXT UNIQUE,
    episode TEXT,
    episode_title TEXT,
    resolution TEXT,
    container TEXT,
    subtitle TEXT,
    source_type TEXT,
    raw_title TEXT,
    publish_date TEXT
);
"""

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Emby Configuration
EMBY_HOST = "http://YOUR_NAS_IP:8096" # 请替换为实际地址
EMBY_API_KEY = "YOUR_API_KEY"         # 请替换为实际 Key
EMBY_SERIES_NAME = "名侦探柯南"       # 目标剧集名称
