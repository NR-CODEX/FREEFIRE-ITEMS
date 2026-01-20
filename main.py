import os
import json
import requests
import base64
import io
import re
import time
import threading
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================= CONFIG =================
OB52_JSON = "OB52.json"
SAVE_DIR = "IMAGE"

ASTC_URL = "https://dl.cdn.freefiremobile.com/live/ABHotUpdates/IconCDN/android/{}_rgb.astc"
ASTC2PNG_URL = "https://astc2png.deaddos.online/"

MAX_WORKERS = 20
RETRIES = 3
TIMEOUT = 25
SLEEP_FAIL = 1
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://astc2png.deaddos.online",
    "Referer": "https://astc2png.deaddos.online/"
}

IMG_PATTERN = re.compile(r'src="data:image/png;base64,([^"]+)"')

os.makedirs(SAVE_DIR, exist_ok=True)
thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        retry = Retry(
            total=RETRIES,
            connect=RETRIES,
            read=RETRIES,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
        session.mount("https://", adapter)
        thread_local.session = session
    return thread_local.session

def download_convert(item_id):
    png_path = os.path.join(SAVE_DIR, f"{item_id}.png")

    try:
        session = get_session()

        # 1️⃣ Always download latest ASTC
        r = session.get(ASTC_URL.format(item_id), timeout=TIMEOUT)
        if r.status_code != 200:
            raise Exception(f"ASTC {r.status_code}")

        # 2️⃣ Always convert
        files = {"files": (f"{item_id}.astc", r.content)}
        resp = session.post(ASTC2PNG_URL, files=files, headers=HEADERS, timeout=TIMEOUT)

        match = IMG_PATTERN.search(resp.text)
        if not match:
            raise Exception("PNG DATA NOT FOUND")

        # 3️⃣ Always overwrite PNG
        img_data = base64.b64decode(match.group(1))
        with Image.open(io.BytesIO(img_data)) as img:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            img.save(png_path, optimize=True)

        return f"🔄 UPDATED {item_id}.png"

    except Exception as e:
        time.sleep(SLEEP_FAIL)
        return f"❌ {item_id} | FAILED"

def main():
    if not os.path.exists(OB52_JSON):
        print("OB52.json not found!")
        return

    with open(OB52_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    item_ids = [str(i["itemID"]) for i in data if "itemID" in i]

    print(f"\n🚀 FORCE UPDATE MODE")
    print(f"📦 TOTAL ITEMS: {len(item_ids)}")
    print(f"⚡ WORKERS: {MAX_WORKERS}")
    print("♻️ SKIP: OFF | OVERWRITE: ON | LATEST: ON\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_convert, item_id) for item_id in item_ids]

        for future in as_completed(futures):
            print(future.result())

    print("\n🔥 ALL ITEMS UPDATED WITH LATEST FILES")

if __name__ == "__main__":
    main()
