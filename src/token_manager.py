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
    )
except ImportError:
    import storage
    from config import (
        INSTAGRAM_APP_ID,
        INSTAGRAM_APP_SECRET,
        TIKTOK_CLIENT_KEY,
        TIKTOK_CLIENT_SECRET,
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


def exchange_instagram_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    """
    Menukar Authorization Code dengan Long-Lived User Access Token untuk Instagram.
    Alur resmi Meta:
    1. Code -> Short-Lived Access Token (1 jam) via api.instagram.com
       Mendukung dua format respons token pendek:
       - Datar: {"access_token": "...", "user_id": ...}
       - Terbungkus: {"data": [{"access_token": "...", "user_id": ...}]}
    2. Short-Lived -> Long-Lived Access Token (60 hari) via graph.instagram.com
    3. Ambil data profil dasar akun sendiri (id, username)
    4. Simpan ke database terenkripsi tanpa pernah mencetak/me-log token.
    """
    if not INSTAGRAM_APP_ID or not INSTAGRAM_APP_SECRET:
        raise OAuthError("INSTAGRAM_APP_ID dan INSTAGRAM_APP_SECRET belum diisi di konfigurasi.")

    # Instagram terkadang menyematkan '#_' di akhir parameter code
    clean_code = code.split("#_")[0]

    # Langkah 1: Tukar code dengan short-lived token
    short_lived_url = "https://api.instagram.com/oauth/access_token"
    payload = {
        "client_id": INSTAGRAM_APP_ID,
        "client_secret": INSTAGRAM_APP_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": clean_code
    }

    try:
        resp = requests.post(short_lived_url, data=payload, timeout=15)
        data = resp.json()
    except Exception as e:
        # Jangan masukkan str(e) karena bisa memuat URL/secret
        raise OAuthError(f"Gagal menghubungi server Instagram ({e.__class__.__name__}).")

    # Parsing DUA format respons token pendek:
    short_token: Optional[str] = None
    user_id: str = ""

    if isinstance(data, dict):
        # Format 1: Format Datar {"access_token": "...", "user_id": ...}
        if "access_token" in data:
            short_token = data["access_token"]
            user_id = str(data.get("user_id", ""))
        # Format 2: Format Terbungkus List {"data": [{"access_token": "...", "user_id": ...}]}
        elif "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            first_item = data["data"][0]
            if isinstance(first_item, dict) and "access_token" in first_item:
                short_token = first_item["access_token"]
                user_id = str(first_item.get("user_id", ""))
        # Format 2b: Terbungkus Dict {"data": {"access_token": "...", "user_id": ...}}
        elif "data" in data and isinstance(data["data"], dict) and "access_token" in data["data"]:
            short_token = data["data"]["access_token"]
            user_id = str(data["data"].get("user_id", ""))

    if resp.status_code != 200 or not short_token:
        raw_err = data.get("error_message") or data.get("error", {}).get("message", "Gagal mendapatkan short-lived token")
        raise OAuthError(f"Instagram OAuth error: {_clean_error_message(raw_err)}")

    # Langkah 2: Tukar short-lived token menjadi long-lived token (60 hari)
    long_lived_url = "https://graph.instagram.com/access_token"
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": INSTAGRAM_APP_SECRET,
        "access_token": short_token
    }

    try:
        resp_long = requests.get(long_lived_url, params=params, timeout=15)
        data_long = resp_long.json()
    except Exception as e:
        raise OAuthError(f"Gagal menghubungi endpoint long-lived Instagram ({e.__class__.__name__}).")

    if resp_long.status_code != 200 or "access_token" not in data_long:
        raw_err = data_long.get("error", {}).get("message", "Gagal menukar ke long-lived token")
        raise OAuthError(f"Instagram Long-Lived Token error: {_clean_error_message(raw_err)}")

    long_token = data_long["access_token"]
    expires_in = int(data_long.get("expires_in", 5184000))  # Default 60 hari
    expires_at = int(time.time()) + expires_in

    # Langkah 3: Ambil username akun pengguna sendiri
    username = user_id
    try:
        profile_url = "https://graph.instagram.com/v21.0/me"
        p_resp = requests.get(profile_url, params={"fields": "id,username,name", "access_token": long_token}, timeout=10)
        if p_resp.status_code == 200:
            p_data = p_resp.json()
            username = p_data.get("username", user_id)
            user_id = str(p_data.get("id", user_id))
    except Exception:
        # Jika query profile gagal, tetap lanjutkan dengan user_id
        pass

    # Langkah 4: Simpan ke storage terenkripsi
    storage.save_token(
        platform="instagram",
        account_id=user_id,
        username=username,
        access_token=long_token,
        refresh_token=None,  # Instagram long-lived token direfresh langsung menggunakan dirinya sendiri
        expires_at=expires_at,
        scopes="instagram_business_basic"
    )

    return {
        "platform": "instagram",
        "account_id": user_id,
        "username": username,
        "expires_at": expires_at
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
    scope = token_data.get("scope", "user.info.basic,user.info.profile,video.list")
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
        # Aturan resmi Meta:
        # - Long-lived token berlaku 60 hari.
        # - Token HANYA dapat diperbarui jika usianya sudah minimal 24 jam (created_at <= now - 86400).
        # - Token belum boleh kedaluwarsa sepenuhnya (expires_at > now).
        # - Rekomendasi refresh: ketika sisa masa berlaku < 15 hari.
        remaining_seconds = expires_at - now
        token_age_seconds = now - created_at

        if remaining_seconds < (15 * 86400) and token_age_seconds >= 86400:
            if remaining_seconds <= 0:
                raise OAuthError("Token Instagram telah kedaluwarsa penuh (> 60 hari). Pengguna harus menghubungkan ulang akun.")

            refresh_url = "https://graph.instagram.com/refresh_access_token"
            params = {
                "grant_type": "ig_refresh_token",
                "access_token": access_token
            }
            try:
                resp = requests.get(refresh_url, params=params, timeout=15)
                data = resp.json()
            except Exception as e:
                # Jika jaringan bermasalah namun token masih valid, gunakan token yang ada
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
                return new_token
            else:
                # Jika refresh gagal namun token masih punya sisa waktu, tetap kembalikan token
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
                return new_access
            else:
                raw_err = _extract_tiktok_error(res_json)
                raise OAuthError(f"TikTok refresh error: {_clean_error_message(raw_err)}")

        return access_token

    else:
        raise OAuthError(f"Platform '{platform}' tidak didukung.")
