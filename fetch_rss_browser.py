
import asyncio
from playwright.async_api import async_playwright
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def fetch_rss():
    async with async_playwright() as p:
        # Launch with anti-detection args
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Remove webdriver property
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        
        candidates = [
            "https://www.sbsub.com/rss.xml",
            "https://www.sbsub.com/feed/",
            "https://www.sbsub.com/atom.xml"
        ]
        
        found_content = None
        found_url = None

        for url in candidates:
            logging.info(f"Trying to fetch RSS from: {url}")
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                status = response.status
                logging.info(f"Status: {status}")
                
                if status == 200:
                    content = await page.content()
                    logging.info(f"Content length: {len(content)}")
                    logging.info(f"Content preview: {content[:500]}")
                    
                    # Check if it looks like XML/RSS
                    if "<?xml" in content or "<rss" in content or "<feed" in content:
                        logging.info(f"SUCCESS: Found valid RSS content at {url}")
                        found_content = content
                        found_url = url
                        # Get raw text content if possible (browser wraps XML in pretty print HTML sometimes)
                        try:
                            # Try to get innerText of the body, which for XML view in Chrome often contains the raw XML or the tree
                            # But page.content() gives the serialized HTML.
                            # For XML, sometimes it's better to fetch as buffer?
                            # Let's just print the first 500 chars of content
                            pass
                        except:
                            pass
                        break
                    else:
                        logging.warning(f"Content at {url} does not look like RSS.")
                else:
                    logging.warning(f"Failed to fetch {url} with status {status}")
            except Exception as e:
                logging.error(f"Error fetching {url}: {e}")
        
        if not found_content:
            logging.info("Direct access failed. Checking home page for discovery...")
            try:
                await page.goto("https://www.sbsub.com", wait_until="domcontentloaded")
                # Check <link> tags
                rss_links = await page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('link[type="application/rss+xml"], link[type="application/atom+xml"]'));
                    return links.map(l => l.href);
                }''')
                
                if rss_links:
                    logging.info(f"Discovered RSS links on home page: {rss_links}")
                    # Try the first one
                    target = rss_links[0]
                    logging.info(f"Navigating to discovered link: {target}")
                    response = await page.goto(target, wait_until="domcontentloaded")
                    if response.status == 200:
                        found_content = await page.content()
                        found_url = target
                else:
                    logging.info("No RSS links found in head.")
                    
            except Exception as e:
                logging.error(f"Error during discovery: {e}")

        if found_content:
            print(f"\n--- CONTENT FROM {found_url} ---")
            print(found_content[:1000])
            print("\n-------------------------------")
        else:
            print("FAILED to find any working RSS feed.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(fetch_rss())
