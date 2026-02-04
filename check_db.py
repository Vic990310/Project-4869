
import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT episode, raw_title FROM magnets LIMIT 5")
rows = cursor.fetchall()
print("First 5 rows:")
for r in rows:
    print(r)
conn.close()
