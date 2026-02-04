import feedparser
import sqlite3
import datetime
from config import DB_PATH, SBSUB_RSS_URL, CREATE_TABLE_SQL, USER_AGENT, setup_logger
from utils.parser import parse_title

# Configure logging
logger = setup_logger('monitor')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    return conn

def monitor():
    conn = init_db()
    cursor = conn.cursor()

    logger.info(f"Fetching RSS feed from {SBSUB_RSS_URL}")
    
    # Use agent to avoid 403
    feed = feedparser.parse(SBSUB_RSS_URL, agent=USER_AGENT)

    if feed.bozo:
        logger.error(f"Error parsing RSS feed: {feed.bozo_exception}")
        return

    logger.info(f"Found {len(feed.entries)} entries.")
    
    new_count = 0
    for entry in feed.entries:
        raw_title = entry.title
        magnet_link = None

        # Try to find magnet link
        if hasattr(entry, 'link') and entry.link.startswith('magnet:'):
            magnet_link = entry.link
        elif hasattr(entry, 'enclosures'):
            for enc in entry.enclosures:
                if enc.get('type') == 'application/x-bittorrent' or enc.get('href', '').startswith('magnet:'):
                    magnet_link = enc.get('href')
                    break
        
        if not magnet_link:
            # logger.debug(f"No magnet link found for {raw_title}")
            continue

        # Check if exists
        cursor.execute("SELECT id FROM magnets WHERE magnet_link = ?", (magnet_link,))
        if cursor.fetchone():
            continue

        # Parse
        parsed = parse_title(raw_title)
        
        # Publish date
        pub_date = datetime.datetime.now().isoformat()
        if hasattr(entry, 'published'):
            pub_date = entry.published

        try:
            cursor.execute("""
                INSERT INTO magnets 
                (magnet_link, episode, resolution, container, subtitle, source_type, raw_title, publish_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                magnet_link, 
                parsed['episode'], 
                parsed['resolution'], 
                parsed['container'], 
                parsed['subtitle'], 
                parsed['source_type'], 
                raw_title,
                pub_date
            ))
            new_count += 1
            logger.info(f"Added new: {raw_title}")
        except sqlite3.IntegrityError:
            pass # Already exists (double check)
        except Exception as e:
            logger.error(f"Error inserting {raw_title}: {e}")

    conn.commit()
    conn.close()
    logger.info(f"RSS check finished. Added {new_count} new items.")

if __name__ == "__main__":
    monitor()
