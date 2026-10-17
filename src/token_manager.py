import os
import json
import time
import requests
from typing import Dict, Any, Optional
try:
    from src import storage
    from src.config import (
        INSTAGRAM_APP_ID,
        INSTAGRAM_APP_SECRET,
        TIKTOK_CLIENT_KEY,
        TIKTOK_CLIENT_SECRET,
        FB_API_VER,
        TOKEN_URL,
        GRAPH_URL,
        INSTAGRAM_SCOPES,
    )
except ImportError:
    import storage
    from config import (
        INSTAGRAM_APP_ID,
        INSTAGRAM_APP_SECRET,
        TIKTOK_CLIENT_KEY,
        TIKTOK_CLIENT_SECRET,
        FB_API_VER,
        TOKEN_URL,
        GRAPH_URL,
        INSTAGRAM_SCOPES,
    )


class OAuthError(Exception):
    """Exception khusus untuk error autentikasi OAuth."""
    pass


def _clean_error_message(msg: Any) -> str:
    """
    Membersihkan pesan error dari kemungkinan kebocoran URL, query params, atau token.
    Memotong URL dan membatasi panjang pesan.
    """
    if not msg:
        return "Unknown error"
    text = str(msg)
    if "?" in text:
        text = text.split("?")[0]
    # Samarkan nilai rahasia ASLI jika sampai muncul. Pesan error dari provider
    # (misalnya "client_secret is incorrect") tetap ditampilkan supaya bisa didiagnosis.
    for secret in (INSTAGRAM_APP_SECRET, TIKTOK_CLIENT_SECRET):
        if secret:
            text = text.replace(secret, "***")
    return text[:200]


def _tiktok_token_payload(res_json: Any) -> Dict[str, Any]:
    """
    Respons token TikTok Login Kit v2 berbentuk DATAR (access_token, open_id, dst. di level atas),
    tanpa pembungkus "data". Bentuk terbungkus tetap diterima untuk berjaga-jaga.
    Mengembalikan {} jika respons bukan token yang valid.
    """
    if not isinstance(res_json, dict):
        return {}
    if res_json.get("access_token"):
        return res_json
    wrapped = res_json.get("data")
    if isinstance(wrapped, dict) and wrapped.get("access_token"):
        return wrapped
    return {}


def _extract_tiktok_error(res_json: Any) -> str:
    """Mengekstrak pesan error dari berbagai kemungkinan format respon API TikTok."""
    if not isinstance(res_json, dict):
        return str(res_json)[:200]
    
    # 1. Cek data.description (format resmi TikTok Display API / Login Kit v2)
    data = res_json.get("data")
    if isinstance(data, dict):
        desc = data.get("description")
        err_code = data.get("error_code")
        if desc:
            return f"{desc} (code: {err_code})" if err_code else str(desc)

    # 2. Cek error.message atau error.code
    err = res_json.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        code = err.get("code")
        if msg and code and code != "ok":
            return f"{code}: {msg}"
        elif msg:
            return str(msg)
        elif code and code != "ok":
            return f"Error code: {code}"
    elif isinstance(err, str) and err:
        desc = res_json.get("error_description")
        return f"{err}: {desc}" if desc else err

    # 3. Cek error_description atau message di level root
    if res_json.get("error_description"):
        return str(res_json["error_description"])
    if res_json.get("message"):
        return str(res_json["message"])

    # Jangan cetak isi respons (bisa memuat token); cukup nama kunci untuk diagnosis.
    return f"Respon TikTok tidak dikenali (kunci: {', '.join(list(res_json.keys())[:8])})"


INSTAGRAM_TOKEN_JSON_FILE = os.path.join(storage.BASE_DIR, "token.json")


