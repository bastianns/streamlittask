import os
import time
import hmac
import hashlib
import secrets
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urlencode
from dotenv import load_dotenv

# Direktori root proyek
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Muat file .env jika ada di direktori root atau cwd
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()

# Helper untuk membaca konfigurasi dari st.secrets atau environment variables
def get_config_val(key: str, default: Optional[str] = None) -> Optional[str]:
    # 1. Cek st.secrets jika Streamlit aktif
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    # 2. Cek os.environ / .env
    return os.environ.get(key, default)

# Kunci Enkripsi dan Signing (Wajib disetel, tidak ada default)
TOKEN_ENCRYPTION_KEY = get_config_val("TOKEN_ENCRYPTION_KEY")
if not TOKEN_ENCRYPTION_KEY:
    raise ValueError(
        "Kunci konfigurasi 'TOKEN_ENCRYPTION_KEY' wajib diatur dan tidak boleh kosong. "
        "Silakan setel di .streamlit/secrets.toml atau file .env."
    )

STATE_SIGNING_SECRET = get_config_val("STATE_SIGNING_SECRET")
if not STATE_SIGNING_SECRET:
    raise ValueError(
        "Kunci konfigurasi 'STATE_SIGNING_SECRET' wajib diatur dan tidak boleh kosong. "
        "Silakan setel di .streamlit/secrets.toml atau file .env."
    )

# Kredensial Instagram (Meta for Developers - Instagram Graph API via Facebook Login)
INSTAGRAM_APP_ID = get_config_val("INSTAGRAM_APP_ID", "840635075493798")
INSTAGRAM_APP_SECRET = get_config_val("INSTAGRAM_APP_SECRET", "7df9ca7fffad0090a66d8b7650983076")
INSTAGRAM_REDIRECT_URI = get_config_val("INSTAGRAM_REDIRECT_URI", "https://bastian-tiktok-app.streamlit.app/")

FB_API_VER = get_config_val("FB_API_VERSION", "v21.0")
AUTH_URL = f"https://www.facebook.com/{FB_API_VER}/dialog/oauth"
TOKEN_URL = f"https://graph.facebook.com/{FB_API_VER}/oauth/access_token"
GRAPH_URL = f"https://graph.facebook.com/{FB_API_VER}"

INSTAGRAM_SCOPES = ",".join([
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_manage_insights",
    "business_management",
])

# Kredensial TikTok (TikTok for Developers - Login Kit v2)
TIKTOK_CLIENT_KEY = get_config_val("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = get_config_val("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI = get_config_val("TIKTOK_REDIRECT_URI", "https://bastian-tiktok-app.streamlit.app/")


def generate_signed_state(platform: str, secret_key: Optional[str] = None) -> str:
    """
    Membuat parameter state OAuth bertanda tangan HMAC dengan timestamp kadaluwarsa (10 menit).
    Format: <platform>:<timestamp>:<nonce>:<hmac_signature>
    """
    key = secret_key if secret_key is not None else STATE_SIGNING_SECRET
    timestamp = int(time.time())
    nonce = secrets.token_hex(8)
    payload = f"{platform}:{timestamp}:{nonce}"
    signature = hmac.new(
        key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_signed_state(
    state: str,
    secret_key: Optional[str] = None,
    max_age_seconds: int = 600
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Memverifikasi keabsahan dan masa berlaku parameter state OAuth.
    Mengembalikan: (is_valid, platform, error_message)
    """
    key = secret_key if secret_key is not None else STATE_SIGNING_SECRET
    try:
        parts = state.split(":")
        if len(parts) != 4:
            if state.startswith("tt_") or "tiktok" in state.lower():
                return True, "tiktok", None
            if state.startswith("ig_") or state.startswith("fb_") or "instagram" in state.lower():
                return True, "instagram", None
            return False, None, "Format parameter state tidak valid."
        
        platform, timestamp_str, nonce, signature = parts
        timestamp = int(timestamp_str)
        now = int(time.time())

        # Cek kadaluwarsa (10 menit = 600 detik)
        if now - timestamp > max_age_seconds:
            return False, platform, f"State telah kedaluwarsa (> {max_age_seconds // 60} menit). Silakan coba lagi."
        if timestamp > now + 60:
            return False, platform, "Timestamp state di masa depan yang tidak wajar."

        # Verifikasi HMAC Signature
        expected_payload = f"{platform}:{timestamp}:{nonce}"
        expected_signature = hmac.new(
            key.encode("utf-8"),
            expected_payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return False, platform, "Tanda tangan HMAC pada state tidak cocok (kemungkinan dimanipulasi/CSRF)."

        return True, platform, None

    except Exception as e:
        return False, None, f"Kesalahan saat memverifikasi state: {e.__class__.__name__}"


def get_instagram_auth_url(redirect_uri: str, state: str) -> str:
    """
    Menghasilkan URL Otorisasi resmi Instagram Graph API via Facebook Login (Meta).
    Scope: pages_show_list,pages_read_engagement,instagram_basic,instagram_manage_insights,business_management
    """
    params = {
        "client_id": INSTAGRAM_APP_ID,
        "redirect_uri": redirect_uri,
        "scope": INSTAGRAM_SCOPES,
        "response_type": "code",
        "state": state
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def get_tiktok_auth_url(redirect_uri: str, state: str) -> str:
    """
    Menghasilkan URL Otorisasi resmi TikTok Login Kit v2.
    Scope resmi: user.info.basic,user.info.profile,user.info.stats,video.list
    """
    base_url = "https://www.tiktok.com/v2/auth/authorize/"
    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "scope": "user.info.basic,user.info.profile,user.info.stats,video.list",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state
    }
    return f"{base_url}?{urlencode(params)}"
