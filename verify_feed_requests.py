
import requests
from config import USER_AGENT

url = "https://www.sbsub.com/data/rss/"
headers = {
    'User-Agent': USER_AGENT
}

try:
    print(f"Fetching {url}...")
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Headers: {resp.headers.get('content-type')}")
    print(f"Content Preview: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
