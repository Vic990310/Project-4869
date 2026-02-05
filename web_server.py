
import os
import sqlite3
import asyncio
import subprocess
import requests
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

# Import existing configs
from config import DB_PATH, SBSUB_RSS_URL, setup_logger, CREATE_TABLE_SQL
# Import monitoring logic
from monitor_rss import monitor

# Logging Setup
logger = setup_logger('web_server')

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # Ensure data directory exists
    if not os.path.exists(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH))
    
    # Initialize DB
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        conn.close()
        logger.info("Database schema initialized.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Scheduler Setup
scheduler = BackgroundScheduler()

def run_rss_monitor():
    logger.info("Running scheduled RSS monitor...")
    try:
        monitor()
    except Exception as e:
        logger.error(f"RSS Monitor failed: {e}")

# Default job: Run every hour
# scheduler.add_job(run_rss_monitor, CronTrigger.from_crontab('0 * * * *'), id='rss_monitor')
scheduler.start()

class CronConfig(BaseModel):
    cron_expression: str
    enabled: bool = False

# 定义请求模型
class EmbyConfigRequest(BaseModel):
    host: str
    api_key: str
    tmdb_id: str = "30983"         # 默认柯南 ID
    max_episode: int = 1191

@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

@app.get("/api/magnets")
async def get_magnets():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM magnets ORDER BY id DESC") # Show newest first
        rows = cursor.fetchall()
        conn.close()
        
        # Determine max episode for "missing" logic
        episodes = []
        max_ep = 0
        data_map = {}
        
        for row in rows:
            item = dict(row)
            episodes.append(item)
            try:
                ep_num = int(item['episode']) if item['episode'] and item['episode'].isdigit() else 0
                if ep_num > max_ep:
                    max_ep = ep_num
                # Group by episode number
                if ep_num > 0:
                    if ep_num not in data_map:
                        data_map[ep_num] = []
                    data_map[ep_num].append(item)
            except:
                pass

        return JSONResponse(content={
            "data": episodes,
            "max_episode": max_ep,
            "grouped_by_episode": data_map
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/options")
async def get_options():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        options = {}
        # 获取四个核心维度的所有去重选项
        fields = {
            'resolution': '分辨率',
            'subtitle': '字幕',
            'source_type': '来源',
            'container': '容器'
        }
        
        for field in fields.keys():
            # Use f-string for field name is safe here because keys are hardcoded above
            cursor.execute(f"SELECT DISTINCT {field} FROM magnets WHERE {field} IS NOT NULL AND {field} != ''")
            # 过滤掉 None，转为列表
            items = [row[0] for row in cursor.fetchall() if row[0]]
            options[field] = sorted(items)
            
        conn.close()
        return options
    except Exception as e:
        logger.error(f"Get options failed: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/emby/missing")
async def check_emby_missing(config: EmbyConfigRequest):
    try:
        headers = {"X-Emby-Token": config.api_key}
        
        # 1. 获取 Series ID (优先使用 TMDB ID)
        search_params = {
            "Recursive": "true",
            "IncludeItemTypes": "Series"
        }
        
        # 强制使用 TMDB ID 查询
        if not config.tmdb_id:
             return JSONResponse({"error": "必须提供 TMDB ID"}, status_code=400)
             
        search_params["AnyProviderIdEquals"] = f"tmdb.{config.tmdb_id}"

        search_res = requests.get(
            f"{config.host}/Items",
            headers=headers,
            params=search_params,
            timeout=5
        )
        
        items = search_res.json().get('Items', [])
        if not items:
            return JSONResponse({"error": f"未找到剧集 (TMDB: {config.tmdb_id})"}, status_code=404)
        
        series_id = items[0]['Id']
        
        # 2. 获取所有集数
        ep_res = requests.get(
            f"{config.host}/Items",
            headers=headers,
            params={
                "ParentId": series_id,
                "Recursive": "true",
                "IncludeItemTypes": "Episode",
                "Fields": "IndexNumber"
            },
            timeout=10
        )
        
        existing = set()
        for item in ep_res.json().get('Items', []):
            if 'IndexNumber' in item:
                existing.add(item['IndexNumber'])
        
        # 3. 计算缺失
        full_set = set(range(1, config.max_episode + 1))
        missing = sorted(list(full_set - existing))
        
        return {"missing_episodes": missing, "total_count": len(existing)}
        
    except Exception as e:
        logger.error(f"Emby check failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.delete("/api/database")
async def clear_database():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM magnets")
        conn.commit()
        conn.close()
        logger.info("Database cleared by user request.")
        return {"status": "success", "message": "数据库已清空"}
    except Exception as e:
        logger.error(f"Failed to clear database: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/scrape/full")
async def trigger_full_scrape(background_tasks: BackgroundTasks):
    def run_scraper():
        logger.info("Starting full scrape via subprocess...")
        # Use subprocess to run the script in a separate process
        try:
            import sys
            # Capture output to ensure errors are logged even if the script crashes early
            result = subprocess.run(
                [sys.executable, "scraper_history.py"], 
                capture_output=True, 
                text=True,
                check=False
            )
            
            # stdout is usually already logged by the scraper's logger to file, 
            # but we can log it here for debug if needed, or just rely on the file.
            # However, stderr often contains crash info that didn't make it to the log file.
            if result.stdout:
                # Avoid flooding logs if stdout is huge, but here it's useful
                logger.info(f"Scraper process output: \n{result.stdout.strip()}")
            
            if result.returncode != 0:
                logger.error(f"Scraper process failed (code {result.returncode})")
                if result.stderr:
                    logger.error(f"Scraper stderr: \n{result.stderr.strip()}")
            elif result.stderr:
                # Sometimes warnings go to stderr even on success
                logger.warning(f"Scraper stderr: \n{result.stderr.strip()}")
                
        except Exception as e:
            logger.error(f"Full scrape subprocess failed: {e}")

    background_tasks.add_task(run_scraper)
    return {"message": "Full scrape triggered in background"}

@app.post("/api/rss/config")
async def configure_rss(config: CronConfig):
    try:
        # Validate cron expression
        if not config.cron_expression.strip():
            return JSONResponse(content={"error": "Cron expression cannot be empty"}, status_code=400)

        trigger = CronTrigger.from_crontab(config.cron_expression)
        
        job_id = 'rss_monitor'
        job_exists = scheduler.get_job(job_id)
        
        if config.enabled:
            if job_exists:
                scheduler.reschedule_job(job_id, trigger=trigger)
                logger.info(f"Rescheduled RSS job: {config.cron_expression}")
            else:
                scheduler.add_job(run_rss_monitor, trigger, id=job_id)
                logger.info(f"Added RSS job: {config.cron_expression}")
            return {"message": f"RSS Monitor ENABLED with schedule: {config.cron_expression}"}
        else:
            if job_exists:
                scheduler.remove_job(job_id)
                logger.info("Removed RSS job")
            return {"message": "RSS Monitor DISABLED"}
            
    except ValueError as e:
        error_msg = str(e)
        if "Wrong number of fields" in error_msg:
            friendly_msg = "Cron 表达式格式错误：应包含 5 个字段 (分 时 日 月 周)，例如 '0 * * * *'"
        else:
            friendly_msg = f"Cron 表达式无效: {error_msg}"
        
        logger.error(f"RSS Config Error: {e}")
        return JSONResponse(content={"error": friendly_msg}, status_code=400)
    except Exception as e:
        logger.error(f"RSS Config Error: {e}")
        return JSONResponse(content={"error": f"配置错误: {e}"}, status_code=400)

@app.get("/api/system/logs")
async def get_logs():
    # Read the latest logs from logs/ directory
    # Prioritize scraper.log
    
    target_log = os.path.join("logs", "scraper.log")
    if not os.path.exists(target_log):
        # Fallback to web_server.log
        target_log = os.path.join("logs", "web_server.log")
        if not os.path.exists(target_log):
             return {"logs": ["Log file not found."]}

    try:
        # Simple tail implementation
        with open(target_log, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_50 = lines[-50:]
            return {"logs": last_50}
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4869)
