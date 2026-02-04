
import requests
from config import USER_AGENT

headers = {
    'User-Agent': USER_AGENT
}

try:
    resp = requests.get("https://www.sbsub.com/rss.xml", headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Content Start: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
