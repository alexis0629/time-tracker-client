import sqlite3
import threading
import time
import schedule
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from pynput import keyboard, mouse
import pygetwindow as gw

DB_NAME = "activity_log.db"
SERVER_URL = "http://127.0.0.1:8000/log"
USER_ID = "user123"  # this should be dynamic in real use

# Thresholds
KEYBOARD_THRESHOLD = 5
MOUSE_THRESHOLD = 5
WINDOW_THRESHOLD = 1
LOG_INTERVAL = 10  # 1 minutes in seconds

# Globals to count activity
keyboard_count = 0
mouse_click_count = 0
window_switch_count = 0
last_active_window = None

def setup_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp DATETIME,
            hours REAL,
            synced INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def log_work_session(hours=0.1):
    conn = sqlite3.connect(DB_NAME)
    japan_time = datetime.now(ZoneInfo("Asia/Tokyo"))
    c = conn.cursor()
    c.execute('''
        INSERT INTO logs (user_id, timestamp, hours, synced)
        VALUES (?, ?, ?, 0)
    ''', (USER_ID, japan_time, hours))
    conn.commit()
    conn.close()
    print(f"[LOGGED] {hours} hr at {japan_time}")

def evaluate_activity():
    global keyboard_count, mouse_click_count, window_switch_count
    print(f"[CHECK] Keys: {keyboard_count}, Mouse: {mouse_click_count}, Windows: {window_switch_count}")
    
    if (keyboard_count >= KEYBOARD_THRESHOLD and
        mouse_click_count >= MOUSE_THRESHOLD and
        window_switch_count >= WINDOW_THRESHOLD):
        log_work_session()

    # Reset counters
    keyboard_count = 0
    mouse_click_count = 0
    window_switch_count = 0

def keyboard_listener():
    def on_press(key):
        global keyboard_count
        keyboard_count += 1
    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

def mouse_listener():
    def on_click(x, y, button, pressed):
        global mouse_click_count
        if pressed:
            mouse_click_count += 1
    with mouse.Listener(on_click=on_click) as listener:
        listener.join()

def window_checker():
    global last_active_window, window_switch_count
    while True:
        try:
            active_window = gw.getActiveWindow()
            if active_window:
                current_title = active_window.title
                if current_title != last_active_window:
                    window_switch_count += 1
                    last_active_window = current_title
        except Exception:
            pass
        time.sleep(2)  # Check every 2 seconds

def sync_with_server():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, user_id, timestamp, hours FROM logs WHERE synced = 0")
    unsynced_logs = c.fetchall()

    if not unsynced_logs:
        conn.close()
        print("[SYNC] No new logs to sync.")
        return

    print(f"[SYNC] Attempting to send {len(unsynced_logs)} log(s)...")

    success_ids = []

    for log_id, user_id, timestamp, hours in unsynced_logs:
        payload = {
            "user_id": user_id,
            "timestamp": timestamp,
            "hours": hours
        }

        try:
            response = requests.post(SERVER_URL, json=payload, timeout=5)
            if response.status_code == 200:
                success_ids.append((log_id,))
        except requests.RequestException as e:
            print(f"[ERROR] Failed to sync log {log_id}: {e}")

    if success_ids:
        c.executemany("UPDATE logs SET synced = 1 WHERE id = ?", success_ids)
        conn.commit()
        print(f"[SYNC] Synced {len(success_ids)} log(s).")

    conn.close()

def main():
    setup_db()
    threading.Thread(target=keyboard_listener, daemon=True).start()
    threading.Thread(target=mouse_listener, daemon=True).start()
    threading.Thread(target=window_checker, daemon=True).start()

    schedule.every(LOG_INTERVAL).seconds.do(evaluate_activity)
    schedule.every(1).minutes.do(sync_with_server)  # adjust as needed

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
