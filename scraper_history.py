
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
        logger.info(f"Starting Bulk Extraction using selector: {row_selector}..." ) 
        
        extracted_data = await page.evaluate( f''' 
            () => {{ 
                const rows = document.querySelectorAll("{row_selector} "); 
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
                        
                        // 修正策略：从 input 往上找，只找最近的父级容器里的 label 
                        let current = input.parentElement; 
                        let html_snapshot = ""; // To debug
                        let source_type = ""; // 来源类型 (如 WEBRIP)
                        
                        // 1. 查找字幕/分辨率标签 (label.resb)
                        // 往上找最多 3 层
                        for (let i = 0; i < 3; i++) {{ 
                            if (!current || current.classList.contains("modal-body")) break;
                            
                            // Debug: Capture HTML of the parent to see what we are looking at
                            if (i == 1) html_snapshot = current.outerHTML;

                            const label = current.querySelector("label.resb"); 
                            if (label) {{ 
                                context = label.innerText.trim(); 
                                break; 
                            }} 
                            current = current.parentElement; 
                        }} 
                        
                        // 2. 查找来源类型 (Source Type)
                        // 逻辑：向上找到 .modal 容器 -> 获取 ID -> 查找 data-target="#ID" 的触发按钮
                        const modal = input.closest(".modal");
                        if (modal && modal.id) {{
                            // 查找触发该模态框的按钮
                            // 通常在同一行的 .btn-group 或类似结构中
                            // 我们在整个文档中搜索，或者在当前 item 范围内搜索
                            // 由于 ID 是唯一的，直接用 document.querySelector 最稳
                            const triggerBtn = document.querySelector(`[data-target="#${{modal.id}}"]`);
                            if (triggerBtn) {{
                                source_type = triggerBtn.innerText.trim();
                            }}
                        }}

                        // 如果上面没找到 label，再用旧策略（兜底） 
                        if (!context) {{ 
                            const modalBody = input.closest(".modal-body"); 
                            if (modalBody) {{ 
                                const labels = modalBody.querySelectorAll("label.resb"); 
                                if (labels.length === 1) context = labels[0].innerText.trim(); 
                            }} 
                        }} 
                        
                        resources.push({{ 
                            magnet: magnet, 
                            context: context,
                            source_type: source_type,
                            html_snapshot: html_snapshot
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
        ''' )
        
        logger.info(f"Bulk extraction finished. Processing {len(extracted_data)} rows in Python...")
        
        count = 0
        for row_data in extracted_data:
            row_text = row_data['row_text']
            resources = row_data['resources']
            
            if not row_text: continue
            
            # 清洗行文本
            lines = [l.strip() for l in row_text.split('\n') if l.strip()]
            if not lines: continue
            
            # 原始父级信息 (包含标题和可能的 WEBRIP 标签)
            raw_parent_line = lines[0]
            
            # --- 1. 提取纯净标题 (去除集数、日期、标签) ---
            # 先去掉开头的集数
            clean_ep_title = re.sub(r'^(?:\d+|M\d+|Movie\s*\d+|第\d+[集话])\s*', '', raw_parent_line).strip()
            # 去掉日期
            clean_ep_title = re.sub(r'\d{4}-\d{2}-\d{2}', '', clean_ep_title).strip()
            # 去掉常见的标签 (防止标题里混入 WEBRIP)
            clean_ep_title = re.sub(r'\s*(WEBRIP|HDTV|BDRIP|DVDISO)\s*', '', clean_ep_title, flags=re.IGNORECASE).strip()
            # ---------------------------

            # --- 2. 预先从父级标题提取 Source Type ---
            # (已移除：用户指出 source_type 仅存在于点击的资源标签中，不存在于父级标题)
            # ---------------------------

            for res in resources:
                magnet_link = res['magnet']
                res_context = res['context'] or "Unknown"
                
                # 获取 JS 提取的 source_type (WEBRIP等)
                extracted_source_type = res.get('source_type', '')

                # 组合完整标题 (仅用于解析集数等通用信息)
                full_raw_title = f"{raw_parent_line} - {res_context}"
                
                # 解析元数据
                parsed = parse_title(full_raw_title)
                episode = parsed.get('episode')
                resolution = parsed.get('resolution')
                subtitle = parsed.get('subtitle')
                
                # 容器格式处理
                container = parsed.get('container')
                if not container:
                    container = "MKV" if "MKV" in res_context.upper() else "MP4"

                # --- 3. 源码类型提取 ---
                # 优先使用从模态框触发按钮提取的 source_type (WEBRIP)
                # 如果没有提取到，回退到 res_context (label 内容)
                if extracted_source_type:
                    source_type = extracted_source_type
                else:
                    source_type = res_context
                # ---------------------------------

                # --- 4. 字幕语言提取 (直接提取原始中文，不进行转换) ---
                # 用户指令：抓的时候去抓磁力就近的简繁日 繁日 简日 这些
                # 覆盖 utils.parser 的结果
                subtitle = None
                # 匹配常见的字幕标记
                sub_match = re.search(r'(简繁日|简日|繁日|简繁|日文|内嵌|Chs|Cht|Big5|Jp)', res_context, re.IGNORECASE)
                if sub_match:
                    subtitle = sub_match.group(0) # 保留原始字符串 (e.g. "简日")
                else:
                    # 如果 res_context 里没找到，再回退到 parser 的结果 (但 parser 会转成 CHS_JP，可能需要处理)
                    # 用户说 "CHT_JP CHT_JP 不可读"，所以尽量不要用 parser 的 output 如果它转码了
                    # 这里如果没找到，就让它为空，或者保留 parser 的结果但要注意
                    if parsed.get('subtitle'):
                         # 如果 parser 找到了但我们没找到，可能是 regex 不全
                         # 但 parser 会归一化，我们先暂时保留 parser 的结果作为最后的 fallback
                         # 或者干脆只信赖 regex
                         pass
                
                # 如果 regex 没找到，且 parser 找到了，尝试反向映射回中文? 
                # 不，简单点，直接用 regex 抓到的。如果没有抓到，subtitle 就是 None。
                # 这样能保证数据是用户想要的 "简日" 等原始格式。
                # ---------------------------------

                # 分辨率兜底

                # 分辨率兜底
                if not resolution and "1080" in res_context: resolution = "1080P"
                if not resolution and "720" in res_context: resolution = "720P"

                # 提取发布日期
                pub_date = datetime.now().strftime("%Y-%m-%d")
                if len(lines) > 1 and re.search(r'\d{4}-\d{2}-\d{2}', lines[1]):
                    pub_date = lines[1].strip()

                # 插入数据库
                cursor.execute('''
                    INSERT OR REPLACE INTO magnets
                    (magnet_link, episode, episode_title, resolution, container, subtitle, source_type, raw_title, publish_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    magnet_link,
                    episode,
                    clean_ep_title,
                    resolution,
                    container,
                    subtitle,
                    source_type,
                    full_raw_title,
                    pub_date
                ))
                
                if cursor.rowcount > 0:
                    count += 1
                    # Print FIRST item detail as requested
                    if count == 1:
                        logger.info(f"SUCCESS! First Item Extracted:")
                        logger.info(f"  Parent Title: {raw_parent_line}")
                        logger.info(f"  Clean Title: {clean_ep_title}")
                        logger.info(f"  Resource Context: {res_context}")
                        logger.info(f"  Combined Raw Title: {full_raw_title}")
                        logger.info(f"  Magnet: {magnet_link[:50]}...")
                        logger.info(f"  Parsed Episode: {episode}")
                        logger.info(f"  Source Type: {source_type}")
                        # Log the HTML snapshot to see the structure
                        html_snapshot = res.get('html_snapshot', 'No Snapshot')
                        logger.info(f"  HTML Structure: {html_snapshot[:500]}...")

                    if count % 100 == 0:
                        conn.commit()

        conn.commit()
        logger.info(f"Scraping finished. Added {count} new items.")
        
        await browser.close()
        conn.close()

if __name__ == "__main__":
    asyncio.run(scrape())
