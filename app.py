import os
import sys
import datetime
import streamlit as st

# Pastikan direktori root proyek berada di sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pandas as pd

import importlib
import src.storage
importlib.reload(src.storage)
import src.token_manager
importlib.reload(src.token_manager)
import src.fetcher
importlib.reload(src.fetcher)

from src import storage, config
from src.token_manager import (
    exchange_instagram_code,
    exchange_tiktok_code,
    get_valid_token,
    test_tiktok_refresh_token,
    save_manual_tiktok_tokens,
    delete_tiktok_token_file,
    export_tiktok_token_to_json,
    TIKTOK_TOKEN_JSON_FILE,
    OAuthError
)
from src.fetcher import fetch_data, FetcherError

import importlib
import src.cookie_manager
importlib.reload(src.cookie_manager)

from src.cookie_manager import (
    save_tiktok_cookie_session,
    capture_tiktok_cookies_via_browser,
    get_tiktok_cookie_headers,
    delete_cookie_txt_file,
    CookieAuthError
)

import src.instagram_cookie_manager
importlib.reload(src.instagram_cookie_manager)

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
if "code" in params and "state" in params:
    code = params["code"]
    state = params["state"]

    with st.spinner("Memproses otentikasi OAuth dan memverifikasi tanda tangan HMAC..."):
        # Verifikasi HMAC state dan kedaluwarsa 10 menit
        is_valid, platform, error_msg = config.verify_signed_state(state)

        if not is_valid:
            st.error(f"❌ **Validasi State Gagal:** {error_msg}")
            st.query_params.clear()
        else:
            try:
                redirect_uri = config.INSTAGRAM_REDIRECT_URI if platform == "instagram" else config.TIKTOK_REDIRECT_URI
                if platform == "instagram":
                    res = exchange_instagram_code(code, redirect_uri)
                    st.success(f"🎉 Berhasil menghubungkan akun Instagram **@{res.get('username')}**!")
                elif platform == "tiktok":
                    res = exchange_tiktok_code(code, redirect_uri)
                    st.success(f"🎉 Berhasil menghubungkan akun TikTok **@{res.get('username')}**!")
                else:
                    st.error(f"Platform {platform} tidak dikenali.")

                # Bersihkan URL query parameter setelah berhasil diproses
                st.query_params.clear()
                st.rerun()

            except OAuthError as oe:
                st.error(f"❌ **Autentikasi Gagal:** {str(oe)}")
                st.query_params.clear()
            except Exception as ex:
                st.error(f"❌ **Terjadi Kesalahan Server:** ({ex.__class__.__name__})")
                st.query_params.clear()

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
    st.subheader("Instagram Graph API with Instagram Login")
    st.write(
        "Autentikasi resmi untuk akun **Instagram Professional (Business atau Creator)**. "
        "Menggunakan scope `instagram_business_basic` untuk membaca profil dan media publik milik akun sendiri."
    )

    ig_meta = storage.get_token_metadata("instagram")

    if not ig_meta:
        # Belum terhubung
        col_info, col_action = st.columns([2, 1])
        with col_info:
            st.markdown("""
            **Aturan & Kebijakan Meta:**
            * Menghubungkan akun secara langsung ke jendela otorisasi resmi Instagram/Facebook.
            * Tidak ada form username/password lokal.
            * Token jangka panjang (*Long-Lived Token*) berlaku selama 60 hari dan direfresh secara otomatis sebelum kedaluwarsa.
            """)
            if not config.INSTAGRAM_APP_ID or not config.INSTAGRAM_APP_SECRET:
                st.info("ℹ️ Kredensial `INSTAGRAM_APP_ID` dan `INSTAGRAM_APP_SECRET` belum diisi di `.streamlit/secrets.toml` atau `.env`. Harap isi untuk menguji koneksi langsung ke Meta.")

        with col_action:
            state_token = config.generate_signed_state("instagram")
            auth_url = config.get_instagram_auth_url(config.INSTAGRAM_REDIRECT_URI, state_token)
            st.link_button(
                "🔗 Connect Instagram",
                auth_url,
                type="primary",
                help="Buka halaman otorisasi OAuth 2.0 resmi Instagram Login"
            )
    else:
        # Sudah terhubung
        st.markdown('<span class="badge-active">● TERHUBUNG</span>', unsafe_allow_html=True)
        exp_time = datetime.datetime.fromtimestamp(ig_meta["expires_at"]).strftime("%Y-%m-%d %H:%M:%S")

        col1, col2, col3 = st.columns(3)
        col1.metric("Username Akun", f"@{ig_meta['username']}")
        col2.metric("Account ID", ig_meta["account_id"])
        col3.metric("Masa Berlaku Token", exp_time)

        st.caption(f"🔒 Token tersimpan dalam keadaan terenkripsi Fernet (SQLite). Scope: `{ig_meta.get('scopes')}`")

        c_fetch, c_disconnect = st.columns([1, 1])
        with c_fetch:
            if st.button("🔄 Ambil Data Akun (fetch_data)", key="btn_fetch_ig"):
                try:
                    with st.spinner("Memanggil endpoint resmi Instagram Graph API..."):
                        data = fetch_data("instagram")
                        st.session_state["ig_data"] = data
                        st.success("Data berhasil diambil dari endpoint resmi!")
                except (OAuthError, FetcherError) as fe:
                    st.error(f"Gagal mengambil data: {str(fe)}")

        with c_disconnect:
            if st.button("❌ Putuskan Sambungan Akun", key="btn_disc_ig"):
                storage.delete_token("instagram")
                if "ig_data" in st.session_state:
                    del st.session_state["ig_data"]
                st.rerun()

        # Tampilkan data jika sudah diambil
        if "ig_data" in st.session_state and st.session_state["ig_data"].get("platform") == "instagram":
            data = st.session_state["ig_data"]
            prof = data.get("profile", {})
            media = data.get("media", [])

            st.divider()
            st.markdown("### 👤 Informasi Profil Resmi Akun")
            p_col1, p_col2 = st.columns([1, 4])
            with p_col1:
                if prof.get("profile_picture_url"):
                    st.image(prof["profile_picture_url"], width=100)
                else:
                    st.markdown("🖼️ *(Tidak ada foto)*")
            with p_col2:
                st.write(f"**Nama Tampilan:** {prof.get('name', '-')}")
                st.write(f"**Username:** @{prof.get('username', '-')}")
                st.write(f"**Tipe Akun:** {prof.get('account_type', '-')}")

            st.markdown("### 📸 Media Terbaru Milik Akun")
            if data.get("media_error"):
                st.warning(f"⚠️ **Peringatan Pengambilan Media:** {data['media_error']}")

            if not media:
                if not data.get("media_error"):
                    st.info("Belum ada media/postingan ditemukan untuk akun ini.")
            else:
                cols = st.columns(3)
                for idx, m in enumerate(media):
                    with cols[idx % 3]:
                        media_url = m.get("media_url") or m.get("thumbnail_url")
                        if media_url:
                            st.image(media_url, use_container_width=True)
                        st.caption(f"**Tipe:** {m.get('media_type')} | [Lihat Post]({m.get('permalink')})")
                        if m.get("caption"):
                            st.write(m.get("caption")[:100] + "...")


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

