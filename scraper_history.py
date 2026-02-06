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

# 【修改点1】目标地址更新为数据站总入口
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
        # 【修改点2】开启无头模式 (Headless Mode)
        logger.info("Launching browser (Headless Mode)...")
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        logger.info(f"Navigating to {TARGET_URL}")
        try:
            page.goto(TARGET_URL, timeout=90000)
            
            # --- 处理版权页 (Copyright Gate) ---
            try:
                gate_trigger = page.get_by_text("版权声明确认", exact=False)
                # 无头模式下建议稍微多等一下
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
                
                # 限定在 #tvcontainer 内部查找 .loadA
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
                        # 只统计 #tvlist 下的数量
                        current_count = page.locator('#tvlist li.ylist-items').count()
                        
                        # 滚动到底部
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        
                        if current_count != last_count:
                            logger.info(f"Loaded items: {current_count} ...")
                            last_count = current_count
                            stable_checks = 0 
                            # 无头模式下渲染可能稍慢，给足时间
                            page.wait_for_timeout(3000) 
                        else:
                            logger.info(f"Count stable at {current_count}, checking again...")
                            stable_checks += 1
                            page.wait_for_timeout(2000)
                            
                            # 连续 4 次无变化则退出
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

    # 4. 解析与入库 (BeautifulSoup)
    logger.info("Parsing content...")
    soup = BeautifulSoup(html_content, 'lxml')
    
    # 精准锁定 TV 列表
    tv_list = soup.find('ul', id='tvlist')
    if not tv_list:
        logger.error("Error: <ul id='tvlist'> not found!")
        conn.close()
        return

    items = tv_list.find_all('li', class_='ylist-items')
    logger.info(f"Total items to process: {len(items)}")

    count = 0
    new_count = 0
    episodes_found = []

    for item in items:
        # --- 基础信息 ---
        div_l = item.find('div', class_='resdiv-l')
        if not div_l: continue

        spans_l = div_l.find_all('span', recursive=False)
        if not spans_l: continue
            
        episode_raw = spans_l[0].get_text(strip=True)
        
        # 简单过滤
        if not (episode_raw.isdigit() or episode_raw.upper().startswith('M') or '剧场版' in episode_raw):
            continue

        episode = episode_raw
        episodes_found.append(episode)
        
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
            magnet_input = group.find('input', class_='reslink')
            if not magnet_input: continue
                
            magnet_link = magnet_input['value']

            type_link = group.find('a')
            source_type_label = type_link.get_text(strip=True) if type_link else "Unknown"

            resb_label = group.find('label', class_='resb')
            detail_label = resb_label.get_text(strip=True) if resb_label else ""

            # 构造 raw_title
            full_raw_title = f"{episode} {ep_title} {source_type_label} {detail_label}"
            
            parsed = parse_title(full_raw_title)
            
            resolution = parsed['resolution']
            container = parsed['container']
            subtitle = parsed['subtitle']
            source_type = parsed['source_type']
            
            if not source_type and source_type_label:
                source_type = source_type_label.upper()

            if not subtitle:
                if "简日" in detail_label: subtitle = "CHS_JP"
                elif "繁日" in detail_label: subtitle = "CHT_JP"
                elif "简" in detail_label: subtitle = "CHS"
                elif "繁" in detail_label: subtitle = "CHT"

            # 入库
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
                    full_raw_title,
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
    
    # 打印总结
    logger.info("="*30)
    logger.info(f"SCRAPE SUMMARY")
    logger.info(f"Total Items in #tvlist: {len(items)}")
    if episodes_found:
        logger.info(f"Latest Episode: {episodes_found[0]}")
        logger.info(f"Oldest Episode: {episodes_found[-1]}")
    logger.info(f"New Records Added: {new_count}")
    logger.info("="*30)

if __name__ == "__main__":
    try:
        run_scraper()
    except Exception as e:
        logger.exception("Fatal error in scraper process:")
        sys.exit(1)