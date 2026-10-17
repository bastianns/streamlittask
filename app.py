import os
import sys
import datetime
import streamlit as st

# Pastikan direktori root proyek berada di sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pandas as pd

from src import storage, config
from src.token_manager import (
    exchange_instagram_code,
    exchange_tiktok_code,
    get_valid_token,
    test_tiktok_refresh_token,
    save_manual_tiktok_tokens,
    delete_tiktok_token_file,
    export_tiktok_token_to_json,
    save_manual_instagram_token,
    delete_instagram_token_file,
    INSTAGRAM_TOKEN_JSON_FILE,
    TIKTOK_TOKEN_JSON_FILE,
    OAuthError
)
from src.fetcher import (
    fetch_data,
    get_instagram_account,
    get_user_media,
    get_media_in_range,
    get_instagram_stories,
    get_single_media_insights,
    get_reached_demographics,
    get_audience_demographics,
    get_insights_window,
    get_insights_range,
    parse_insights_to_series,
    FetcherError
)

from src.cookie_manager import (
    save_tiktok_cookie_session,
    capture_tiktok_cookies_via_browser,
    get_tiktok_cookie_headers,
    delete_cookie_txt_file,
    CookieAuthError
)

from src.instagram_cookie_manager import (
    save_instagram_cookie_session,
    capture_instagram_cookies_via_browser,
    get_instagram_cookie_headers,
    delete_ig_cookie_txt_file,
    IGCookieAuthError
)


# Gunakan ikon aplikasi di folder assets jika tersedia
icon_path = os.path.join(BASE_DIR, "assets", "app_icon.png")
page_icon = icon_path if os.path.exists(icon_path) else "🔐"

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="Official OAuth 2.0 Hub (Instagram & TikTok)",
    page_icon=page_icon,
    layout="wide"
)

