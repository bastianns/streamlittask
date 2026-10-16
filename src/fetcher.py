import time
import requests
from typing import Dict, Any, List, Optional
try:
    from src.token_manager import get_valid_token, OAuthError
except ImportError:
    from token_manager import get_valid_token, OAuthError


class FetcherError(Exception):
    """Exception khusus untuk error pengambilan data dari API resmi."""
    pass


def fetch_data(platform: str) -> Dict[str, Any]:
    """
    Mengambil data akun resmi milik pengguna yang terautentikasi.
    ATURAN: Hanya mengambil data akun sendiri (me / owned videos).
    Tidak mengambil data akun publik lain atau akun privat lain.
    """
    platform = platform.lower().strip()
    # 1. Dapatkan token aktif (auto refresh jika mendekati kadaluwarsa)
    access_token = get_valid_token(platform)

    if platform == "instagram":
        return _fetch_instagram_data(access_token)
    elif platform == "tiktok":
        return _fetch_tiktok_data(access_token)
    else:
        raise FetcherError(f"Platform '{platform}' tidak didukung.")


def _fetch_instagram_data(access_token: str) -> Dict[str, Any]:
    """
    Mengambil profil dan media akun Instagram sendiri via Instagram Graph API.
    Endpoints resmi Meta:
    - Profil: GET https://graph.instagram.com/v21.0/me
    - Media:  GET https://graph.instagram.com/v21.0/me/media
    """
    # 1. Ambil data profil akun
    profile_url = "https://graph.instagram.com/v21.0/me"
    profile_params = {
        "fields": "id,username,name,account_type,profile_picture_url",
        "access_token": access_token
    }

    try:
        resp_prof = requests.get(profile_url, params=profile_params, timeout=15)
        prof_data = resp_prof.json()
    except Exception as e:
        raise FetcherError(f"Gagal menghubungi endpoint profil Instagram ({e.__class__.__name__}).")

    if resp_prof.status_code != 200:
        err_msg = prof_data.get("error", {}).get("message", f"HTTP {resp_prof.status_code}")
        raise FetcherError(f"Instagram Graph API Profil Error: {err_msg}")

    # 2. Ambil media terbaru akun sendiri
    media_url = "https://graph.instagram.com/v21.0/me/media"
    media_params = {
        "fields": "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp",
        "limit": 12,
        "access_token": access_token
    }

    media_items: List[Dict[str, Any]] = []
    media_error: Optional[str] = None

    try:
        resp_med = requests.get(media_url, params=media_params, timeout=15)
        if resp_med.status_code == 200:
            media_data = resp_med.json()
            media_items = media_data.get("data", [])
        else:
            try:
                med_err_json = resp_med.json()
                raw_err = med_err_json.get("error", {}).get("message", f"HTTP {resp_med.status_code}")
            except Exception:
                raw_err = f"HTTP {resp_med.status_code}"
            media_error = f"Instagram Media API error (Status {resp_med.status_code}): {raw_err}"
    except Exception as e:
        media_error = f"Gagal menghubungi endpoint media Instagram ({e.__class__.__name__})."

    return {
        "platform": "instagram",
        "fetched_at": int(time.time()),
        "profile": prof_data,
        "media": media_items,
        "media_error": media_error
    }


def _fetch_tiktok_data(access_token: str) -> Dict[str, Any]:
    """
    Mengambil profil dan video akun TikTok sendiri via TikTok Display API v2.
    Endpoints resmi TikTok:
    - Profil: GET  https://open.tiktokapis.com/v2/user/info/
    - Video:  POST https://open.tiktokapis.com/v2/video/list/
    """
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # 1. Ambil info profil akun
    user_info_url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,avatar_url_100,avatar_large_url,display_name,bio_description,profile_deep_link,is_verified"

    try:
        resp_user = requests.get(user_info_url, headers=headers, timeout=15)
        user_res = resp_user.json()
    except Exception as e:
        raise FetcherError(f"Gagal menghubungi endpoint profil TikTok ({e.__class__.__name__}).")

    user_data = user_res.get("data", {}).get("user", {})
    if resp_user.status_code != 200 or not user_data:
        err_msg = user_res.get("error", {}).get("message", f"HTTP {resp_user.status_code}")
        raise FetcherError(f"TikTok Display API Profil Error: {err_msg}")

    # 2. Ambil daftar video akun sendiri
    video_list_url = "https://open.tiktokapis.com/v2/video/list/?fields=id,title,video_description,duration,cover_image_url,embed_html,embed_link,like_count,comment_count,share_count,view_count"
    video_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    video_body = {"max_count": 10}

    video_items: List[Dict[str, Any]] = []
    videos_error: Optional[str] = None

    try:
        resp_vid = requests.post(video_list_url, headers=video_headers, json=video_body, timeout=15)
        if resp_vid.status_code == 200:
            vid_res = resp_vid.json()
            video_items = vid_res.get("data", {}).get("videos", [])
            err_obj = vid_res.get("error", {})
            if err_obj.get("code") not in (None, "", "ok", "0", 0):
                videos_error = f"TikTok Video API error: {err_obj.get('message', 'Kode error ' + str(err_obj.get('code')))}"
        else:
            try:
                vid_err_json = resp_vid.json()
                raw_err = vid_err_json.get("error", {}).get("message") or vid_err_json.get("message", f"HTTP {resp_vid.status_code}")
            except Exception:
                raw_err = f"HTTP {resp_vid.status_code}"
            videos_error = f"TikTok Video API error (Status {resp_vid.status_code}): {raw_err}"
    except Exception as e:
        videos_error = f"Gagal menghubungi endpoint video TikTok ({e.__class__.__name__})."

    return {
        "platform": "tiktok",
        "fetched_at": int(time.time()),
        "profile": user_data,
        "videos": video_items,
        "videos_error": videos_error
    }
