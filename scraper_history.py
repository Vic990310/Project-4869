
import asyncio
import sqlite3
import re
import sys
from datetime import datetime
from playwright.async_api import async_playwright
from config import DB_PATH, CREATE_TABLE_SQL, SBSUB_DATA_URL, setup_logger
from utils.parser import parse_title
import socket

# Configure logging
logger = setup_logger('scraper')

def check_connectivity(host, port=443, timeout=5):
    """
    Simple TCP connection check to verify network connectivity.
    """
    try:
        logger.info(f"Testing connectivity to {host}:{port}...")
        socket.create_connection((host, port), timeout=timeout)
        logger.info(f"Successfully connected to {host}")
        return True
    except OSError as e:
        logger.error(f"Failed to connect to {host}: {e}")
        return False

async def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    return conn

async def scrape():
    # Pre-flight Connectivity Check
    if not check_connectivity("www.google.com"):
        logger.warning("Internet connectivity (Google) check failed. You might be offline or blocked.")
    
    # Check target specifically
    if not check_connectivity("www.sbsub.com"):
        logger.error("Target (sbsub.com) is unreachable. Aborting scrape to avoid timeouts.")
        return

    logger.info("Initializing DB...")
    conn = await init_db()
    cursor = conn.cursor()

    async with async_playwright() as p:
        logger.info("Launching browser...")
        # Add anti-detection args
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            ignore_https_errors=True
        )
        page = await context.new_page()
        
        # Add webdriver property removal script
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        logger.info(f"Navigating to {SBSUB_DATA_URL}")
        try:
            # Retry logic
            for i in range(3):
                try:
                    await page.goto(SBSUB_DATA_URL, timeout=90000, wait_until='domcontentloaded')
                    logger.info("Navigation successful.")
                    break
                except Exception as e:
                    logger.warning(f"Attempt {i+1} failed: {e}")
                    if i == 2: raise e
                    await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Failed to load page: {e}")
            await browser.close()
            return

        # 1. Copyright Gate
        try:
            gate_trigger = page.locator("text=版权声明确认")
            if await gate_trigger.count() > 0:
                logger.info("Handling Copyright Gate...")
                await gate_trigger.first.click()
                await asyncio.sleep(1)
                agree_btn = page.locator("text=我已认真阅读并同意以上说明")
                if await agree_btn.count() > 0:
                    await agree_btn.first.click()
                    logger.info("Clicked agree.")
                    await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Gate error: {e}")

        # 2. Load All
        try:
            load_all_btn = page.locator("text=加载全部")
            if await load_all_btn.count() > 0 and await load_all_btn.first.is_visible():
                logger.info("Clicking 'Load All'...")
                await load_all_btn.first.click()
                logger.info("Waiting for data load...")
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Load All error: {e}")

        # 3. Row Discovery & Iteration
        logger.info("Starting Row Discovery...")
        
        # Find a sample input to discover the row structure
        sample_input = page.locator("input.reslink").first
        row_selector = None
        
        # Wait for inputs to appear
        try:
            await sample_input.wait_for(state="attached", timeout=10000)
        except:
            logger.warning("No inputs found initially.")

        if await sample_input.count() > 0:
            current = sample_input
            for i in range(10): # Traverse up to 10 levels
                parent = current.locator("..")
                if await parent.count() == 0: break
                
                # Check if this parent contains text resembling an episode title (e.g., "1190 ...")
                text = await parent.text_content()
                text = text.strip() if text else ""
                
                # Regex for Episode ID (e.g. 1190 or 1000+) at start of string or newline
                # Matches: "1190 Title", "1190\nTitle", "Movie 27..."
                if re.search(r'(?:^|\n)\s*(?:\d{3,4}|M\d+|Movie)\s+', text):
                    tag = await parent.evaluate("e => e.tagName.toLowerCase()")
                    cls = await parent.get_attribute("class")
                    if cls:
                        # Normalize class selector
                        cls_selector = "." + ".".join(cls.split())
                        row_selector = f"{tag}{cls_selector}"
                    else:
                        row_selector = tag
                    
                    logger.info(f"Discovered Row Selector: {row_selector} (Level {i+1})")
                    logger.info(f"Row Text Preview: {text[:50]}...")
                    break
                
                current = parent
        
        if not row_selector:
            logger.warning("Could not discover row selector automatically. Falling back to 'div.item, tr'.")
            row_selector = "div.item, tr" # Fallback

        # --- Bulk Extraction (JS Execution) ---
        logger.info(f"Starting Bulk Extraction using selector: {row_selector}...")
        
        extracted_data = await page.evaluate(f'''
            () => {{
                const rows = document.querySelectorAll("{row_selector}");
                const results = [];
                
                rows.forEach(row => {{
                    // Extract Row Text (Title context)
                    const fullText = row.innerText || "";
                    
                    const resources = [];
                    const inputs = row.querySelectorAll("input.reslink");
                    
                    inputs.forEach(input => {{
                        const magnet = input.value;
                        if (!magnet || !magnet.startsWith("magnet:")) return;
                        
                        let context = "";
                        
                        // Strategy 1: Immediate parent text
                        if (input.parentElement && input.parentElement.innerText && input.parentElement.innerText.trim().length < 50) {{
                            context = input.parentElement.innerText.trim();
                        }}
                        
                        // Strategy 2: Label in closest modal-body or container
                        if (!context) {{
                            const modalBody = input.closest(".modal-body") || input.parentElement.parentElement;
                            if (modalBody) {{
                                const label = modalBody.querySelector("label.resb");
                                if (label) context = label.innerText.trim();
                            }}
                        }}
                        
                        resources.push({{
                            magnet: magnet,
                            context: context
                        }});
                    }});
                    
                    if (resources.length > 0) {{
                        results.push({{
                            row_text: fullText,
                            resources: resources
                        }});
                    }}
                }});
                
                return results;
            }}
        ''')
        
        logger.info(f"Bulk extraction finished. Processing {len(extracted_data)} rows in Python...")
        
        count = 0
        for row_data in extracted_data:
            row_text = row_data['row_text']
            resources = row_data['resources']
            
            if not row_text: continue
            
            # Clean text lines
            lines = [l.strip() for l in row_text.split('\n') if l.strip()]
            if not lines: continue
            
            # Assume first line is title or contains episode ID
            episode_title = lines[0]
            
            # Try to extract Episode ID
            ep_match = re.search(r'(?:^|\s)(?:\d{3,4}|M\d+|Movie\s*\d+)', episode_title)
            if not ep_match and len(lines) > 1:
                 # Try second line if first line is empty or just a date
                 episode_title = lines[1]
            
            for res in resources:
                magnet_link = res['magnet']
                res_context = res['context'] or "Unknown"
                
                # Combine Data
                full_raw_title = f"{episode_title} - {res_context}"
                
                # Parse
                parsed = parse_title(full_raw_title)
                episode = parsed.get('episode')
                resolution = parsed.get('resolution')
                source_type = parsed.get('source_type')
                
                if not resolution and "1080" in res_context: resolution = "1080P"
                if not resolution and "720" in res_context: resolution = "720P"
                
                pub_date = datetime.now().strftime("%Y-%m-%d")

                # Insert
                cursor.execute('''
                    INSERT OR IGNORE INTO magnets (magnet_link, episode, resolution, container, subtitle, source_type, raw_title, publish_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    magnet_link,
                    episode,
                    resolution,
                    "MKV" if "MKV" in full_raw_title.upper() else "MP4",
                    "Unknown",
                    source_type,
                    full_raw_title,
                    pub_date
                ))
                if cursor.rowcount > 0:
                    count += 1
                    # Print FIRST item detail as requested
                    if count == 1:
                        logger.info(f"SUCCESS! First Item Extracted:")
                        logger.info(f"  Parent Title: {episode_title}")
                        logger.info(f"  Resource Context: {res_context}")
                        logger.info(f"  Combined Raw Title: {full_raw_title}")
                        logger.info(f"  Magnet: {magnet_link[:50]}...")
                        logger.info(f"  Parsed Episode: {episode}")

                    if count % 100 == 0:
                        conn.commit()

        conn.commit()
        logger.info(f"Scraping finished. Added {count} new items.")
        
        await browser.close()
        conn.close()

if __name__ == "__main__":
    asyncio.run(scrape())
