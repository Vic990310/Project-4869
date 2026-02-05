import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Navigating to https://www.sbsub.com/data/ ...")
        await page.goto("https://www.sbsub.com/data/")
        
        # Handle copyright gate if present
        try:
            await page.click('#agree', timeout=5000)
            print("Clicked agree.")
        except:
            print("No agree button found or timeout.")
            
        print("Waiting for input.reslink...")
        try:
            await page.wait_for_selector("input.reslink", timeout=15000)
        except:
            print("Timeout waiting for input.reslink.")
            
        # Check total rows
        total_rows = await page.evaluate('document.querySelectorAll("div.resdiv-l").length')
        print(f"Total rows on page: {total_rows}")
        
        # Dump first 3 rows
        first_rows = await page.evaluate('''() => {
            const rows = document.querySelectorAll("div.resdiv-l");
            const data = [];
            for(let i=0; i<Math.min(3, rows.length); i++) {
                data.push(rows[i].innerText.substring(0, 100));
            }
            return data;
        }''')
        print("First 3 rows:")
        for r in first_rows:
            print(f"- {r}")
            
        # Try to find 'Load All' button
        load_btn = page.locator("#show_all_link") # Common ID? Or search by text.
        # Based on previous log "Clicking 'Load All'...", I likely had code for it.
        # Let's search for any element with text '全部'
        
        print("Looking for 'Load All' button...")
        # Check for '显示全部' or similar
        buttons = await page.evaluate('''() => {
            const btns = document.querySelectorAll("a, button, div.btn");
            const candidates = [];
            btns.forEach(b => {
                if (b.innerText.includes("全部") || b.innerText.includes("加载")) {
                    candidates.push({text: b.innerText, selector: b.className});
                }
            });
            return candidates;
        }''')
        print(f"Candidates for Load All: {buttons}")
        
        # Try to click the first likely candidate
        try:
            await page.click("text=加载全部", timeout=5000)
            print("Clicked '加载全部'.")
            await page.wait_for_timeout(3000) # Wait for load
        except:
            print("Could not click '加载全部'.")
            
        print("Searching for 'WEBRIP' and '984'...")
        
        # Evaluate JS to find elements containing these strings
        results = await page.evaluate('''() => {
            const rows = document.querySelectorAll("div.resdiv-l");
            const hits = [];
            
            rows.forEach(row => {
                const text = row.innerText;
                if (text.includes("984") || text.includes("983")) {
                    // Look for modal trigger buttons within the same logical block
                    const container = row.parentElement;
                    const triggers = container ? container.querySelectorAll("[data-toggle='modal'], [data-target]") : [];
                    let hasWebripBtn = false;
                    let hasVcBtn = false;
                    const triggerTexts = [];
                    triggers.forEach(t => {
                        const tx = (t.innerText || "").toUpperCase();
                        triggerTexts.push(tx);
                        if (tx.includes("WEBRIP")) hasWebripBtn = true;
                        if (tx.includes("VC")) hasVcBtn = true;
                    });
                    
                    hits.push({
                        text: text,
                        html: row.outerHTML,
                        has_webrip: text.toUpperCase().includes("WEBRIP") || hasWebripBtn,
                        has_vc: text.toUpperCase().includes("VC") || hasVcBtn,
                        trigger_texts: triggerTexts
                    });
                }
            });
            return hits;
        }''')
        
        print(f"Found {len(results)} rows for 983/984.")
        for i, hit in enumerate(results):
            print(f"--- Row {i+1} ---")
            print(f"Text: {hit['text'][:100]}...")
            print(f"Has WEBRIP: {hit['has_webrip']}")
            print(f"Has VC: {hit['has_vc']}")
            print(f"HTML snippet: {hit['html'][:200]}...")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
