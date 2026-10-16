import os
import time
import json
from typing import Dict, Any, Optional
try:
    from src import storage
except ImportError:
    import storage

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IG_COOKIE_TXT_FILE = os.path.join(BASE_DIR, "instagram_cookie.txt")

class IGCookieAuthError(Exception):
    """Exception khusus untuk error pengambilan atau penyimpanan cookie Instagram."""
    pass

def export_ig_cookie_to_txt_file(sessionid: str, full_cookies: Dict[str, str]) -> str:
    """
    Menyimpan cookie dalam format teks polos (plaintext) ke file instagram_cookie.txt
    agar pengguna bisa langsung membuka atau meng-copas nilai cookie tanpa enkripsi.
    """
    cookie_str = "; ".join([f"{k}={v}" for k, v in full_cookies.items()])
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    
    # Format khusus untuk di-import langsung di ekstensi browser 'Cookie-Editor'
    cookie_editor_list = [
        {
            "domain": ".instagram.com",
            "hostOnly": False,
            "httpOnly": (k in ["sessionid", "mid", "ds_user_id", "csrftoken"]),
            "name": k,
            "path": "/",
            "sameSite": "no_restriction",
            "secure": True,
            "session": False,
            "value": v
        }
        for k, v in full_cookies.items()
    ]

    txt_content = (
        "# ============================================================\n"
        "# INSTAGRAM SESSION COOKIE (PLAINTEXT - SIAP COPAS)\n"
        f"# Waktu Simpan: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "# File ini otomatis diabaikan di .gitignore\n"
        "# ============================================================\n\n"
        "--- [1. sessionid SAJA] ---\n"
        f"{sessionid}\n\n"
        "--- [2. USER-AGENT SESI INI] ---\n"
        f"{user_agent}\n\n"
        "--- [3. COOKIE HEADER STRING] ---\n"
        f"{cookie_str}\n\n"
        "--- [4. FORMAT JSON UNTUK 'Cookie-Editor'] ---\n"
        f"{json.dumps(cookie_editor_list, indent=2)}\n\n"
        "--- [5. SELURUH COOKIE (Key-Value JSON)] ---\n"
        f"{json.dumps(full_cookies, indent=2)}\n"
    )
    try:
        with open(IG_COOKIE_TXT_FILE, "w", encoding="utf-8") as f:
            f.write(txt_content)
    except Exception:
        pass
    return txt_content

def delete_ig_cookie_txt_file() -> None:
    if os.path.exists(IG_COOKIE_TXT_FILE):
        try:
            os.remove(IG_COOKIE_TXT_FILE)
        except Exception:
            pass

def save_instagram_cookie_session(
    sessionid: str,
    full_cookies: Optional[Dict[str, str]] = None,
    username: str = "Instagram User (Cookie)",
    days_valid: int = 30
) -> Dict[str, Any]:
    """
    Menyimpan sessionid dan cookie pendukung ke SQLite dengan enkripsi Fernet.
    Menggunakan platform 'instagram_cookie' agar aman terpisah dari token OAuth resmi.
    """
    sessionid = sessionid.strip()
    if not sessionid:
        raise IGCookieAuthError("Nilai cookie 'sessionid' tidak boleh kosong.")

    if full_cookies is None:
        full_cookies = {"sessionid": sessionid}
    else:
        full_cookies["sessionid"] = sessionid

    expires_at = int(time.time()) + (days_valid * 86400)
    cookies_json = json.dumps(full_cookies)

    # Memanfaatkan enkripsi storage.save_token yang sudah ada
    storage.save_token(
        platform="instagram_cookie",
        account_id="ig_cookie_session",
        username=username,
        access_token=sessionid,
        refresh_token=cookies_json,
        expires_at=expires_at,
        scopes="cookie.session"
    )

    export_ig_cookie_to_txt_file(sessionid, full_cookies)

    return {
        "platform": "instagram_cookie",
        "username": username,
        "expires_at": expires_at,
        "txt_file": IG_COOKIE_TXT_FILE
    }

def capture_instagram_cookies_via_browser(timeout_seconds: int = 180) -> Dict[str, Any]:
    """
    Membuka Chromium via Playwright, menunggu login Instagram, lalu menangkap cookie 'sessionid'.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise IGCookieAuthError(
            "Playwright belum terinstal. Jalankan: 'pip install playwright && playwright install chromium'"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            page.goto("https://instagram.com", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass

        start_time = time.time()
        captured_cookies: Dict[str, str] = {}
        sessionid_val: Optional[str] = None

        while time.time() - start_time < timeout_seconds:
            try:
                cookies_list = context.cookies()
            except Exception:
                break # Browser ditutup pengguna

            cookie_map = {c["name"]: c["value"] for c in cookies_list}

            if "sessionid" in cookie_map and cookie_map["sessionid"]:
                sessionid_val = cookie_map["sessionid"]
                captured_cookies = cookie_map
                break

            time.sleep(1.5)

        try:
            browser.close()
        except Exception:
            pass

        if not sessionid_val:
            raise IGCookieAuthError("Waktu tunggu habis atau browser ditutup sebelum login selesai.")

        return save_instagram_cookie_session(
            sessionid=sessionid_val,
            full_cookies=captured_cookies,
            username="Akun Instagram (Browser Session)"
        )

def get_instagram_cookie_headers() -> Dict[str, Any]:
    record = storage.get_token_record("instagram_cookie")
    if not record:
        raise IGCookieAuthError("Belum ada Cookie Session Instagram yang tersimpan.")

    sessionid = record["access_token"]
    try:
        all_cookies = json.loads(record["refresh_token"]) if record["refresh_token"] else {"sessionid": sessionid}
    except Exception:
        all_cookies = {"sessionid": sessionid}

    cookie_str = "; ".join([f"{k}={v}" for k, v in all_cookies.items()])

    if not os.path.exists(IG_COOKIE_TXT_FILE):
        export_ig_cookie_to_txt_file(sessionid, all_cookies)

    return {
        "sessionid": sessionid,
        "cookies_dict": all_cookies,
        "cookie_str": cookie_str,
        "cookie_txt_path": IG_COOKIE_TXT_FILE,
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://instagram.com",
            "Cookie": cookie_str
        }
    }
