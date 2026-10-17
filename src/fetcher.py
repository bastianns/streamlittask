import os
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

try:
    from src.token_manager import get_valid_token, OAuthError
    from src.config import GRAPH_URL, FB_API_VER
except ImportError:
    from token_manager import get_valid_token, OAuthError
    from config import GRAPH_URL, FB_API_VER


class FetcherError(Exception):
    """Exception khusus untuk error pengambilan data dari API resmi."""
    pass


TIMEOUT = 15


# ── Low level request helper ────────────────────────────────────────────────
def _get(url: str, params: dict, timeout: int = TIMEOUT) -> dict:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        if e.response is not None:
            try:
                return {"error": e.response.json().get("error", {"message": str(e)})}
            except ValueError:
                pass
        return {"error": {"message": str(e)}}


# ── Instagram Graph API Helpers (Matching Archive) ──────────────────────────
def get_instagram_account(token: str) -> dict:
    """Mendapatkan akun Instagram Business/Creator yang terhubung ke Facebook Page."""
    pages = _get(f"{GRAPH_URL}/me/accounts", {
        "access_token": token,
        "fields": "id,name,instagram_business_account",
    })
    if "error" in pages:
        return pages
    for page in pages.get("data", []):
        ig = page.get("instagram_business_account")
        if ig:
            detail = _get(f"{GRAPH_URL}/{ig['id']}", {
                "fields": "id,username,name,biography,followers_count,follows_count,"
                          "media_count,profile_picture_url,website",
                "access_token": token,
            })
            return detail
    return {"error": {"message": "Tidak ada akun Instagram Business yang terhubung ke Facebook Page."}}


def get_user_media(ig_id: str, token: str, limit: int = 12) -> dict:
    """Mengambil media terbaru milik akun Instagram sendiri."""
    return _get(f"{GRAPH_URL}/{ig_id}/media", {
        "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink,"
                  "like_count,comments_count",
        "access_token": token,
        "limit": limit,
    })