def export_instagram_token_to_json(
    access_token: str,
    expires_in: int = 5184000,
    token_type: str = "bearer"
) -> str:
    """Menyimpan token Instagram ke token.json (format kompatibel dengan Archive)."""
    data = {
        "access_token": access_token,
        "expires_in": expires_in,
        "token_type": token_type
    }
    try:
        with open(INSTAGRAM_TOKEN_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
    return INSTAGRAM_TOKEN_JSON_FILE


def delete_instagram_token_file() -> None:
    """Menghapus file token.json saat disconnect."""
    if os.path.exists(INSTAGRAM_TOKEN_JSON_FILE):
        try:
            os.remove(INSTAGRAM_TOKEN_JSON_FILE)
        except Exception:
            pass


def save_manual_instagram_token(
    access_token: str,
    expires_in: int = 5184000,
    token_type: str = "bearer"
) -> Dict[str, Any]:
    """
    Menyimpan token Instagram yang diinput secara manual atau dari file token.json.
    Secara otomatis mengambil detail Instagram Business Account via Facebook Graph API.
    """
    clean_token = access_token.strip()
    if not clean_token:
        raise OAuthError("Token Instagram tidak boleh kosong.")

    ig_id = None
    username = "Instagram Business"
    try:
        pages_resp = requests.get(
            f"{GRAPH_URL}/me/accounts",
            params={"access_token": clean_token, "fields": "id,name,instagram_business_account"},
            timeout=15
        )
        if pages_resp.status_code == 200:
            pages = pages_resp.json().get("data", [])
            for page in pages:
                ig_info = page.get("instagram_business_account")
                if ig_info:
                    ig_id = str(ig_info["id"])
                    detail_resp = requests.get(
                        f"{GRAPH_URL}/{ig_id}",
                        params={
                            "fields": "id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website",
                            "access_token": clean_token
                        },
                        timeout=15
                    )
                    if detail_resp.status_code == 200:
                        detail = detail_resp.json()
                        username = detail.get("username", username)
                    break
    except Exception:
        pass

    if not ig_id:
        try:
            me_resp = requests.get(f"{GRAPH_URL}/me", params={"access_token": clean_token, "fields": "id,name"}, timeout=10)
            if me_resp.status_code == 200:
                me_data = me_resp.json()
                ig_id = str(me_data.get("id", "instagram_user"))
                username = me_data.get("name", "Instagram Account")
        except Exception:
            ig_id = "instagram_user"

    expires_at = int(time.time()) + expires_in
    storage.save_token(
        platform="instagram",
        account_id=ig_id,
        username=username,
        access_token=clean_token,
        refresh_token=None,
        expires_at=expires_at,
        scopes=INSTAGRAM_SCOPES
    )
    export_instagram_token_to_json(clean_token, expires_in, token_type)
    return {
        "platform": "instagram",
        "account_id": ig_id,
        "username": username,
        "expires_at": expires_at
    }


def exchange_instagram_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    """
    Menukar Authorization Code dengan Long-Lived Token via Facebook Login & Instagram Graph API.
    Alur sama persis dengan Archive_sosmed/streamlit-sosmed:
    1. Code -> Short-Lived Access Token via https://graph.facebook.com/v21.0/oauth/access_token
    2. Short-Lived -> Long-Lived Token (60 hari) via fb_exchange_token
    3. Cari Instagram Business Account yang terhubung ke Facebook Page
    4. Simpan ke database SQLite terenkripsi dan token.json
    """
    if not INSTAGRAM_APP_ID or not INSTAGRAM_APP_SECRET:
        raise OAuthError("INSTAGRAM_APP_ID dan INSTAGRAM_APP_SECRET belum diisi di konfigurasi.")

    clean_code = code.split("#")[0].strip()

    # 1. Tukar code dengan token via Facebook OAuth
    params = {
        "client_id": INSTAGRAM_APP_ID,
        "client_secret": INSTAGRAM_APP_SECRET,
        "redirect_uri": redirect_uri,
        "code": clean_code
    }

    try:
        resp = requests.get(TOKEN_URL, params=params, timeout=15)
        data = resp.json()
    except Exception as e:
        raise OAuthError(f"Gagal menghubungi server Facebook/Instagram ({e.__class__.__name__}).")

    if resp.status_code != 200 or "access_token" not in data:
        raw_err = data.get("error", {}).get("message", "Gagal menukar authorization code")
        raise OAuthError(f"Instagram OAuth error: {_clean_error_message(raw_err)}")

    short_token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    token_type = data.get("token_type", "bearer")

    # 2. Tukar short-lived token ke long-lived token (60 hari)
    long_params = {
        "grant_type": "fb_exchange_token",
        "client_id": INSTAGRAM_APP_ID,
        "client_secret": INSTAGRAM_APP_SECRET,
        "fb_exchange_token": short_token
    }

    final_token = short_token
    try:
        resp_long = requests.get(f"{GRAPH_URL}/oauth/access_token", params=long_params, timeout=15)
        long_data = resp_long.json()
        if resp_long.status_code == 200 and "access_token" in long_data:
            final_token = long_data["access_token"]
            expires_in = int(long_data.get("expires_in", 5184000))
            token_type = long_data.get("token_type", "bearer")
    except Exception:
        pass

    # 3. Simpan dan hubungkan akun Instagram
    return save_manual_instagram_token(final_token, expires_in=expires_in, token_type=token_type)


TIKTOK_TOKEN_JSON_FILE = os.path.join(storage.BASE_DIR, ".tiktok_token.json")


def export_tiktok_token_to_json(
    access_token: str,
    refresh_token: str,
    open_id: str = "",
    scope: str = "",
    expires_in: int = 86400,
    expires_at: Optional[int] = None
) -> str:
    """
    Menyimpan token TikTok ke file .tiktok_token.json (format plaintext sama persis dengan TikTokAnalytics).
    """
    if expires_at is None:
        expires_at = int(time.time()) + expires_in
    data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "open_id": open_id,
        "scope": scope,
        "expires_in": expires_in,
        "expires_at": expires_at
    }
    try:
        with open(TIKTOK_TOKEN_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
    return TIKTOK_TOKEN_JSON_FILE


def delete_tiktok_token_file() -> None:
    """Menghapus file .tiktok_token.json saat disconnect."""
    if os.path.exists(TIKTOK_TOKEN_JSON_FILE):
        try:
            os.remove(TIKTOK_TOKEN_JSON_FILE)
        except Exception:
            pass


def save_manual_tiktok_tokens(
    access_token: str,
    refresh_token: str,
    open_id: str = "manual_account",
    username: str = "TikTok Account",
    expires_in: int = 86400
) -> Dict[str, Any]:
    """Menyimpan token TikTok yang diinput secara manual langsung ke database dan file .tiktok_token.json."""
    expires_at = int(time.time()) + expires_in
    scope = "user.info.basic,user.info.profile,user.info.stats,video.list"
    storage.save_token(
        platform="tiktok",
        account_id=open_id,
        username=username,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scopes=scope
    )
    export_tiktok_token_to_json(
        access_token=access_token,
        refresh_token=refresh_token,
        open_id=open_id,
        scope=scope,
        expires_in=expires_in,
        expires_at=expires_at
    )
    return {
        "platform": "tiktok",
        "account_id": open_id,
        "username": username,
        "expires_at": expires_at
    }


def test_tiktok_refresh_token(refresh_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Melakukan panggilan HTTP POST langsung ke endpoint https://open.tiktokapis.com/v2/oauth/token/
    dengan grant_type=refresh_token untuk menguji validitas refresh token secara transparan.
    Mengembalikan detail respon lengkap (status, waktu respon, raw JSON, headers, dan cURL).
    """
    if not refresh_token:
        record = storage.get_token_record("tiktok")
        if record and record.get("refresh_token"):
            refresh_token = record["refresh_token"]
        else:
            raise OAuthError("Refresh token tidak ditemukan di database maupun parameter.")

    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    curl_command = (
        f'curl -X POST "{token_url}" \\\n'
        f'  -H "Content-Type: application/x-www-form-urlencoded" \\\n'
        f'  -d "client_key={TIKTOK_CLIENT_KEY}" \\\n'
        f'  -d "client_secret={TIKTOK_CLIENT_SECRET}" \\\n'
        f'  -d "grant_type=refresh_token" \\\n'
        f'  -d "refresh_token={refresh_token}"'
    )

    start_time = time.time()
    try:
        resp = requests.post(token_url, headers=headers, data=payload, timeout=20)
        elapsed_ms = int((time.time() - start_time) * 1000)
        res_json = resp.json()
    except Exception as e:
        raise OAuthError(f"Gagal menghubungi endpoint TikTok ({e.__class__.__name__}): {str(e)}")

    token_data = _tiktok_token_payload(res_json)
    is_success = resp.status_code == 200 and bool(token_data.get("access_token"))

    if is_success:
        new_access = token_data["access_token"]
        new_refresh = token_data.get("refresh_token", refresh_token)
        new_expires_in = int(token_data.get("expires_in", 86400))
        new_expires_at = int(time.time()) + new_expires_in
        open_id = token_data.get("open_id", "")
        scope = token_data.get("scope", "")

        record = storage.get_token_record("tiktok")
        account_id = record["account_id"] if record else open_id
        username = record["username"] if record else open_id
        scopes = scope or (record["scopes"] if record else "user.info.basic,user.info.profile,user.info.stats,video.list")

        storage.save_token(
            platform="tiktok",
            account_id=account_id,
            username=username,
            access_token=new_access,
            refresh_token=new_refresh,
            expires_at=new_expires_at,
            scopes=scopes
        )
        export_tiktok_token_to_json(
            access_token=new_access,
            refresh_token=new_refresh,
            open_id=account_id,
            scope=scopes,
            expires_in=new_expires_in,
            expires_at=new_expires_at
        )

    return {
        "status_code": resp.status_code,
        "elapsed_ms": elapsed_ms,
        "is_success": is_success,
        "headers": dict(resp.headers),
        "response_json": res_json,
        "curl_command": curl_command,
        "token_data": token_data,
        "refresh_token_used": refresh_token
    }


def exchange_tiktok_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    """
    Menukar Authorization Code dengan Access Token & Refresh Token untuk TikTok Login Kit v2.
    Endpoint resmi: POST https://open.tiktokapis.com/v2/oauth/token/
    Scope: user.info.basic,user.info.profile,video.list
    """
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET:
        raise OAuthError("TIKTOK_CLIENT_KEY dan TIKTOK_CLIENT_SECRET belum diisi di konfigurasi.")

    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    clean_code = code.split("#")[0].strip()
    payload = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": clean_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri
    }

    try:
        resp = requests.post(token_url, headers=headers, data=payload, timeout=15)
        res_json = resp.json()
    except Exception as e:
        raise OAuthError(f"Gagal menghubungi server TikTok ({e.__class__.__name__}).")

    # Respon token TikTok v2 berbentuk datar (lihat _tiktok_token_payload)
    token_data = _tiktok_token_payload(res_json)

    if resp.status_code != 200 or not token_data:
        raw_err = _extract_tiktok_error(res_json)
        raise OAuthError(f"TikTok OAuth error: {_clean_error_message(raw_err)}")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = int(token_data.get("expires_in", 86400))  # Default 24 jam
    open_id = token_data.get("open_id", "")
    scope = token_data.get("scope", "user.info.basic,user.info.profile,user.info.stats,video.list")
    expires_at = int(time.time()) + expires_in

    # Ambil display name akun sendiri
    display_name = open_id
    try:
        user_info_url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,avatar_url"
        u_headers = {"Authorization": f"Bearer {access_token}"}
        u_resp = requests.get(user_info_url, headers=u_headers, timeout=10)
        if u_resp.status_code == 200:
            u_data = u_resp.json().get("data", {}).get("user", {})
            display_name = u_data.get("display_name", open_id)
    except Exception:
        pass

    storage.save_token(
        platform="tiktok",
        account_id=open_id,
        username=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scopes=scope
    )

    export_tiktok_token_to_json(
        access_token=access_token,
        refresh_token=refresh_token,
        open_id=open_id,
        scope=scope,
        expires_in=expires_in,
        expires_at=expires_at
    )

    return {
        "platform": "tiktok",
        "account_id": open_id,
        "username": display_name,
        "expires_at": expires_at
    }


def get_valid_token(platform: str) -> str:
    """
    Titik masuk autentikasi untuk modul pengambil data.
    1. Membaca token tersimpan dari storage SQLite (didekripsi secara aman di memori).
    2. Memeriksa masa berlaku dan melakukan refresh otomatis jika mendekati kedaluwarsa
       sesuai aturan refresh resmi dari masing-masing platform.
    3. Menyimpan token hasil pembaruan kembali ke database terenkripsi.
    4. Mengembalikan access_token yang valid.
    PENTING: Jangan pernah mencetak atau me-log isi token!
    """
    platform = platform.lower().strip()
    record = storage.get_token_record(platform)
    if not record and platform == "instagram":
        # Coba auto-load dari token.json jika ada
        if os.path.exists(INSTAGRAM_TOKEN_JSON_FILE):
            try:
                with open(INSTAGRAM_TOKEN_JSON_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if "access_token" in saved and saved["access_token"]:
                    save_manual_instagram_token(saved["access_token"], int(saved.get("expires_in", 5184000)))
                    record = storage.get_token_record("instagram")
            except Exception:
                pass

    if not record:
        raise OAuthError(f"Belum ada akun {platform.capitalize()} yang terhubung. Silakan lakukan otorisasi terlebih dahulu.")

    now = int(time.time())
    access_token = record["access_token"]
    refresh_token = record["refresh_token"]
    expires_at = record["expires_at"]
    created_at = record["created_at"]
    account_id = record["account_id"]
    username = record["username"]
    scopes = record["scopes"]

    # ==========================
    # REFRESH LOGIC: INSTAGRAM
    # ==========================
    if platform == "instagram":
        remaining_seconds = expires_at - now
        token_age_seconds = now - created_at

        if remaining_seconds < (15 * 86400) and token_age_seconds >= 86400:
            if remaining_seconds <= 0:
                raise OAuthError("Token Instagram telah kedaluwarsa penuh (> 60 hari). Pengguna harus menghubungkan ulang akun.")

            refresh_url = f"{GRAPH_URL}/oauth/access_token"
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": INSTAGRAM_APP_ID,
                "client_secret": INSTAGRAM_APP_SECRET,
                "fb_exchange_token": access_token
            }
            try:
                resp = requests.get(refresh_url, params=params, timeout=15)
                data = resp.json()
            except Exception as e:
                if remaining_seconds > 3600:
                    return access_token
                raise OAuthError(f"Gagal merefresh token Instagram ({e.__class__.__name__}).")

            if resp.status_code == 200 and "access_token" in data:
                new_token = data["access_token"]
                new_expires_in = int(data.get("expires_in", 5184000))
                new_expires_at = now + new_expires_in

                storage.save_token(
                    platform="instagram",
                    account_id=account_id,
                    username=username,
                    access_token=new_token,
                    refresh_token=None,
                    expires_at=new_expires_at,
                    scopes=scopes
                )
                export_instagram_token_to_json(new_token, new_expires_in)
                return new_token
            else:
                if remaining_seconds > 3600:
                    return access_token
                raw_err = data.get("error", {}).get("message", "Gagal merefresh token")
                raise OAuthError(f"Instagram refresh error: {_clean_error_message(raw_err)}")

        return access_token

    # ==========================
    # REFRESH LOGIC: TIKTOK
    # ==========================
    elif platform == "tiktok":
        # Aturan resmi TikTok Login Kit v2:
        # - Access token berlaku 24 jam (86400 detik).
        # - Refresh token berlaku hingga 365 hari.
        # - Endpoint refresh: POST https://open.tiktokapis.com/v2/oauth/token/
        # - Parameter: client_key, client_secret, grant_type=refresh_token, refresh_token
        remaining_seconds = expires_at - now

        if remaining_seconds < 3600:
            if not refresh_token:
                raise OAuthError("Refresh token TikTok tidak tersedia. Silakan hubungkan ulang akun.")

            refresh_url = "https://open.tiktokapis.com/v2/oauth/token/"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            payload = {
                "client_key": TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            }

            try:
                resp = requests.post(refresh_url, headers=headers, data=payload, timeout=15)
                res_json = resp.json()
            except Exception as e:
                if remaining_seconds > 300:
                    return access_token
                raise OAuthError(f"Gagal menghubungi endpoint refresh TikTok ({e.__class__.__name__}).")

            token_data = _tiktok_token_payload(res_json)
            if resp.status_code == 200 and token_data:
                new_access = token_data["access_token"]
                new_refresh = token_data.get("refresh_token", refresh_token)
                new_expires_in = int(token_data.get("expires_in", 86400))
                new_expires_at = now + new_expires_in

                storage.save_token(
                    platform="tiktok",
                    account_id=account_id,
                    username=username,
                    access_token=new_access,
                    refresh_token=new_refresh,
                    expires_at=new_expires_at,
                    scopes=token_data.get("scope", scopes)
                )
                export_tiktok_token_to_json(
                    access_token=new_access,
                    refresh_token=new_refresh,
                    open_id=account_id,
                    scope=token_data.get("scope", scopes),
                    expires_in=new_expires_in,
                    expires_at=new_expires_at
                )
                return new_access
            else:
                raw_err = _extract_tiktok_error(res_json)
                raise OAuthError(f"TikTok refresh error: {_clean_error_message(raw_err)}")

        return access_token

    else:
        raise OAuthError(f"Platform '{platform}' tidak didukung.")
