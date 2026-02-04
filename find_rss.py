
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating...")
        page.goto("https://www.sbsub.com", wait_until="domcontentloaded")
        print(f"Page Title: {page.title()}")
        
        # Look for RSS links
        links = page.query_selector_all("a")
        print(f"Found {len(links)} links")
        for link in links:
            href = link.get_attribute("href")
            if href and ("rss" in href or "xml" in href or "feed" in href):
                print(f"Found potential RSS link: {href}")
        
        # Also check head
        head_links = page.query_selector_all("link[type='application/rss+xml']")
        for link in head_links:
             print(f"Found Head RSS: {link.get_attribute('href')}")

        browser.close()

if __name__ == "__main__":
    run()