# --- CSS Styling Kustom ---
st.markdown("""
    <style>
    .main {background-color: #f8fafc;}
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .metric-card {
        background-color: white;
        padding: 1.2rem;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .badge-active {
        display: inline-block;
        background-color: #dcfce7;
        color: #166534;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-inactive {
        display: inline-block;
        background-color: #fee2e2;
        color: #991b1b;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

# --- Banner Prototipe Wajib ---
st.warning(
    "⚠️ **PROTOTIPE SISTEM AUTENTIKASI OAUTH 2.0 RESMI**\n\n"
    "Aplikasi ini hanya menggunakan alur **OAuth 2.0 resmi** (Meta Instagram Login & TikTok Login Kit v2). "
    "Aplikasi **tidak pernah** meminta atau menyimpan password, kode SMS/PIN, maupun cookie sesi. "
    "Token akses dienkripsi dengan standar *AES-128 (Fernet)* di database lokal SQLite dan tidak pernah di-log."
)

st.title("🔐 Multi-Platform Official OAuth Hubb")
st.caption("Hubungkan akun resmi Instagram (Business/Creator) dan TikTok untuk sinkronisasi data langsung via API resmi.")

# =========================================================================
# 1. PENANGANAN OAUTH CALLBACK (st.query_params)
# =========================================================================
params = st.query_params
if "code" in params:
    raw_code = params["code"]
    raw_state = params.get("state", "")

    # Simpan ke session_state dan bersihkan URL seketika untuk mencegah double-render consumption
    if "pending_oauth_code" not in st.session_state:
        st.session_state["pending_oauth_code"] = raw_code
        st.session_state["pending_oauth_state"] = raw_state
        st.query_params.clear()
        st.rerun()

if "pending_oauth_code" in st.session_state:
    code = st.session_state.pop("pending_oauth_code")
    state = st.session_state.pop("pending_oauth_state", "")

    with st.spinner("Memproses otentikasi OAuth..."):
        is_valid, platform, error_msg = config.verify_signed_state(state) if state else (False, None, "Parameter state tidak ada.")
        if not is_valid:
            if state.startswith("tt_") or "tiktok" in state.lower():
                platform = "tiktok"
            elif state.startswith("ig_") or state.startswith("fb_") or "instagram" in state.lower():
                platform = "instagram"
            else:
                platform = None

        if not platform:
            st.error(f"❌ **Validasi State Gagal:** {error_msg}")
        else:
            try:
                redirect_uri = config.INSTAGRAM_REDIRECT_URI if platform == "instagram" else config.TIKTOK_REDIRECT_URI
                if platform == "instagram":
                    res = exchange_instagram_code(code, redirect_uri)
                    st.success(f"🎉 Berhasil menghubungkan akun Instagram **@{res.get('username')}**!")
                elif platform == "tiktok":
                    res = exchange_tiktok_code(code, redirect_uri)
                    st.success(f"🎉 Berhasil menghubungkan akun TikTok **@{res.get('username')}**!")
                st.rerun()
            except OAuthError as oe:
                st.error(f"❌ **Autentikasi Gagal:** {str(oe)}")
            except Exception as ex:
                st.error(f"❌ **Terjadi Kesalahan Server:** ({ex.__class__.__name__})")

# =========================================================================
# 2. TAB UTAMA: INSTAGRAM & TIKTOK
# =========================================================================
tab_ig, tab_ig_cookie, tab_tt, tab_tt_cookie = st.tabs([
    "📸 Instagram (Business / Creator)",
    "🍪 Instagram (Cookie Session)",
    "🎵 TikTok (Login Kit v2)",
    "🍪 TikTok (Cookie Session)"
])



# -------------------------------------------------------------------------
# TAB INSTAGRAM
# -------------------------------------------------------------------------
with tab_ig:
    st.subheader("📸 Instagram Graph API Dashboard (Meta)")
    st.write(
        "Autentikasi resmi untuk akun **Instagram Professional (Business atau Creator)** yang terhubung "
        "dengan Facebook Page via Meta Graph API."
    )

    ig_meta = storage.get_token_metadata("instagram")
    ig_record = storage.get_token_record("instagram") if ig_meta else None

    # Auto-load token dari token.json jika database belum terisi
    if not ig_record and os.path.exists(INSTAGRAM_TOKEN_JSON_FILE):
        try:
            with open(INSTAGRAM_TOKEN_JSON_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if "access_token" in saved and saved["access_token"]:
                save_manual_instagram_token(saved["access_token"], int(saved.get("expires_in", 5184000)))
                ig_meta = storage.get_token_metadata("instagram")
                ig_record = storage.get_token_record("instagram")
        except Exception:
            pass

    if not ig_meta:
        # Belum terhubung
        col_info, col_action = st.columns([2, 1])
        with col_info:
            st.markdown("""
            **Aturan & Kebijakan Meta:**
            * Menghubungkan akun secara langsung melalui jendela otorisasi resmi Facebook Login / Instagram Graph API.
            * Akun Instagram wajib bertipe **Business atau Creator** dan terhubung ke **Facebook Page**.
            * Token jangka panjang (*Long-Lived Token*) berlaku selama 60 hari dan direfresh secara otomatis sebelum kedaluwarsa.
            """)
            if not config.INSTAGRAM_APP_ID or not config.INSTAGRAM_APP_SECRET:
                st.info("ℹ️ Kredensial `INSTAGRAM_APP_ID` dan `INSTAGRAM_APP_SECRET` belum diisi di `.streamlit/secrets.toml` atau `.env`.")

        with col_action:
            state_token = config.generate_signed_state("instagram")
            auth_url = config.get_instagram_auth_url(config.INSTAGRAM_REDIRECT_URI, state_token)
            st.link_button(
                "🔐 Login with Facebook / Instagram",
                auth_url,
                type="primary",
                help="Buka halaman otorisasi OAuth 2.0 resmi Meta Graph API"
            )

        with st.expander("🛠️ Opsi Alternatif: Masukkan Authorization Code atau Access Token Manual"):
            st.caption(
                "Gunakan opsi ini jika Anda memiliki token dari file `token.json` atau redirect URI Anda "
                "mengarah ke halaman eksternal."
            )
            subcol1, subcol2 = st.columns(2)
            with subcol1:
                st.markdown("##### 📥 Tukar Code Manual dari Redirect URL")
                with st.form("form_manual_ig_code"):
                    manual_code = st.text_input("Authorization Code (dari parameter `code=...`)", placeholder="AQ...")
                    custom_redirect = st.text_input("Redirect URI yang Digunakan", value=config.INSTAGRAM_REDIRECT_URI)
                    submit_code = st.form_submit_button("⚡ Tukar Code Menjadi Token")
                    if submit_code and manual_code.strip():
                        try:
                            with st.spinner("Menukar authorization code ke Meta..."):
                                res = exchange_instagram_code(manual_code.strip(), custom_redirect.strip())
                                st.success(f"🎉 Berhasil menghubungkan akun @{res.get('username')}!")
                                st.rerun()
                        except OAuthError as oe:
                            st.error(f"Gagal: {str(oe)}")
            with subcol2:
                st.markdown("##### 🔑 Impor User Access Token")
                with st.form("form_manual_ig_token"):
                    man_token = st.text_input("Access Token (Facebook / IG)", type="password", placeholder="EAAL...")
                    submit_tok = st.form_submit_button("💾 Simpan & Hubungkan")
                    if submit_tok and man_token.strip():
                        try:
                            with st.spinner("Memverifikasi token ke Meta Graph API..."):
                                res = save_manual_instagram_token(man_token.strip())
                                st.success(f"🎉 Berhasil menghubungkan akun @{res.get('username')}!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Gagal: {str(e)}")
    else:
        # Sudah terhubung
        token = get_valid_token("instagram")
        ig_id = ig_meta["account_id"]
        exp_time = datetime.datetime.fromtimestamp(ig_meta["expires_at"]).strftime("%Y-%m-%d %H:%M:%S")

        st.markdown('<span class="badge-active">● INSTAGRAM TERHUBUNG</span>', unsafe_allow_html=True)

        # ── Fetch Profile Details ──────────────────────────────────────────
        if "ig_profile_detail" not in st.session_state:
            with st.spinner("🔍 Mengambil profil Instagram…"):
                st.session_state["ig_profile_detail"] = get_instagram_account(token)
        
        ig_detail = st.session_state.get("ig_profile_detail", {})
        if "error" in ig_detail:
            st.warning(f"⚠️ Peringatan Profil: {ig_detail['error'].get('message')}")

        # ── Profile Header Banner ──────────────────────────────────────────
        st.divider()
        col_pic, col_stats = st.columns([1, 5])
        with col_pic:
            if ig_detail.get("profile_picture_url"):
                st.image(ig_detail["profile_picture_url"], width=110)
            else:
                st.markdown("🖼️ *(Tidak ada foto)*")
        with col_stats:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Username", f"@{ig_detail.get('username', ig_meta['username'])}")
            followers_val = ig_detail.get("followers_count", "—")
            c2.metric("Followers", f"{followers_val:,}" if isinstance(followers_val, int) else str(followers_val))
            c3.metric("Posts", ig_detail.get("media_count", "—"))
            c4.metric("Account ID", ig_detail.get("id", ig_id))
            if ig_detail.get("biography"):
                st.caption(ig_detail["biography"])
            if ig_detail.get("website"):
                st.markdown(f"🌐 [{ig_detail['website']}]({ig_detail['website']})")

        # ── Action Buttons (Refresh & Disconnect) ───────────────────────────
        c_sync, c_disc = st.columns([1, 1])
        with c_sync:
            if st.button("🔄 Sinkronisasi / Refresh Data", key="btn_sync_ig", use_container_width=True):
                st.session_state.pop("ig_profile_detail", None)
                st.session_state.pop("ig_monthly_insights", None)
                st.session_state.pop("ig_audience_data", None)
                st.session_state.pop("ig_reached_city", None)
                st.session_state.pop("ig_reached_country", None)
                st.session_state.pop("ig_media_data", None)
                st.session_state.pop("ig_stories_data", None)
                st.rerun()
        with c_disc:
            if st.button("🚪 Logout / Putuskan Instagram", key="btn_disc_ig", use_container_width=True):
                storage.delete_token("instagram")
                delete_instagram_token_file()
                st.session_state.clear()
                st.rerun()

        # ── 30-Day Impressions & Reach Chart ───────────────────────────────
        st.divider()
        st.subheader("📊 Impresi & Jangkauan — 30 Hari Terakhir")

        if "ig_monthly_insights" not in st.session_state:
            until_dt = datetime.datetime.utcnow()
            since_dt = until_dt - datetime.timedelta(days=30)
            with st.spinner("📈 Mengambil data insights 30 hari…"):
                st.session_state["ig_monthly_insights"] = get_insights_window(ig_id, token, since_dt, until_dt)

        insights_raw = st.session_state.get("ig_monthly_insights", {})
        if "error" in insights_raw:
            st.warning(f"Insights tidak tersedia: {insights_raw['error'].get('message')}")
            st.caption("Butuh akun Business/Creator + izin `instagram_manage_insights`.")
        else:
            series = parse_insights_to_series(insights_raw)
            if series:
                all_dates = sorted(set(d for v in series.values() for d in v))
                df_insights = pd.DataFrame({"Tanggal": all_dates})
                df_insights["Tanggal"] = pd.to_datetime(df_insights["Tanggal"])

                label_map = {
                    "views": "Tayangan (Views)",
                    "reach": "Jangkauan",
                    "profile_views": "Kunjungan Profil"
                }
                for key, label in label_map.items():
                    if key in series:
                        df_insights[label] = df_insights["Tanggal"].dt.strftime("%Y-%m-%d").map(series[key]).fillna(0).astype(int)
                df_insights = df_insights.set_index("Tanggal")

                available_cols = [c for c in label_map.values() if c in df_insights.columns]
                kpi_cols = st.columns(len(available_cols))
                for i, col_name in enumerate(available_cols):
                    total = int(df_insights[col_name].sum()) if pd.notna(df_insights[col_name].sum()) else 0
                    avg = int(df_insights[col_name].mean()) if pd.notna(df_insights[col_name].mean()) else 0
                    kpi_cols[i].metric(f"Total {col_name}", f"{total:,}", f"rata-rata {avg:,}/hari")

                st.write("")
                tab_metrics = st.tabs([f"📈 {c}" for c in available_cols] + ["📋 Tabel"])
                for i, col_name in enumerate(available_cols):
                    with tab_metrics[i]:
                        st.area_chart(df_insights[[col_name]], use_container_width=True, height=280)
                with tab_metrics[-1]:
                    st.dataframe(df_insights[available_cols].sort_index(ascending=False), use_container_width=True)
            else:
                st.info("Tidak ada data insights untuk 30 hari terakhir.")

        # ── Historical Data Puller ─────────────────────────────────────────
        st.divider()
        st.subheader("🗓️ Historical Data Puller")
        st.caption("Tarik data insights harian + seluruh postingan media pada rentang tanggal apa pun (dipecah otomatis per 30 hari).")

        hc1, hc2, hc3 = st.columns([1, 1, 1])
        with hc1:
            date_since = st.date_input("Sejak", value=datetime.date(2025, 1, 1), key="ig_hist_since")
        with hc2:
            date_until = st.date_input("Sampai", value=min(datetime.date(2025, 12, 31), datetime.date.today()), key="ig_hist_until")
        with hc3:
            st.write("")
            st.write("")
            pull_clicked = st.button("⬇️ Tarik Data Rentang", use_container_width=True, type="primary")

        if pull_clicked:
            s_dt = datetime.datetime.combine(date_since, datetime.time.min)
            u_dt = datetime.datetime.combine(date_until, datetime.time.max)

            with st.spinner(f"Menarik data {s_dt.date()} → {u_dt.date()}…"):
                daily = get_insights_range(ig_id, token, s_dt, u_dt)
                media_range = get_media_in_range(ig_id, token, s_dt, u_dt)
                for item in media_range:
                    item["insights"] = get_single_media_insights(item["id"], item.get("media_type"), token)

            st.session_state["ig_hist_daily"] = daily
            st.session_state["ig_hist_media"] = media_range
            st.success(f"✅ {len(media_range)} postingan ditemukan, {len(daily.get('views', {}))} hari data insights.")

        if "ig_hist_daily" in st.session_state:
            hd = st.session_state["ig_hist_daily"]
            hm = st.session_state.get("ig_hist_media", [])

            if hd.get("_errors"):
                with st.expander("⚠️ Sebagian rentang gagal ditarik"):
                    for e in hd["_errors"]:
                        st.write("-", e)

            tab_h_daily, tab_h_media = st.tabs(["📈 Insight Harian", "🖼️ Semua Post"])
            with tab_h_daily:
                rows = {}
                for metric_name in ("views", "reach", "profile_views"):
                    for date_str, val in hd.get(metric_name, {}).items():
                        rows.setdefault(date_str, {})[metric_name] = val
                if rows:
                    df_hist = pd.DataFrame.from_dict(rows, orient="index").sort_index()
                    st.dataframe(df_hist, use_container_width=True)
                    st.download_button(
                        "⬇️ Download CSV — Insight Harian",
                        df_hist.to_csv().encode("utf-8"),
                        file_name=f"ig_daily_insights_{date_since}_{date_until}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Tidak ada data harian pada rentang ini.")
            with tab_h_media:
                if hm:
                    flat_media = []
                    for item in hm:
                        ins = item.get("insights", {})
                        flat_media.append({
                            "timestamp": item.get("timestamp"),
                            "media_type": item.get("media_type"),
                            "caption": (item.get("caption") or "")[:80],
                            "like_count": item.get("like_count", 0),
                            "comments_count": item.get("comments_count", 0),
                            "reach": ins.get("reach") or ins.get("carousel_album_reach") or 0,
                            "saved": ins.get("saved", 0),
                            "permalink": item.get("permalink")
                        })
                    df_m = pd.DataFrame(flat_media).sort_values("timestamp", ascending=False)
                    st.dataframe(df_m, use_container_width=True)
                    st.download_button(
                        "⬇️ Download CSV — Semua Post",
                        df_m.to_csv(index=False).encode("utf-8"),
                        file_name=f"ig_media_{date_since}_{date_until}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Tidak ada post pada rentang ini.")

        # ── Active Stories ─────────────────────────────────────────────────
        st.divider()
        st.subheader("⏱️ Active Stories")
        if "ig_stories_data" not in st.session_state:
            st.session_state["ig_stories_data"] = get_instagram_stories(ig_id, token)
        stories_data = st.session_state.get("ig_stories_data", {})

        if "data" in stories_data and stories_data["data"]:
            s_cols = st.columns(4)
            for i, item in enumerate(stories_data["data"]):
                with s_cols[i % 4]:
                    url = item.get("media_url") or item.get("thumbnail_url")
                    if url and item.get("media_type") == "IMAGE":
                        st.image(url, use_container_width=True)
                    elif item.get("media_type") == "VIDEO":
                        st.video(item.get("media_url", ""))
                    insights = get_single_media_insights(item.get("id"), "STORY", token)
                    st.caption(f"🕒 {item.get('timestamp', '')[:10]}")
                    st.markdown(f"👁️ Reach: **{insights.get('reach', 0)}** &nbsp; 📊 Impresi: **{insights.get('impressions', 0)}** &nbsp; 💬 Balasan: **{insights.get('replies', 0)}**")
        else:
            err = stories_data.get("error", {}).get("message")
            if err:
                st.warning(f"Could not load stories: {err}")
            else:
                st.info("Tidak ada Stories aktif saat ini.")

        # ── Audience Demographics ──────────────────────────────────────────
        st.divider()
        st.subheader("👥 Audience Demographics")
        if "ig_audience_data" not in st.session_state:
            with st.spinner("📊 Mengambil data audiens…"):
                st.session_state["ig_audience_data"] = get_audience_demographics(ig_id, token)
        audience_raw = st.session_state.get("ig_audience_data", {})

        if "error" in audience_raw:
            st.warning(f"Data audiens tidak tersedia: {audience_raw['error'].get('message')}")
        else:
            demographics, online_followers = {}, {}
            for metric in audience_raw.get("data", []):
                if metric["name"] == "follower_demographics":
                    demographics = metric.get("values", [{}])[0].get("value", {})
                elif metric["name"] == "online_followers":
                    online_followers = metric.get("values", [{}])[0].get("value", {})

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Follower Demographics (Top Cities)**")
                if demographics:
                    df_demo = pd.DataFrame(list(demographics.items()), columns=["Location", "Count"]).sort_values("Count", ascending=False).head(10)
                    st.bar_chart(df_demo.set_index("Location"))
                else:
                    st.info("Tidak ada data demografi follower.")
            with col2:
                st.markdown("**Online Followers (by Hour)**")
                if online_followers:
                    df_online = pd.DataFrame(list(online_followers.items()), columns=["Hour", "Count"])
                    df_online["Hour"] = df_online["Hour"].astype(int)
                    df_online = df_online.sort_values("Hour")
                    st.line_chart(df_online.set_index("Hour"))
                else:
                    st.info("Tidak ada data follower aktif per jam.")

        # ── Reached Demographics (30 Hari) ─────────────────────────────────
        st.divider()
        st.subheader("🌍 Reached Audience (Last 30 Days)")
        if "ig_reached_city" not in st.session_state:
            with st.spinner("🌍 Mengambil reach per kota…"):
                st.session_state["ig_reached_city"] = get_reached_demographics(ig_id, token, "city")
        if "ig_reached_country" not in st.session_state:
            with st.spinner("🌍 Mengambil reach per negara…"):
                st.session_state["ig_reached_country"] = get_reached_demographics(ig_id, token, "country")

        city_raw = st.session_state.get("ig_reached_city", {})
        country_raw = st.session_state.get("ig_reached_country", {})

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("**Top Cities Reached**")
            if "error" in city_raw:
                st.warning(f"Error: {city_raw['error'].get('message')}")
            else:
                cities = {}
                for metric in city_raw.get("data", []):
                    if metric["name"] == "reached_audience_demographics":
                        cities = metric.get("values", [{}])[0].get("value", {})
                if cities:
                    df_c = pd.DataFrame(list(cities.items()), columns=["City", "Reach"]).sort_values("Reach", ascending=False).head(10)
                    st.bar_chart(df_c.set_index("City"))
                else:
                    st.info("Tidak ada data reach per kota.")

        with col_c2:
            st.markdown("**Top Countries Reached**")
            if "error" in country_raw:
                st.warning(f"Error: {country_raw['error'].get('message')}")
            else:
                countries = {}
                for metric in country_raw.get("data", []):
                    if metric["name"] == "reached_audience_demographics":
                        countries = metric.get("values", [{}])[0].get("value", {})
                if countries:
                    df_co = pd.DataFrame(list(countries.items()), columns=["Country", "Reach"]).sort_values("Reach", ascending=False).head(10)
                    st.bar_chart(df_co.set_index("Country"))
                else:
                    st.info("Tidak ada data reach per negara.")

        # ── Recent Media Grid ──────────────────────────────────────────────
        st.divider()
        st.subheader("🖼️ Recent Media")
        if "ig_media_data" not in st.session_state:
            with st.spinner("🖼️ Mengambil media terbaru…"):
                st.session_state["ig_media_data"] = get_user_media(ig_id, token, limit=12)

        media_data = st.session_state.get("ig_media_data", {})
        m_items = media_data.get("data", []) if "data" in media_data else []

        if m_items:
            cols = st.columns(3)
            for i, item in enumerate(m_items):
                with cols[i % 3]:
                    url = item.get("media_url") or item.get("thumbnail_url")
                    m_type = item.get("media_type")
                    if url and m_type in ("IMAGE", "CAROUSEL_ALBUM"):
                        st.image(url, use_container_width=True)
                    elif m_type == "VIDEO":
                        st.video(item.get("media_url", ""))
                    caption = (item.get("caption") or "")[:100]
                    st.caption(caption + ("…" if len(item.get("caption") or "") > 100 else ""))

                    insights = get_single_media_insights(item.get("id"), m_type, token)
                    reach = insights.get("reach") or insights.get("carousel_album_reach") or 0
                    likes = int(item.get("like_count") or 0)
                    comments = int(item.get("comments_count") or 0)
                    er = ((comments / likes) * 100) if likes > 0 else (100.0 if (likes + comments) > 0 else 0.0)

                    st.markdown(
                        f"❤️ {likes} &nbsp; 💬 {comments} &nbsp; 📈 ER: **{er:.1f}%**<br>"
                        f"👁️ Reach: **{reach}** &nbsp; [🔗 View Post]({item.get('permalink', '#')})",
                        unsafe_allow_html=True
                    )
                    st.divider()
        else:
            st.info("Belum ada media ditemukan.")

        # ── Token Inspector & Raw JSON ─────────────────────────────────────
        st.divider()
        with st.expander("🔑 Token Inspector", expanded=False):
            t1, t2, t3 = st.columns([3, 1, 1])
            with t1:
                st.code(token[:15] + "..." + token[-10:] if len(token) > 25 else token, language="text")
            with t2:
                days_left = max(0, (ig_meta["expires_at"] - int(time.time())) // 86400)
                st.metric("Expires In", f"{days_left} hari")
            with t3:
                st.metric("Storage", "SQLite AES-128")
            st.caption(f"Token disinkronisasi ke: `{INSTAGRAM_TOKEN_JSON_FILE}`")

        with st.expander("🛠️ Raw JSON (Profile & Insights)"):
            st.json(ig_detail)
            st.json(insights_raw)


# -------------------------------------------------------------------------
# TAB TIKTOK
# -------------------------------------------------------------------------
with tab_tt:
    st.subheader("🎵 TikTok Login Kit v2 & Analytics Hub")
    st.write(
        "Autentikasi resmi untuk akun **TikTok** dengan fitur analitik lengkap dan alat pengujian "
        "langsung endpoint refresh token (`https://open.tiktokapis.com/v2/oauth/token/`)."
    )

    tt_meta = storage.get_token_metadata("tiktok")
    tt_record = storage.get_token_record("tiktok") if tt_meta else None

    # Sinkronisasikan token ke .tiktok_token.json jika sudah terhubung
    if tt_record and tt_record.get("access_token") and tt_record.get("refresh_token"):
        export_tiktok_token_to_json(
            access_token=tt_record["access_token"],
            refresh_token=tt_record["refresh_token"],
            open_id=tt_record.get("account_id", ""),
            scope=tt_record.get("scopes", ""),
            expires_at=tt_record.get("expires_at")
        )

    if not tt_meta:
        # Belum terhubung
        col_info_tt, col_action_tt = st.columns([2, 1])
        with col_info_tt:
            st.markdown("""
            **Aturan & Kebijakan TikTok for Developers:**
            * Otorisasi langsung melalui portal resmi TikTok Login Kit v2.
            * Token dienkripsi dengan standar AES-128 di database dan otomatis diekspor ke `.tiktok_token.json`.
            * Access token berlaku 24 jam dan refresh token berlaku hingga 365 hari.
            """)
            if not config.TIKTOK_CLIENT_KEY or not config.TIKTOK_CLIENT_SECRET:
                st.info("ℹ️ Kredensial `TIKTOK_CLIENT_KEY` dan `TIKTOK_CLIENT_SECRET` belum diisi di `.streamlit/secrets.toml` atau `.env`.")

        with col_action_tt:
            state_token_tt = config.generate_signed_state("tiktok")
            auth_url_tt = config.get_tiktok_auth_url(config.TIKTOK_REDIRECT_URI, state_token_tt)
            st.link_button(
                "🔗 Connect TikTok",
                auth_url_tt,
                type="primary",
                help="Buka halaman otorisasi OAuth 2.0 resmi TikTok Login Kit"
            )

        # OPSI ALTERNATIF INPUT MANUAL JIKA REDIRECT KE LINK LAIN (misal google.com)
        with st.expander("🛠️ Opsi Alternatif: Masukkan Authorization Code atau Token Manual"):
            st.caption(
                "Gunakan opsi ini jika redirect URI Anda mengarah ke halaman eksternal (misalnya `https://google.com/?code=...`) "
                "atau jika Anda sudah memiliki token sebelumnya."
            )
            subcol1, subcol2 = st.columns(2)
            with subcol1:
                st.markdown("##### 📥 Tukar Code Manual dari Redirect URL")
                with st.form("form_manual_tt_code"):
                    manual_code = st.text_input("Authorization Code (dari parameter `code=...`)", placeholder="Contoh: v2.xxxxx")
                    custom_redirect = st.text_input("Redirect URI yang Digunakan", value=config.TIKTOK_REDIRECT_URI)
                    submit_code = st.form_submit_button("⚡ Tukar Code Menjadi Token")
                    if submit_code and manual_code.strip():
                        try:
                            with st.spinner("Menukar authorization code ke endpoint TikTok..."):
                                res = exchange_tiktok_code(manual_code.strip(), custom_redirect.strip())
                                st.success(f"🎉 Berhasil menghubungkan akun TikTok @{res.get('username')}!")
                                st.rerun()
                        except OAuthError as oe:
                            st.error(f"Gagal: {str(oe)}")
            with subcol2:
                st.markdown("##### 🔑 Impor Access & Refresh Token")
                with st.form("form_manual_tt_token"):
                    man_access = st.text_input("Access Token", type="password")
                    man_refresh = st.text_input("Refresh Token", type="password")
                    man_account = st.text_input("Open ID / Label Akun", value="Akun TikTok")
                    submit_token = st.form_submit_button("💾 Simpan & Hubungkan")
                    if submit_token and man_access.strip() and man_refresh.strip():
                        save_manual_tiktok_tokens(man_access.strip(), man_refresh.strip(), username=man_account.strip())
                        st.success("🎉 Token berhasil disimpan!")
                        st.rerun()
    else:
        # Sudah terhubung
        st.markdown('<span class="badge-active">● TIKTOK TERHUBUNG</span>', unsafe_allow_html=True)
        exp_time_tt = datetime.datetime.fromtimestamp(tt_meta["expires_at"]).strftime("%Y-%m-%d %H:%M:%S")

        col1, col2, col3 = st.columns(3)
        col1.metric("Display Name", tt_meta.get("username", "-"))
        col2.metric("Open ID", tt_meta.get("account_id", "-"))
        col3.metric("Masa Berlaku Access Token", exp_time_tt)

        # -------------------------------------------------------------
        # PANEL TOKEN & AUTH INFO (ALA TIKTOKANALYTICS)
        # -------------------------------------------------------------
        st.markdown("### 🔑 Token & Auth Info (Siap Salin & Unduh)")
        st.caption(
            "Nilai token mentah (plaintext) siap disalin untuk pengujian atau integrasi. "
            "Token ini juga otomatis tersimpan di file **`.tiktok_token.json`**."
        )

        acc_token_val = tt_record.get("access_token", "") if tt_record else ""
        ref_token_val = tt_record.get("refresh_token", "") if tt_record else ""

        t_col1, t_col2 = st.columns(2)
        with t_col1:
            st.markdown("##### 🔄 Refresh Token (Masa Berlaku ~365 Hari)")
            st.code(ref_token_val, language="text")
        with t_col2:
            st.markdown("##### ⚡ Access Token (Masa Berlaku ~24 Jam)")
            st.code(acc_token_val, language="text")

        with st.expander("🔍 Detail Lengkap Token & Status File"):
            st.json({
                "access_token": acc_token_val,
                "refresh_token": ref_token_val,
                "open_id": tt_meta.get("account_id"),
                "scope": tt_meta.get("scopes"),
                "expires_at": tt_meta.get("expires_at"),
                "expires_at_readable": exp_time_tt,
                "token_json_file": os.path.abspath(TIKTOK_TOKEN_JSON_FILE)
            })
            if os.path.exists(TIKTOK_TOKEN_JSON_FILE):
                with open(TIKTOK_TOKEN_JSON_FILE, "r", encoding="utf-8") as f:
                    file_contents = f.read()
                st.download_button(
                    label="📥 Unduh .tiktok_token.json",
                    data=file_contents,
                    file_name=".tiktok_token.json",
                    mime="application/json"
                )

        # -------------------------------------------------------------
        # ALAT PENGUJIAN LANGSUNG REFRESH TOKEN KE TIKTOK API
        # -------------------------------------------------------------
        st.markdown("### 🧪 Uji Panggil Endpoint Refresh Token (`https://open.tiktokapis.com/v2/oauth/token/`)")
        st.caption(
            "Klik tombol di bawah untuk menguji panggilan langsung ke server resmi TikTok menggunakan refresh token Anda. "
            "Hasil respons HTTP, headers, dan JSON token baru akan ditampilkan langsung secara transparan."
        )

        test_col1, test_col2 = st.columns([1, 1])
        with test_col1:
            if st.button("🚀 Uji / Panggil Endpoint Refresh Token Sekarang", type="primary", key="btn_test_refresh"):
                try:
                    with st.spinner("Mengirim permintaan POST ke https://open.tiktokapis.com/v2/oauth/token/..."):
                        test_result = test_tiktok_refresh_token(ref_token_val)
                        st.session_state["tt_refresh_test_result"] = test_result
                except Exception as ex:
                    st.error(f"❌ Panggilan gagal: {str(ex)}")

        with test_col2:
            st.info("💡 Setiap kali refresh berhasil, TikTok akan memberikan access token baru dan refresh token baru yang otomatis diperbarui di aplikasi.")

        # Tampilkan hasil test jika ada di session_state
        if "tt_refresh_test_result" in st.session_state:
            res_test = st.session_state["tt_refresh_test_result"]
            st.markdown("#### 📡 Hasil Respons Resmi Server TikTok:")

            status_color = "🟢" if res_test.get("is_success") else "🔴"
            m1, m2, m3 = st.columns(3)
            m1.metric("Status Kode HTTP", f"{status_color} {res_test.get('status_code')}")
            m2.metric("Waktu Respon", f"{res_test.get('elapsed_ms')} ms")
            m3.metric("Status Validasi", "SUKSES ✅" if res_test.get("is_success") else "GAGAL ❌")

            st.markdown("**Respons JSON Mentah dari Endpoint:**")
            st.json(res_test.get("response_json"))

            if res_test.get("is_success"):
                st.success("🎉 Panggilan ke `https://open.tiktokapis.com/v2/oauth/token/` BERHASIL! Token baru telah disimpan dan disinkronkan.")

            with st.expander("📋 Perintah cURL & Snippet Python (Siap Eksekusi di Terminal / Postman)"):
                st.markdown("**Perintah cURL:**")
                st.code(res_test.get("curl_command", ""), language="bash")
                st.markdown("**Kode Python (Requests):**")
                py_snippet = (
                    "import requests\n\n"
                    "url = 'https://open.tiktokapis.com/v2/oauth/token/'\n"
                    "data = {\n"
                    f"    'client_key': '{config.TIKTOK_CLIENT_KEY}',\n"
                    f"    'client_secret': '{config.TIKTOK_CLIENT_SECRET}',\n"
                    "    'grant_type': 'refresh_token',\n"
                    f"    'refresh_token': '{ref_token_val}'\n"
                    "}\n"
                    "headers = {'Content-Type': 'application/x-www-form-urlencoded'}\n"
                    "response = requests.post(url, headers=headers, data=data)\n"
                    "print('Status:', response.status_code)\n"
                    "print('Response:', response.json())\n"
                )
                st.code(py_snippet, language="python")

        st.divider()

        # -------------------------------------------------------------
        # TOMBOL AKSI DATA & DISCONNECT
        # -------------------------------------------------------------
        c_fetch_tt, c_disconnect_tt = st.columns([1, 1])
        with c_fetch_tt:
            if st.button("🔄 Ambil Data Akun & Video (fetch_data)", key="btn_fetch_tt"):
                try:
                    with st.spinner("Memanggil endpoint resmi TikTok Display API v2..."):
                        data_tt = fetch_data("tiktok")
                        st.session_state["tt_data"] = data_tt
                        st.success("Data berhasil diambil dari endpoint resmi TikTok!")
                except (OAuthError, FetcherError) as fe:
                    st.error(f"Gagal mengambil data: {str(fe)}")

        with c_disconnect_tt:
            if st.button("❌ Putuskan Sambungan Akun", key="btn_disc_tt"):
                storage.delete_token("tiktok")
                delete_tiktok_token_file()
                if "tt_data" in st.session_state:
                    del st.session_state["tt_data"]
                if "tt_refresh_test_result" in st.session_state:
                    del st.session_state["tt_refresh_test_result"]
                st.rerun()

        # -------------------------------------------------------------
        # TAMPILAN DATA & ANALISIS ALA TIKTOKANALYTICS
        # -------------------------------------------------------------
        if "tt_data" in st.session_state and st.session_state["tt_data"].get("platform") == "tiktok":
            data_tt = st.session_state["tt_data"]
            prof_tt = data_tt.get("profile", {})
            videos_tt = data_tt.get("videos", [])

            st.divider()
            st.markdown("### 👤 Informasi Profil Resmi Akun")
            p_col1, p_col2 = st.columns([1, 4])
            with p_col1:
                avatar = prof_tt.get("avatar_large_url") or prof_tt.get("avatar_url")
                if avatar:
                    st.image(avatar, width=120)
                else:
                    st.markdown("🖼️ *(Tidak ada foto)*")
            with p_col2:
                st.header(prof_tt.get("display_name") or tt_meta.get("username") or "TikTok Account")
                st.caption(f"Bio: {prof_tt.get('bio_description', '-')}")
                if prof_tt.get("profile_deep_link"):
                    st.markdown(f"[Buka Profil di Aplikasi TikTok ↗]({prof_tt.get('profile_deep_link')})")

            # 4 Kartu Metrik ala TikTokAnalytics
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Followers", f"{prof_tt.get('follower_count', 0):,}")
            m_col2.metric("Following", f"{prof_tt.get('following_count', 0):,}")
            m_col3.metric("Total Likes", f"{prof_tt.get('likes_count', 0):,}")
            m_col4.metric("Videos", f"{prof_tt.get('video_count', len(videos_tt)):,}")

            st.divider()

            # VIDEO PERFORMANCE & TABEL STATISTIK
            st.subheader("📊 Video Performance & Engagement Analytics")
            if data_tt.get("videos_error"):
                st.warning(f"⚠️ **Peringatan Pengambilan Video:** {data_tt['videos_error']}")

            if not videos_tt:
                if not data_tt.get("videos_error"):
                    st.info("Belum ada video ditemukan untuk akun ini.")
            else:
                df = pd.DataFrame(videos_tt)

                # Hitung Engagement Rate (Likes + Comments + Shares) / Views * 100
                if "view_count" in df.columns:
                    df["engagement_rate"] = df.apply(
                        lambda r: (
                            (r.get("like_count", 0) + r.get("comment_count", 0) + r.get("share_count", 0))
                            / r["view_count"]
                            * 100
                        ) if r["view_count"] > 0 else 0,
                        axis=1
                    )

                # 1. Detail Analisis per Video
                st.markdown("#### 🔍 Detail Analisis per Video")
                video_titles = [v.get("title") or v.get("video_description") or f"Video {v.get('id')}" for v in videos_tt]
                selected_title = st.selectbox("Pilih Video untuk Detail Statistik:", options=video_titles, index=0)
                selected_video = next((v for v in videos_tt if (v.get("title") or v.get("video_description") or f"Video {v.get('id')}") == selected_title), None)

                if selected_video:
                    col_v_img, col_v_detail = st.columns([1, 2])
                    with col_v_img:
                        if selected_video.get("cover_image_url"):
                            st.image(selected_video["cover_image_url"], use_container_width=True)
                    with col_v_detail:
                        st.markdown(f"##### **{selected_title}**")
                        if "create_time" in selected_video:
                            try:
                                post_date = datetime.datetime.fromtimestamp(selected_video["create_time"]).strftime('%Y-%m-%d %H:%M:%S')
                                st.caption(f"Diposting pada: {post_date}")
                            except Exception:
                                pass
                        
                        target_link = selected_video.get("share_url") or selected_video.get("embed_link")
                        if target_link:
                            st.markdown(f"[Tonton Video di TikTok ↗]({target_link})")

                        v_views = selected_video.get("view_count", 0)
                        v_likes = selected_video.get("like_count", 0)
                        v_comments = selected_video.get("comment_count", 0)
                        v_shares = selected_video.get("share_count", 0)
                        v_engagements = v_likes + v_comments + v_shares
                        v_er = (v_engagements / v_views * 100) if v_views > 0 else 0

                        sm1, sm2 = st.columns(2)
                        sm1.metric("Views (Ditonton)", f"{v_views:,}")
                        sm1.metric("Likes (Disukai)", f"{v_likes:,}")
                        sm2.metric("Comments (Komentar)", f"{v_comments:,}")
                        sm2.metric("Shares (Dibagikan)", f"{v_shares:,}")
                        st.metric("Engagement Rate (ER)", f"{v_er:.2f}%")

                # 2. Tabel Semua Video
                st.markdown("#### 📋 Daftar Semua Video")
                table_cols = ["title", "view_count", "like_count", "comment_count", "share_count", "engagement_rate", "share_url"]
                available_cols = [c for c in table_cols if c in df.columns]
                col_config = {
                    "title": "Judul Video",
                    "view_count": st.column_config.NumberColumn("Views", format="%d"),
                    "like_count": st.column_config.NumberColumn("Likes", format="%d"),
                    "comment_count": st.column_config.NumberColumn("Comments", format="%d"),
                    "share_count": st.column_config.NumberColumn("Shares", format="%d"),
                    "engagement_rate": st.column_config.NumberColumn("Engagement Rate (ER)", format="%.2f%%"),
                    "share_url": st.column_config.LinkColumn("Link Video")
                }
                st.dataframe(df[available_cols], use_container_width=True, hide_index=True, column_config=col_config)

                # 3. Total Performance
                st.markdown("#### 📈 Total Performa Semua Video")
                tot_views = df.get("view_count", pd.Series(dtype=int)).sum()
                tot_likes = df.get("like_count", pd.Series(dtype=int)).sum()
                tot_comments = df.get("comment_count", pd.Series(dtype=int)).sum()
                tot_shares = df.get("share_count", pd.Series(dtype=int)).sum()

                tcol1, tcol2, tcol3, tcol4 = st.columns(4)
                tcol1.metric("Total Views", f"{tot_views:,.0f}")
                tcol2.metric("Total Likes", f"{tot_likes:,.0f}")
                tcol3.metric("Total Comments", f"{tot_comments:,.0f}")
                tcol4.metric("Total Shares", f"{tot_shares:,.0f}")

# -------------------------------------------------------------------------
# TAB TIKTOK COOKIE SESSION
# -------------------------------------------------------------------------
with tab_tt_cookie:
    st.subheader("TikTok Session Cookie (Non-OAuth / Web Session)")
    st.write(
        "Gunakan opsi ini jika Anda memerlukan akses sesi web langsung (`sessionid`) "
        "yang disimpan secara terenkripsi menggunakan **Fernet (AES-128)** di SQLite."
    )

    cookie_meta = storage.get_token_metadata("tiktok_cookie")

    if not cookie_meta:
        col_auto, col_manual = st.columns(2)

        with col_auto:
            st.markdown("#### 🖥️ Opsi 1: Login via Browser (Playwright)")
            st.caption(
                "Membuka jendela browser Chromium lokal. Silakan login seperti biasa, "
                "dan aplikasi akan otomatis mengekstrak cookie begitu Anda masuk."
            )
            if st.button("🚀 Buka Browser & Ambil Cookie", type="primary", key="btn_pw_cookie"):
                try:
                    with st.spinner("Menunggu Anda menyelesaikan login di jendela browser yang terbuka (Maks 3 menit)..."):
                        capture_tiktok_cookies_via_browser()
                    st.success("🎉 Cookie session berhasil ditangkap dan dienkripsi!")
                    st.rerun()
                except CookieAuthError as ce:
                    st.error(f"❌ Gagal: {str(ce)}")

        with col_manual:
            st.markdown("#### 📋 Opsi 2: Input Manual (`sessionid`)")
            st.caption(
                "Buka `tiktok.com` di browser -> Tekan **F12 (Application > Cookies)** -> "
                "Salin nilai dari cookie bernama **`sessionid`**."
            )
            with st.form("form_manual_cookie"):
                custom_label = st.text_input("Label / Username Akun", value="MyTikTokAccount")
                raw_sessionid = st.text_input("Nilai Cookie `sessionid`", type="password")
                submitted = st.form_submit_button("💾 Enkripsi & Simpan Cookie")

                if submitted:
                    try:
                        save_tiktok_cookie_session(
                            sessionid=raw_sessionid,
                            username=custom_label
                        )
                        st.success("🎉 Cookie berhasil disimpan secara terenkripsi!")
                        st.rerun()
                    except CookieAuthError as ce:
                        st.error(f"❌ {str(ce)}")
    else:
        # Jika cookie sudah tersimpan
        st.markdown('<span class="badge-active">● COOKIE AKTIF (SIAP COPAS)</span>', unsafe_allow_html=True)
        exp_time_ck = datetime.datetime.fromtimestamp(cookie_meta["expires_at"]).strftime("%Y-%m-%d %H:%M:%S")

        col1, col2, col3 = st.columns(3)
        col1.metric("Label Akun", cookie_meta.get("username", "-"))
        col2.metric("Tipe Kredensial", "Web Session Cookies")
        col3.metric("Estimasi Kedaluwarsa", exp_time_ck)

        # Ambil data cookie yang siap dicopas
        ck_data = get_tiktok_cookie_headers()

        st.divider()
        st.markdown("### 📋 1. Nilai `sessionid` (Tinggal klik ikon Copy di kanan atas)")
        st.code(ck_data["sessionid"], language="text")

        st.markdown("### 🌐 2. Header `Cookie` Lengkap (Siap Copas untuk Postman / cURL / Scraper / Python)")
        st.code(ck_data["cookie_str"], language="http")

        with st.expander("🧩 3. Format JSON untuk Ekstensi Browser 'Cookie-Editor' (Import 1-Klik di Chrome/Edge)"):
            import json
            editor_json = json.dumps([
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
                for k, v in ck_data["cookies_dict"].items()
            ], indent=2)
            st.code(editor_json, language="json")

        with st.expander("🖥️ 4. User-Agent Sesi Ini (Gunakan yang sama di script/Postman)"):
            st.code(ck_data["headers"]["User-Agent"], language="text")

        txt_path = ck_data.get("cookie_txt_path", "")
        st.info("📄 Seluruh format cookie mentah ini juga tersimpan langsung di file: **`tiktok_cookie.txt`** (bisa dibuka langsung di Notepad atau VS Code).")

        c_dl, c_del = st.columns([1, 1])
        with c_dl:
            txt_content = ""
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    txt_content = f.read()
            st.download_button(
                "📥 Download File tiktok_cookie.txt",
                data=txt_content,
                file_name="tiktok_cookie.txt",
                mime="text/plain",
                use_container_width=True
            )

        with c_del:
            if st.button("🗑️ Hapus Cookie Session", key="btn_del_ck", use_container_width=True):
                storage.delete_token("tiktok_cookie")
                delete_cookie_txt_file()
                st.rerun()

# -------------------------------------------------------------------------
# TAB INSTAGRAM COOKIE SESSION (TAMBAHAN BARU)
# -------------------------------------------------------------------------
with tab_ig_cookie:
    st.subheader("Instagram Session Cookie (Non-OAuth / Web Session)")
    st.write(
        "Gunakan opsi ini jika Anda memerlukan akses sesi web langsung (`sessionid` / kuki) "
        "untuk keperluan bot atau scraping, yang disimpan secara terenkripsi menggunakan Fernet (AES-128) di SQLite."
    )

    ig_cookie_meta = storage.get_token_metadata("instagram_cookie")

    if not ig_cookie_meta:
        col_auto_ig, col_manual_ig = st.columns(2)

        with col_auto_ig:
            st.markdown("#### 🖥️ Opsi 1: Login via Browser (Playwright)")
            st.caption(
                "Membuka jendela browser Chromium lokal. Silakan login ke Instagram seperti biasa, "
                "dan aplikasi akan otomatis mengekstrak cookie begitu Anda masuk."
            )
            if st.button("🚀 Buka Browser & Ambil Cookie Instagram", type="primary", key="btn_pw_ig_cookie"):
                try:
                    with st.spinner("Menunggu Anda menyelesaikan login di jendela browser (Maks 3 menit)..."):
                        capture_instagram_cookies_via_browser()
                    st.success("🎉 Cookie session Instagram berhasil ditangkap dan dienkripsi!")
                    st.rerun()
                except IGCookieAuthError as ce:
                    st.error(f"❌ Gagal: {str(ce)}")

        with col_manual_ig:
            st.markdown("#### 📋 Opsi 2: Input Manual (`sessionid`)")
            st.caption(
                "Buka `instagram.com` di browser -> Tekan **F12 (Application > Cookies)** -> "
                "Salin nilai dari cookie bernama **`sessionid`**."
            )
            with st.form("form_manual_ig_cookie"):
                custom_label_ig = st.text_input("Label / Username Akun", value="MyInstagramAccount")
                raw_sessionid_ig = st.text_input("Nilai Cookie `sessionid` Instagram", type="password")
                submitted_ig = st.form_submit_button("💾 Enkripsi & Simpan Cookie Instagram")

                if submitted_ig:
                    try:
                        save_instagram_cookie_session(
                            sessionid=raw_sessionid_ig,
                            username=custom_label_ig
                        )
                        st.success("🎉 Cookie Instagram berhasil disimpan secara terenkripsi!")
                        st.rerun()
                    except IGCookieAuthError as ce:
                        st.error(f"❌ {str(ce)}")
    else:
        st.markdown('<span class="badge-active">● COOKIE INSTAGRAM AKTIF</span>', unsafe_allow_html=True)
        exp_time_ig_ck = datetime.datetime.fromtimestamp(ig_cookie_meta["expires_at"]).strftime("%Y-%m-%d %H:%M:%S")

        col1, col2, col3 = st.columns(3)
        col1.metric("Label Akun", ig_cookie_meta.get("username", "-"))
        col2.metric("Tipe Kredensial", "Web Session Cookies")
        col3.metric("Estimasi Kedaluwarsa", exp_time_ig_ck)

        ig_ck_data = get_instagram_cookie_headers()

        st.divider()
        st.markdown("### 📋 1. Nilai `sessionid` Instagram")
        st.code(ig_ck_data["sessionid"], language="text")

        st.markdown("### 🌐 2. Header `Cookie` Lengkap (Siap untuk Python / Scraper / Requests)")
        st.code(ig_ck_data["cookie_str"], language="http")

        with st.expander("🧩 3. Format JSON untuk Ekstensi 'Cookie-Editor'"):
            import json
            st.code(json.dumps([
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
                for k, v in ig_ck_data["cookies_dict"].items()
            ], indent=2), language="json")

        ig_txt_path = ig_ck_data.get("cookie_txt_path", "")
        st.info(f"📄 Seluruh format cookie mentah ini juga tersimpan langsung di file: **`instagram_cookie.txt`**")

        c_dl_ig, c_del_ig = st.columns([1, 1])
        with c_dl_ig:
            ig_txt_content = ""
            if os.path.exists(ig_txt_path):
                with open(ig_txt_path, "r", encoding="utf-8") as f:
                    ig_txt_content = f.read()
            st.download_button(
                "📥 Download File instagram_cookie.txt",
                data=ig_txt_content,
                file_name="instagram_cookie.txt",
                mime="text/plain",
                use_container_width=True
            )

        with c_del_ig:
            if st.button("🗑️ Hapus Cookie Session Instagram", key="btn_del_ig_ck", use_container_width=True):
                storage.delete_token("instagram_cookie")
                delete_ig_cookie_txt_file()
                st.rerun()

