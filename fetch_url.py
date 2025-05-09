import requests
from bs4 import BeautifulSoup
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
import pytz
import re
import subprocess

def fetch_first_stream_video():
    url = "https://www.youtube.com/@yutinghaofinance/streams"
    headers = {
        "User-Agent": "Mozilla/5.0",
    }
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"[{datetime.now()}] Failed to fetch page. Status code: {response.status_code}")
        return

    matches = re.findall(r'"url":"(/watch\?v=[\w-]+)"', response.text)

    if matches:
        video_url = "https://www.youtube.com" + matches[0]
        print(f"[{datetime.now()}] First video link: {video_url}")

        # Call send_email.py with video URL and email address
        subprocess.run(["python3", "send_email.py", video_url, ""])
    else:
        print(f"[{datetime.now()}] No video links found.")



# Scheduler setup
fetch_first_stream_video()
scheduler = BlockingScheduler(timezone=pytz.timezone('Asia/Taipei'))
scheduler.add_job(fetch_first_stream_video, 'cron', day_of_week='mon-fri', hour=9, minute=15)

print("Scheduler started. Press Ctrl+C to stop.")
try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    print("Scheduler stopped.")
