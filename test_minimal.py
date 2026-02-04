
import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Starting...")
    async with async_playwright() as p:
        print("Launching...")
        browser = await p.chromium.launch(headless=True)
        print("Launched.")
        page = await browser.new_page()
        print("Page created.")
        try:
            await page.goto("https://www.google.com", timeout=10000)
            print("Google loaded.")
        except Exception as e:
            print(f"Google failed: {e}")
        
        try:
            await page.goto("https://www.sbsub.com/data/", timeout=10000)
            print("SBSUB loaded.")
        except Exception as e:
            print(f"SBSUB failed: {e}")
        
        await browser.close()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
