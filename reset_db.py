
import sqlite3
from config import DB_PATH

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM magnets")
    conn.commit()
    conn.close()
    print("Database cleared.")
except Exception as e:
    print(f"Error clearing DB: {e}")
