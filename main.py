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
SAVE_DIR = "IMAGES"
FAILED_JSON = "failed.json"

ASTC_URL = "https://dl.cdn.freefiremobile.com/advance/ABHotUpdates/IconCDN/android/{}_rgb.astc"
ASTC2PNG_URL = "https://astc2png.deaddos.online/"

# High speed settings for GitHub Runner
MAX_WORKERS = 20        
RETRIES = 3
TIMEOUT = 25
SLEEP_FAIL = 1
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Origin": "https://astc2png.deaddos.online",
    "Referer": "https://astc2png.deaddos.online/"
}

IMG_PATTERN = re.compile(r'src="data:image/png;base64,([^"]+)"')

os.makedirs(SAVE_DIR, exist_ok=True)
failed_items = []

# Thread-local storage for sessions
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
    
    # Agar image pehle se hai, toh skip karo (Time bachane ke liye)
    if os.path.exists(png_path):
        return None 

    try:
        session = get_session()

        # 1. Download ASTC
        r = session.get(ASTC_URL.format(item_id), timeout=TIMEOUT)
        if r.status_code != 200:
            raise Exception(f"ASTC HTTP {r.status_code}")

        # 2. Convert to PNG
        files = {"files": (f"{item_id}.astc", r.content, "application/octet-stream")}
        resp = session.post(ASTC2PNG_URL, files=files, headers=HEADERS, timeout=TIMEOUT)

        if resp.status_code != 200:
            raise Exception(f"CONVERT HTTP {resp.status_code}")

        match = IMG_PATTERN.search(resp.text)
        if not match:
            raise Exception("PNG DATA NOT FOUND")

        # 3. Save Image
        img_data = base64.b64decode(match.group(1))
        with Image.open(io.BytesIO(img_data)) as img:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            img.save(png_path, optimize=True, quality=95)

        return f"✅ {item_id}.png"

    except Exception as e:
        failed_items.append({
            "itemID": item_id,
            "error": str(e)
        })
        time.sleep(SLEEP_FAIL)
        return f"❌ {item_id} | {str(e)}"

def main():
    if not os.path.exists(OB52_JSON):
        print(f"File {OB52_JSON} not found!")
        exit(1)

    with open(OB52_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    item_ids = [str(i["itemID"]) for i in data if "itemID" in i]
    item_ids.sort()

    print(f"\n🚀 STARTING JOB: {len(item_ids)} Items")
    print(f"⚡ MAX WORKERS: {MAX_WORKERS}\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_convert, item_id) for item_id in item_ids]
        
        for future in as_completed(futures):
            res = future.result()
            if res:
                print(res)

    # Save failed list (overwrite old failed.json only if errors exist)
    if failed_items:
        with open(FAILED_JSON, "w", encoding="utf-8") as f:
            json.dump(failed_items, f, indent=2)
        print(f"\n⚠️ Failed items saved to: {FAILED_JSON}")
    else:
        # Agar koi fail nahi hua, toh purana failed.json hata do (clean cleanup)
        if os.path.exists(FAILED_JSON):
            os.remove(FAILED_JSON)
    
    print("\n🔥 ALL DONE")

if __name__ == "__main__":
    main()
