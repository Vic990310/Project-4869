import socket
import sqlite3
import re
import sys
import time
import logging
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from datetime import datetime

# 引入项目原有配置
from config import DB_PATH, CREATE_TABLE_SQL, setup_logger
from utils.parser import parse_title

# 配置日志
logger = setup_logger('scraper')

# 目标地址更新为数据站总入口
TARGET_DOMAIN = "www.sbsub.com"
TARGET_URL = "https://www.sbsub.com/data/"

def check_connectivity(host, port=443, timeout=5):
    """检查网络连通性"""
    try:
        socket.create_connection((host, port), timeout=timeout)
        logger.info(f"Target ({host}) is reachable.")
        return True
    except OSError:
        logger.error(f"Target ({host}) is unreachable.")
        return False

def init_db():
    """初始化数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    return conn

def run_scraper():
    # 1. 网络检查
    if not check_connectivity(TARGET_DOMAIN):
        return

    # 2. 初始化数据库
    logger.info("Initializing DB...")
    conn = init_db()
    cursor = conn.cursor()
    
    html_content = ""

    # 3. 启动浏览器抓取源码
    with sync_playwright() as p:
        logger.info("Launching browser (Headless Mode)...")
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        logger.info(f"Navigating to {TARGET_URL}")
        try:
            page.goto(TARGET_URL, timeout=90000)
            
            # --- 处理版权页 ---
            try:
                gate_trigger = page.get_by_text("版权声明确认", exact=False)
                page.wait_for_timeout(3000)
                
                if gate_trigger.count() > 0 and gate_trigger.first.is_visible():
                    logger.info("Handling Copyright Gate...")
                    gate_trigger.first.click()
                    page.wait_for_timeout(1000)
                    
                    agree_btn = page.get_by_text("我已认真阅读并同意以上说明", exact=False)
                    if agree_btn.count() > 0:
                        agree_btn.first.click()
                        logger.info("Clicked agree.")
                        page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"Gate warning: {e}")

            # --- 点击 TV 版的“加载全部” ---
            try:
                logger.info("Looking for TV Section 'Load All' button...")
                load_btn = page.locator("#tvcontainer .loadMore.loadA")
                
                try:
                    load_btn.wait_for(state="visible", timeout=10000)
                except:
                    logger.warning("TV Load button not immediately visible...")

                if load_btn.count() > 0 and load_btn.is_visible():
                    logger.info("Found TV Section '.loadA', clicking...")
                    load_btn.click()
                    
                    logger.info("Button clicked. Start scrolling to the bottom...")
                    last_count = 0
                    stable_checks = 0
                    
                    while True:
                        current_count = page.locator('#tvlist li.ylist-items').count()
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        
                        if current_count != last_count:
                            logger.info(f"Loaded items: {current_count} ...")
                            last_count = current_count
                            stable_checks = 0 
                            page.wait_for_timeout(3000) 
                        else:
                            stable_checks += 1
                            page.wait_for_timeout(2000)
                            if stable_checks >= 4:
                                logger.info(f"List fully loaded! Total items: {current_count}")
                                break
                else:
                    logger.warning("TV 'Load All' button not visible. Assuming page loaded or selector error.")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(3000)

            except Exception as e:
                logger.warning(f"Load/Scroll error: {e}")

            html_content = page.content()
            
        except Exception as e:
            logger.error(f"Page load failed: {e}")
        finally:
            browser.close()

    if not html_content:
        logger.error("No HTML content retrieved.")
        conn.close()
        return

    # 4. 解析与入库
    logger.info("Parsing content...")
    soup = BeautifulSoup(html_content, 'lxml')
    
    tv_list = soup.find('ul', id='tvlist')
    if not tv_list:
        logger.error("Error: <ul id='tvlist'> not found!")
        conn.close()
        return

    items = tv_list.find_all('li', class_='ylist-items')
    logger.info(f"Total items to process: {len(items)}")

    count = 0
    new_count = 0

    for item in items:
        # --- 基础信息 ---
        div_l = item.find('div', class_='resdiv-l')
        if not div_l: continue

        spans_l = div_l.find_all('span', recursive=False)
        if not spans_l: continue
            
        episode_raw = spans_l[0].get_text(strip=True)
        if not (episode_raw.isdigit() or episode_raw.upper().startswith('M') or '剧场版' in episode_raw):
            continue

        episode = episode_raw
        
        title_span = div_l.find('span', class_='restitle')
        ep_title = title_span.get_text(strip=True) if title_span else ""

        # 日期
        div_r = item.find('div', class_='resdiv-r')
        publish_date = datetime.now().strftime("%Y-%m-%d")
        if div_r:
            date_spans = div_r.find_all('span')
            if date_spans:
                date_text = date_spans[-1].get_text(strip=True)
                if re.match(r'\d{4}[-/]\d{2}[-/]\d{2}', date_text):
                    publish_date = date_text

        # --- 资源列表循环 ---
        btn_groups = div_l.find_all('div', class_='btn-group')
        
        for group in btn_groups:
            # 获取来源类型 (WEBRIP/数码重映)
            type_link = group.find('a')
            source_type_label = type_link.get_text(strip=True) if type_link else "Unknown"

            # 获取所有 input
            magnet_inputs = group.find_all('input', class_='reslink')
            
            if not magnet_inputs:
                continue

            for magnet_input in magnet_inputs:
                magnet_link = magnet_input.get('value')
                if not magnet_link: continue

                # 精准查找 Label
                detail_label = ""
                parent_flex = magnet_input.find_parent('div')
                if parent_flex:
                    parent_container = parent_flex.find_parent('div')
                    if parent_container:
                        resb_label = parent_container.find('label', class_='resb')
                        if resb_label:
                            detail_label = resb_label.get_text(strip=True)
                
                # 兜底
                if not detail_label:
                    resb_label_fallback = group.find('label', class_='resb')
                    detail_label = resb_label_fallback.get_text(strip=True) if resb_label_fallback else ""

                # --- 【关键修改】 ---
                # 直接使用 detail_label 作为存入数据库的 raw_title
                # 这样前端列表里就只会显示 "1080P·简日MP4..." 这一段干净的文字
                full_raw_title = detail_label
                
                # 为了提取 metadata，我们依然传这个字符串给 parser
                # 只要 detail_label 里包含 "1080P", "MP4" 等关键字，parser 就能正常工作
                parsed = parse_title(full_raw_title)
                
                resolution = parsed['resolution']
                container = parsed['container']
                source_type = parsed['source_type']
                
                # 如果 detail_label 里没写 WEBRIP，我们从外层按钮补救
                if not source_type and source_type_label:
                    source_type = source_type_label.upper()

                # 字幕提取
                subtitle = None
                sub_match = re.search(r'·\s*(.*?)\s*(?=MP4|MKV|AVI)', detail_label, re.IGNORECASE)
                if sub_match:
                    subtitle = sub_match.group(1).strip()
                else:
                    if "简日" in detail_label: subtitle = "简日"
                    elif "繁日" in detail_label: subtitle = "繁日"
                    elif "简繁" in detail_label: subtitle = "简繁"
                    elif "简体" in detail_label or "简" in detail_label: subtitle = "简体"
                    elif "繁体" in detail_label or "繁" in detail_label: subtitle = "繁体"

                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO magnets
                        (magnet_link, episode, episode_title, resolution, container, subtitle, source_type, raw_title, publish_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        magnet_link,
                        episode,
                        ep_title,
                        resolution,
                        container,
                        subtitle,
                        source_type,
                        full_raw_title, # 这里现在只有 detail_label
                        publish_date
                    ))
                    if cursor.rowcount > 0:
                        new_count += 1
                except Exception as e:
                    logger.error(f"DB Error: {e}")

        count += 1
        if count % 100 == 0:
            conn.commit()
            logger.info(f"Parsed {count} episodes...")

    conn.commit()
    conn.close()
    
    logger.info("="*30)
    logger.info(f"SCRAPE SUMMARY")
    logger.info(f"Total Items processed: {count}")
    logger.info(f"New Records Added: {new_count}")
    logger.info("="*30)

if __name__ == "__main__":
    try:
        run_scraper()
    except Exception as e:
        logger.exception("Fatal error in scraper process:")
        sys.exit(1)