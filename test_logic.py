
import asyncio
import re
import os
from playwright.async_api import async_playwright

async def test_logic():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Load local mock file
        file_path = os.path.abspath("mock_sbsub.html")
        await page.goto(f"file:///{file_path}")
        
        print("Loaded mock page.")
        
        # --- Logic from scraper_history.py ---
        
        # 1. Row Discovery
        sample_input = page.locator("input.reslink").first
        row_selector = None
        
        if await sample_input.count() > 0:
            current = sample_input
            for i in range(10):
                parent = current.locator("..")
                if await parent.count() == 0: break
                
                text = await parent.text_content()
                text = text.strip() if text else ""
                
                # Regex for Episode ID
                if re.search(r'(?:^|\n)\s*(?:\d{3,4}|M\d+|Movie)\s+', text):
                    tag = await parent.evaluate("e => e.tagName.toLowerCase()")
                    cls = await parent.get_attribute("class")
                    if cls:
                        cls_selector = "." + ".".join(cls.split())
                        row_selector = f"{tag}{cls_selector}"
                    else:
                        row_selector = tag
                    print(f"Discovered Row Selector: {row_selector}")
                    break
                current = parent
        
        if not row_selector:
            row_selector = "div.resdiv-l" # Fallback for test if discovery fails (but it should work)
            print("Fallback selector used.")

        rows = await page.locator(row_selector).all()
        print(f"Found {len(rows)} rows.")
        
        for i, row in enumerate(rows):
            print(f"\n--- Processing Row {i+1} ---")
            
            # Extract Parent Info
            row_text = await row.text_content()
            lines = [l.strip() for l in row_text.split('\n') if l.strip()]
            if not lines: continue
            
            episode_title = lines[0]
            print(f"Parent Title: {episode_title}")
            
            # Scope Search
            inputs = await row.locator("input.reslink").all()
            for inp in inputs:
                magnet = await inp.get_attribute("value")
                
                # Context
                res_context = "Unknown"
                try:
                    # Strategy 1: Immediate Parent Text (if non-empty)
                    parent = inp.locator("..")
                    parent_text = await parent.text_content()
                    if parent_text and parent_text.strip() and len(parent_text.strip()) < 50:
                        res_context = parent_text.strip()
                    else:
                        # Strategy 2: Look for sibling/uncle label
                        # Traverse up to find a container with a label
                        current = inp
                        found_label = False
                        for _ in range(3): # Go up 3 levels max
                            parent = current.locator("..")
                            if await parent.count() == 0: break
                            
                            # Check for label in this parent
                            labels = await parent.locator("label.resb").all()
                            if labels:
                                # Found labels in this container. Use the one closest? 
                                # If multiple, this is tricky. For now, take the first one found in the closest container.
                                res_context = (await labels[0].text_content()).strip()
                                found_label = True
                                break
                            current = parent
                        
                        if not found_label:
                             # Strategy 3: Global modal body fallback (last resort)
                             modal_body = inp.locator("xpath=./ancestor::div[contains(@class, 'modal-body')]").first
                             if await modal_body.count() > 0:
                                 label = modal_body.locator("label.resb").first
                                 if await label.count() > 0:
                                     res_context = (await label.text_content()).strip()
                except:
                    pass
                
                full_title = f"{episode_title} - {res_context}"
                print(f"  Resource: {magnet}")
                print(f"  Context: {res_context}")
                print(f"  Full Title: {full_title}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_logic())
