
import os
import sqlite3
import asyncio
import subprocess
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

# Import existing configs
from config import DB_PATH, SBSUB_RSS_URL, setup_logger
# Import monitoring logic
from monitor_rss import monitor

# Logging Setup
logger = setup_logger('web_server')

app = FastAPI()

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
scheduler.add_job(run_rss_monitor, CronTrigger.from_crontab('0 * * * *'), id='rss_monitor')
scheduler.start()

class CronConfig(BaseModel):
    cron_expression: str

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

@app.post("/api/scrape/full")
async def trigger_full_scrape(background_tasks: BackgroundTasks):
    def run_scraper():
        logger.info("Starting full scrape via subprocess...")
        # Use subprocess to run the script in a separate process
        try:
            import sys
            subprocess.run([sys.executable, "scraper_history.py"], check=False)
        except Exception as e:
            logger.error(f"Full scrape subprocess failed: {e}")

    background_tasks.add_task(run_scraper)
    return {"message": "Full scrape triggered in background"}

@app.post("/api/rss/config")
async def configure_rss(config: CronConfig):
    try:
        # Validate cron expression by creating a trigger
        trigger = CronTrigger.from_crontab(config.cron_expression)
        scheduler.reschedule_job('rss_monitor', trigger=trigger)
        return {"message": f"RSS Schedule updated to: {config.cron_expression}"}
    except Exception as e:
        return JSONResponse(content={"error": f"Invalid cron expression: {e}"}, status_code=400)

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
