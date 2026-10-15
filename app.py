import streamlit as st
import datetime
import storage
import config
from token_manager import (
    exchange_instagram_code,
    exchange_tiktok_code,
    get_valid_token,
    OAuthError
)
from fetcher import fetch_data, FetcherError

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="Official OAuth 2.0 Hub (Instagram & TikTok)",
    page_icon="🔐",
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

st.title("🔐 Multi-Platform Official OAuth Hub")
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
tab_ig, tab_tt = st.tabs(["📸 Instagram (Business / Creator)", "🎵 TikTok (Login Kit v2)"])

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
    st.subheader("TikTok Login Kit v2 & Display API")
    st.write(
        "Autentikasi resmi untuk akun **TikTok**. "
        "Menggunakan scope `user.info.basic`, `user.info.profile`, dan `video.list` untuk mengambil data profil dan video milik akun sendiri."
    )

    tt_meta = storage.get_token_metadata("tiktok")

    if not tt_meta:
        # Belum terhubung
        col_info_tt, col_action_tt = st.columns([2, 1])
        with col_info_tt:
            st.markdown("""
            **Aturan & Kebijakan TikTok for Developers:**
            * Otorisasi langsung melalui portal resmi TikTok Login Kit v2.
            * Tidak ada form username/password atau kode OTP SMS di aplikasi ini.
            * Access token berlaku selama 24 jam dan refresh token berlaku hingga 365 hari. Modul sistem otomatis memperbarui token saat hampir kedaluwarsa.
            """)
            if not config.TIKTOK_CLIENT_KEY or not config.TIKTOK_CLIENT_SECRET:
                st.info("ℹ️ Kredensial `TIKTOK_CLIENT_KEY` dan `TIKTOK_CLIENT_SECRET` belum diisi di `.streamlit/secrets.toml` atau `.env`. Harap isi untuk menguji koneksi langsung ke TikTok.")

        with col_action_tt:
            state_token_tt = config.generate_signed_state("tiktok")
            auth_url_tt = config.get_tiktok_auth_url(config.TIKTOK_REDIRECT_URI, state_token_tt)
            st.link_button(
                "🔗 Connect TikTok",
                auth_url_tt,
                type="primary",
                help="Buka halaman otorisasi OAuth 2.0 resmi TikTok Login Kit"
            )
    else:
        # Sudah terhubung
        st.markdown('<span class="badge-active">● TERHUBUNG</span>', unsafe_allow_html=True)
        exp_time_tt = datetime.datetime.fromtimestamp(tt_meta["expires_at"]).strftime("%Y-%m-%d %H:%M:%S")

        col1, col2, col3 = st.columns(3)
        col1.metric("Display Name", tt_meta.get("username", "-"))
        col2.metric("Open ID", tt_meta.get("account_id", "-"))
        col3.metric("Masa Berlaku Access Token", exp_time_tt)

        st.caption(f"🔒 Token tersimpan dalam keadaan terenkripsi Fernet (SQLite). Scope: `{tt_meta.get('scopes')}`")

        c_fetch_tt, c_disconnect_tt = st.columns([1, 1])
        with c_fetch_tt:
            if st.button("🔄 Ambil Data Akun (fetch_data)", key="btn_fetch_tt"):
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
                if "tt_data" in st.session_state:
                    del st.session_state["tt_data"]
                st.rerun()

        # Tampilkan data jika sudah diambil
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
                    st.image(avatar, width=100)
                else:
                    st.markdown("🖼️ *(Tidak ada foto)*")
            with p_col2:
                st.write(f"**Display Name:** {prof_tt.get('display_name', '-')}")
                st.write(f"**Bio:** {prof_tt.get('bio_description', '-')}")
                st.write(f"**Terverifikasi:** {'Ya ✅' if prof_tt.get('is_verified') else 'Tidak ❌'}")
                if prof_tt.get("profile_deep_link"):
                    st.write(f"[Buka Profil di Aplikasi TikTok]({prof_tt.get('profile_deep_link')})")

            st.markdown("### 🎵 Video Milik Akun Sendiri")
            if data_tt.get("videos_error"):
                st.warning(f"⚠️ **Peringatan Pengambilan Video:** {data_tt['videos_error']}")

            if not videos_tt:
                if not data_tt.get("videos_error"):
                    st.info("Belum ada video ditemukan untuk akun ini.")
            else:
                cols = st.columns(3)
                for idx, v in enumerate(videos_tt):
                    with cols[idx % 3]:
                        cover = v.get("cover_image_url")
                        if cover:
                            st.image(cover, use_container_width=True)
                        st.caption(f"**Judul:** {v.get('title') or v.get('video_description') or 'Video'}")
                        st.write(f"❤️ {v.get('like_count', 0)} | 💬 {v.get('comment_count', 0)} | 👁️ {v.get('view_count', 0)}")
                        if v.get("embed_link"):
                            st.markdown(f"[Tonton di TikTok]({v.get('embed_link')})")