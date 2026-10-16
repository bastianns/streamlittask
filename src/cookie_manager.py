import os
import time
import json
from typing import Dict, Any, Optional
try:
    from src import storage
except ImportError:
    import storage

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_TXT_FILE = os.path.join(BASE_DIR, "tiktok_cookie.txt")


def export_cookie_to_txt_file(sessionid: str, full_cookies: Dict[str, str]) -> str:
    """
    Menyimpan cookie dalam format teks polos (plaintext) ke file tiktok_cookie.txt
    agar pengguna bisa langsung membuka atau meng-copas nilai cookie tanpa enkripsi.
    """
    cookie_str = "; ".join([f"{k}={v}" for k, v in full_cookies.items()])
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    
    # Format khusus untuk di-import langsung di ekstensi browser 'Cookie-Editor'
    cookie_editor_list = [
        {
            "domain": ".tiktok.com",
            "hostOnly": False,
            "httpOnly": (k in ["sessionid", "sessionid_ss", "sid_guard", "sid_tt"]),
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
        "# TIKTOK SESSION COOKIE (PLAINTEXT - SIAP COPAS)\n"
        f"# Waktu Simpan: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "# File ini otomatis diabaikan di .gitignore (rule: tiktok*.txt)\n"
        "# ============================================================\n\n"
        "--- [1. SESSIONID SAJA] ---\n"
        f"{sessionid}\n\n"
        "--- [2. USER-AGENT SESI INI (Wajib dicocokkan jika pakai script/bot)] ---\n"
        f"{user_agent}\n\n"
        "--- [3. COOKIE HEADER STRING (Siap Copas untuk Postman / cURL / Python)] ---\n"
        f"{cookie_str}\n\n"
        "--- [4. FORMAT JSON UNTUK EKSTENSI BROWSER 'Cookie-Editor' (Import 1-Klik di Chrome/Edge)] ---\n"
        f"{json.dumps(cookie_editor_list, indent=2)}\n\n"
        "--- [5. SELURUH COOKIE (Key-Value JSON)] ---\n"
        f"{json.dumps(full_cookies, indent=2)}\n"
    )
    try:
        with open(COOKIE_TXT_FILE, "w", encoding="utf-8") as f:
            f.write(txt_content)
    except Exception:
        pass
    return txt_content


def delete_cookie_txt_file() -> None:
    """Menghapus file tiktok_cookie.txt jika cookie dihapus."""
    if os.path.exists(COOKIE_TXT_FILE):
        try:
            os.remove(COOKIE_TXT_FILE)
        except Exception:
            pass


class CookieAuthError(Exception):
    """Exception khusus untuk error pengambilan atau penyimpanan cookie."""
    pass



def save_tiktok_cookie_session(
    sessionid: str,
    full_cookies: Optional[Dict[str, str]] = None,
    username: str = "TikTok User (Cookie)",
    days_valid: int = 30
) -> Dict[str, Any]:
    """
    Menyimpan sessionid dan cookie pendukung ke SQLite dengan enkripsi Fernet.
    Disimpan dengan nama platform 'tiktok_cookie' agar tidak menimpa OAuth resmi.
    """
    sessionid = sessionid.strip()
    if not sessionid:
        raise CookieAuthError("Nilai 'sessionid' tidak boleh kosong.")

    if full_cookies is None:
        full_cookies = {"sessionid": sessionid}
    else:
        full_cookies["sessionid"] = sessionid

    expires_at = int(time.time()) + (days_valid * 86400)
    cookies_json = json.dumps(full_cookies)

    # Memanfaatkan fungsi save_token milik storage.py:
    # - access_token diisi nilai utama 'sessionid'
    # - refresh_token diisi JSON seluruh cookies (ttwid, msToken, dll.)
    storage.save_token(
        platform="tiktok_cookie",
        account_id="cookie_session",
        username=username,
        access_token=sessionid,
        refresh_token=cookies_json,
        expires_at=expires_at,
        scopes="cookie.session"
    )

    # Ekspor otomatis ke file teks polos tiktok_cookie.txt agar mudah dicopas
    export_cookie_to_txt_file(sessionid, full_cookies)

    return {
        "platform": "tiktok_cookie",
        "username": username,
        "expires_at": expires_at,
        "txt_file": COOKIE_TXT_FILE
    }


def capture_tiktok_cookies_via_browser(timeout_seconds: int = 180) -> Dict[str, Any]:
    """
    Membuka browser Chromium lokal menggunakan Playwright.
    Menunggu pengguna login di TikTok dan otomatis mengekstrak cookie 'sessionid'.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CookieAuthError(
            "Playwright belum terinstal. Jalankan: 'pip install playwright && playwright install chromium'"
        )

    with sync_playwright() as p:
        # Gunakan headless=False dan bypass flag otomasi agar pengguna bisa melihat browser & login dengan lancar
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            # Langsung ke URL login dan gunakan 'domcontentloaded' agar tidak menunggu stream video latar belakang
            page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            # Jika timeout minor pada tracker/iklan, browser tetap terbuka dan pengguna tetap bisa login
            pass

        start_time = time.time()
        captured_cookies: Dict[str, str] = {}
        sessionid_val: Optional[str] = None

        # Looping mengecek apakah cookie 'sessionid' sudah muncul (tanda berhasil login)
        while time.time() - start_time < timeout_seconds:
            try:
                cookies_list = context.cookies()
            except Exception:
                # Browser ditutup oleh pengguna
                break

            cookie_Map = {c["name"]: c["value"] for c in cookies_list}

            if "sessionid" in cookie_Map and cookie_Map["sessionid"]:
                sessionid_val = cookie_Map["sessionid"]
                captured_cookies = cookie_Map
                break

            time.sleep(1.5)

        try:
            browser.close()
        except Exception:
            pass

        if not sessionid_val:
            raise CookieAuthError("Waktu tunggu habis atau browser ditutup sebelum login selesai.")

        return save_tiktok_cookie_session(
            sessionid=sessionid_val,
            full_cookies=captured_cookies,
            username="Akun TikTok (Browser Session)"
        )


def get_tiktok_cookie_headers() -> Dict[str, Any]:
    """
    Mengambil kembali cookie yang sudah didekripsi dari database untuk dipakai request/scraping.
    """
    record = storage.get_token_record("tiktok_cookie")
    if not record:
        raise CookieAuthError("Belum ada Cookie Session TikTok yang tersimpan.")

    sessionid = record["access_token"]
    try:
        all_cookies = json.loads(record["refresh_token"]) if record["refresh_token"] else {"sessionid": sessionid}
    except Exception:
        all_cookies = {"sessionid": sessionid}

    cookie_str = "; ".join([f"{k}={v}" for k, v in all_cookies.items()])

    # Pastikan file teks selalu tersedia
    if not os.path.exists(COOKIE_TXT_FILE):
        export_cookie_to_txt_file(sessionid, all_cookies)

    return {
        "sessionid": sessionid,
        "cookies_dict": all_cookies,
        "cookie_str": cookie_str,
        "cookie_txt_path": COOKIE_TXT_FILE,
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://tiktok.com/",
            "Cookie": cookie_str
        }
    }