def get_media_in_range(ig_id: str, token: str, since_dt: datetime, until_dt: datetime,
                       max_pages: int = 100, page_size: int = 50) -> list:
    """
    Mengambil seluruh media pada rentang [since_dt, until_dt] menggunakan pagination cursor.
    """
    results = []
    url = f"{GRAPH_URL}/{ig_id}/media"
    params = {
        "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink,"
                  "like_count,comments_count",
        "access_token": token,
        "limit": page_size,
    }

    for _ in range(max_pages):
        data = _get(url, params)
        if "error" in data:
            break

        items = data.get("data", [])
        if not items:
            break

        stop = False
        for item in items:
            ts_raw = item.get("timestamp", "")
            try:
                ts = datetime.strptime(ts_raw[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
            if ts > until_dt:
                continue
            if ts < since_dt:
                stop = True
                break
            results.append(item)

        if stop:
            break

        next_url = data.get("paging", {}).get("next")
        if not next_url:
            break
        url, params = next_url, {}
        time.sleep(0.15)

    return results


def get_instagram_stories(ig_id: str, token: str) -> dict:
    """Mengambil Instagram Stories aktif."""
    return _get(f"{GRAPH_URL}/{ig_id}/stories", {
        "fields": "id,media_type,media_url,thumbnail_url,timestamp",
        "access_token": token,
    })


def get_single_media_insights(media_id: str, media_type: str, token: str) -> dict:
    """Mengambil insights metrik untuk sebuah postingan media/story."""
    if media_type == "CAROUSEL_ALBUM":
        metrics = "carousel_album_reach"
    elif media_type == "STORY":
        metrics = "reach,impressions,replies,exits"
    else:
        metrics = "reach,saved"

    data = _get(f"{GRAPH_URL}/{media_id}/insights", {
        "metric": metrics,
        "access_token": token,
    })
    result = {}
    for metric in data.get("data", []):
        values = metric.get("values", [])
        if values:
            result[metric["name"]] = values[0].get("value", 0)
    return result


def get_reached_demographics(ig_id: str, token: str, breakdown: str) -> dict:
    """Mengambil demografi reached audience berdasarkan 'city' atau 'country'."""
    return _get(f"{GRAPH_URL}/{ig_id}/insights", {
        "metric": "reached_audience_demographics",
        "period": "lifetime",
        "timeframe": "this_month",
        "breakdown": breakdown,
        "metric_type": "total_value",
        "access_token": token,
    })


def get_audience_demographics(ig_id: str, token: str) -> dict:
    """Mengambil data demografi follower dan online followers (by hour)."""
    return _get(f"{GRAPH_URL}/{ig_id}/insights", {
        "metric": "follower_demographics,online_followers",
        "period": "lifetime",
        "metric_type": "total_value",
        "access_token": token,
    })


def get_insights_window(ig_id: str, token: str, since_dt: datetime, until_dt: datetime) -> dict:
    """Mengambil metrik harian (views, reach, profile_views) dalam rentang <= 30 hari."""
    return _get(f"{GRAPH_URL}/{ig_id}/insights", {
        "metric":       "views,reach,profile_views",
        "period":       "day",
        "since":        int(since_dt.timestamp()),
        "until":        int(until_dt.timestamp()),
        "metric_type":  "total_value",
        "access_token": token,
    })


def get_insights_range(ig_id: str, token: str, since_dt: datetime, until_dt: datetime,
                       chunk_days: int = 30) -> dict:
    """
    Mengambil data insights harian untuk rentang waktu bebas (misal 1 tahun)
    dengan memecahnya menjadi potongan <= 30 hari sesuai batas Graph API.
    """
    merged: dict = {}
    cursor = since_dt
    errors = []

    while cursor < until_dt:
        window_end = min(cursor + timedelta(days=chunk_days), until_dt)
        chunk = get_insights_window(ig_id, token, cursor, window_end)

        if "error" in chunk:
            errors.append(f"{cursor.date()}–{window_end.date()}: {chunk['error'].get('message')}")
        else:
            for metric in chunk.get("data", []):
                name = metric["name"]
                merged.setdefault(name, {})
                for point in metric.get("values", []):
                    date_str = point.get("end_time", "")[:10]
                    merged[name][date_str] = point.get("value", 0)

        cursor = window_end
        time.sleep(0.2)

    if errors:
        merged["_errors"] = errors
    return merged


def parse_insights_to_series(insights_data: dict) -> dict:
    """Mengubah respons mentah Graph API insights menjadi format dict {metric_name: {date_str: value}}."""
    series = {}
    for metric in insights_data.get("data", []):
        name = metric["name"]
        values = {}
        for point in metric.get("values", []):
            date_str = point.get("end_time", "")[:10]
            values[date_str] = point.get("value", 0)
        series[name] = values
    return series


# ── High-Level Data Fetcher ────────────────────────────────────────────────
def fetch_data(platform: str) -> Dict[str, Any]:
    """
    Mengambil data akun resmi milik pengguna yang terautentikasi.
    ATURAN: Hanya mengambil data akun sendiri (me / owned videos).
    """
    platform = platform.lower().strip()
    access_token = get_valid_token(platform)

    if platform == "instagram":
        return _fetch_instagram_data(access_token)
    elif platform == "tiktok":
        return _fetch_tiktok_data(access_token)
    else:
        raise FetcherError(f"Platform '{platform}' tidak didukung.")


def _fetch_instagram_data(access_token: str) -> Dict[str, Any]:
    """
    Mengambil profil dan media akun Instagram via Facebook Graph API.
    """
    account_detail = get_instagram_account(access_token)
    if "error" in account_detail:
        raise FetcherError(f"Instagram Graph API Profil Error: {account_detail['error'].get('message')}")

    ig_id = account_detail.get("id")
    if not ig_id:
        raise FetcherError("ID akun Instagram tidak ditemukan pada profil.")

    media_data = get_user_media(ig_id, access_token, limit=12)
    media_items = media_data.get("data", []) if "data" in media_data else []
    media_error = media_data.get("error", {}).get("message") if "error" in media_data else None

    # Tambahkan per-post insights
    for item in media_items:
        m_type = item.get("media_type", "")
        item["insights"] = get_single_media_insights(item["id"], m_type, access_token)

    return {
        "platform": "instagram",
        "fetched_at": int(time.time()),
        "ig_id": ig_id,
        "profile": account_detail,
        "media": media_items,
        "media_error": media_error
    }


def _fetch_tiktok_data(access_token: str) -> Dict[str, Any]:
    """
    Mengambil profil dan video akun TikTok sendiri via TikTok Display API v2.
    """
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # 1. Ambil info profil akun
    user_info_url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,avatar_url_100,avatar_large_url,display_name,bio_description,profile_deep_link,is_verified,follower_count,following_count,likes_count,video_count"

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
    video_list_url = "https://open.tiktokapis.com/v2/video/list/?fields=id,title,video_description,duration,cover_image_url,embed_html,embed_link,share_url,create_time,like_count,comment_count,share_count,view_count"
    video_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    video_body = {"max_count": 20}

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
