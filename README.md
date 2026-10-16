# 🔐 Multi-Platform Official OAuth 2.0 Hub (Instagram & TikTok)

Aplikasi Streamlit berbasis Python untuk menghubungkan akun **Instagram (Business/Creator)** dan **TikTok** secara resmi melalui protokol **OAuth 2.0**. Token disimpan secara aman dan terenkripsi, serta modul pengambil data menggunakan token tersebut untuk memanggil API resmi platform.

---

## 📚 1. Ringkasan Temuan Riset Dokumentasi Resmi (Meta & TikTok for Developers)

Sesuai aturan ketat, seluruh implementasi endpoint, parameter, scope, dan masa berlaku token mengacu pada dokumentasi resmi terbaru:

### A. Meta for Developers — Instagram API with Instagram Login
* **Tipe Akun:** Instagram Professional (Business atau Creator account).
* **Endpoint Otorisasi:**
  - URL: `https://www.instagram.com/oauth/authorize`
  - Parameter: `client_id`, `redirect_uri`, `response_type=code`, `scope=instagram_business_basic`, `state={hmac_state}`, `force_authentication=1`, `enable_fb_login=0`.
* **Endpoint Penukaran Token (Dua Tahap):**
  1. **Short-Lived Token (1 Jam):**
     - `POST https://api.instagram.com/oauth/access_token`
     - Parameter Body: `client_id`, `client_secret`, `grant_type=authorization_code`, `redirect_uri`, `code` (karakter `#_` yang terkadang disematkan Meta di akhir kode wajib dibersihkan).
     - Format respons yang didukung: Format datar `{"access_token", "user_id"}` dan format terbungkus `{"data": [{"access_token", "user_id"}]}`.
     - Mengembalikan: `access_token` (berlaku ~1 jam) dan `user_id`.
  2. **Long-Lived Token (60 Hari):**
     - `GET https://graph.instagram.com/access_token`
     - Parameter Query: `grant_type=ig_exchange_token`, `client_secret={secret}`, `access_token={short_lived_token}`.
     - Mengembalikan: `access_token` jangka panjang dengan `expires_in=5184000` (~60 hari).
* **Aturan Refresh Token Long-Lived:**
  - `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={long_lived_token}`
  - **Syarat Ketat Meta:** Token hanya dapat diperbarui jika usianya sudah **minimal 24 jam** sejak dibuat dan **belum kedaluwarsa penuh** (< 60 hari). Jika sudah lewat 60 hari tanpa direfresh, token mati total dan pengguna harus login ulang.
  - Hasil refresh mengatur ulang masa berlaku menjadi 60 hari ke depan.
* **Endpoint Data Akun Sendiri:**
  - Profil: `GET https://graph.instagram.com/v21.0/me?fields=id,username,name,profile_picture_url,account_type`
  - Media: `GET https://graph.instagram.com/v21.0/me/media?fields=id,caption,media_type,media_url,permalink,thumbnail_url,timestamp`

---

### B. TikTok for Developers — Login Kit v2 & Display API
* **Endpoint Otorisasi:**
  - URL: `https://www.tiktok.com/v2/auth/authorize/`
  - Parameter: `client_key`, `scope=user.info.basic,user.info.profile,video.list`, `response_type=code`, `redirect_uri`, `state={hmac_state}`.
* **Endpoint Penukaran Token:**
  - `POST https://open.tiktokapis.com/v2/oauth/token/`
  - Headers: `Content-Type: application/x-www-form-urlencoded`
  - Parameter Body: `client_key`, `client_secret`, `grant_type=authorization_code`, `code`, `redirect_uri`.
  - Mengembalikan objek `data`: `access_token` (berlaku **24 jam / 86400 detik**), `refresh_token` (berlaku **365 hari / 1 tahun**), `open_id`, `scope`.
* **Aturan Refresh Token:**
  - `POST https://open.tiktokapis.com/v2/oauth/token/`
  - Parameter: `client_key`, `client_secret`, `grant_type=refresh_token`, `refresh_token={refresh_token}`.
  - Mengembalikan `access_token` baru (24 jam) dan pasangan `refresh_token` baru.
* **Endpoint Data Akun Sendiri:**
  - Profil (Display API): `GET https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,avatar_large_url,display_name,bio_description,profile_deep_link,is_verified` (Header: `Authorization: Bearer <access_token>`).
  - Video Milik Sendiri: `POST https://open.tiktokapis.com/v2/video/list/?fields=id,title,video_description,duration,cover_image_url,like_count,comment_count,share_count,view_count` (Header: `Authorization: Bearer <access_token>`, Body JSON: `{"max_count": 10}`).

---

## 🛡️ 2. Arsitektur Keamanan & Kepatuhan Aturan

Aplikasi ini menerapkan standar keamanan ketat:

1. **Anti-CSRF & State Signature (HMAC-SHA256):**
   - Mengatasi hilangnya `st.session_state` Streamlit saat redirect eksternal.
   - Format state: `<platform>:<timestamp>:<nonce>:<hmac_signature>`.
   - Backend memverifikasi tanda tangan HMAC dan membatasi masa berlaku maksimal **10 menit (600 detik)**.
2. **Penyimpanan Terenkripsi (Fernet AES-128):**
   - Database lokal SQLite (`tokens.db`) menyimpan `access_token_enc` dan `refresh_token_enc`.
   - Kunci enkripsi dibaca dari variabel lingkungan `TOKEN_ENCRYPTION_KEY` (tidak ada nilai default hardcoded).
   - Nilai token plaintext didekripsi hanya di dalam memori saat pemanggilan API, dan **tidak pernah di-log, dicetak ke konsol, atau ditampilkan di antarmuka pengguna**.
3. **Penyegaran Otomatis (`get_valid_token(platform)`):**
   - Titik masuk autentikasi utama untuk modul `fetcher.py`.
   - Otomatis memperbarui token sebelum kedaluwarsa sesuai aturan platform resmi.
4. **Isolasi Kepemilikan Data:**
   - Aplikasi HANYA memanggil endpoint akun yang terautentikasi (`/me` dan daftar video milik sendiri).
   - Tidak ada fitur mengambil data akun publik lain atau akun privat lain.
5. **Tanpa Form Kredensial Manual:**
   - Tidak ada form input username, password, atau kode SMS/PIN verifikasi.
   - Tidak ada penggunaan Selenium, Playwright, ataupun penyimpanan cookie sesi.
6. **Pencegahan Kebocoran URL pada Error:**
   - Pesan exception jaringan tidak menyertakan representasi string URL mentah (`str(e)`) agar `client_secret` atau token yang berada di parameter query tidak bocor ke log atau layar pengguna.

---

## 📁 3. Struktur File Proyek

```text
D:\streamlit\
│
├── .streamlit/
│   ├── secrets.toml            # Konfigurasi kredensial lokal (diabaikan oleh git)
│   └── secrets.toml.example    # Template secrets dengan placeholder aman
├── assets/
│   └── app_icon.png            # Icon visual aplikasi Streamlit
├── src/
│   ├── __init__.py             # Inisialisasi package src
│   ├── config.py               # Konfigurasi, penandatangan & verifikasi HMAC, URL builder
│   ├── storage.py              # Skema SQLite (tokens.db) & fungsi enkripsi/dekripsi Fernet
│   ├── token_manager.py        # Pertukaran kode OAuth & get_valid_token(platform)
│   ├── fetcher.py              # Modul pemanggilan API resmi Instagram & TikTok
│   └── cookie_manager.py       # Manajemen sesi cookie web TikTok (Playwright & manual)
├── tests/
│   ├── __init__.py             # Inisialisasi package tests
│   └── test_core.py            # Unit test HMAC state, enkripsi token, dan py_compile
├── .env.example                # Template variabel lingkungan alternatif
├── .gitignore                  # Mengabaikan tokens.db, .env, secrets.toml, .venv, __pycache__, binary
├── app.py                      # UI Streamlit (Tab Instagram & TikTok, OAuth callback handling)
├── requirements.txt            # Daftar pustaka dependensi (streamlit, cryptography, requests, dll.)
├── run.bat                     # Skrip peluncur instan untuk Windows
└── README.md                   # Dokumentasi teknis, ringkasan riset, dan status pengujian
```

---

## 🧪 4. Status Pengujian

Berikut adalah laporan jujur dan transparan mengenai apa yang telah diuji dan apa yang belum diuji:

### ✅ Apa yang SUDAH Diuji (Unit Tests & Kompilasi Lolos 100%)
Pengujian dijalankan melalui suite `tests/test_core.py` menggunakan Python 3.10 dan seluruhnya lulus (`OK`):
1. **`verify_signed_state` Valid**: Memastikan state yang dibuat dengan secret key yang benar diterima dan didekode dengan platform yang sesuai.
2. **`verify_signed_state` Kedaluwarsa**: Memastikan state yang umurnya melebihi batas (contoh: 15 menit) ditolak dengan pesan error kedaluwarsa.
3. **`verify_signed_state` Manipulasi Tanda Tangan**: Memastikan modifikasi 1 karakter sekalipun pada tanda tangan HMAC langsung ditolak (anti-CSRF/tampering).
4. **Roundtrip Enkripsi/Dekripsi Fernet**: Memastikan token acak yang dienkripsi menghasilkan ciphertext yang aman dan dapat didekripsi kembali persis seperti aslinya.
5. **Penanganan Token Kosong**: Memastikan input string kosong tidak menyebabkan crash atau kegagalan program.
6. **Kompilasi Sintaksis (`py_compile`)**: Seluruh file proyek (`app.py`, `src/`, `tests/`) terkompilasi tanpa error sintaksis.
7. **Pemisahan Error Pengambilan Data**: Modul `fetcher.py` telah diperbarui untuk mengembalikan `media_error` dan `videos_error` secara eksplisit, dan `app.py` menampilkannya via `st.warning`.

### ⚠️ Apa yang BELUM Diuji (Alur Produksi Langsung)
* **Alur OAuth Sungguhan ke Server Meta dan TikTok BELUM diuji secara langsung (live end-to-end)**:
  - Pengujian live memerlukan aplikasi aktif yang terdaftar di Meta for Developers dan TikTok Developer Portal dengan `App ID`/`Client Key` dan `Secret` yang sah.
  - Memerlukan interaksi login langsung oleh pemilik akun Instagram Professional atau akun TikTok di browser.
* **Pemanggilan Endpoint Data Riil**:
  - Pemanggilan langsung ke `https://graph.instagram.com/v21.0/me/media` dan `https://open.tiktokapis.com/v2/video/list/` dengan access token riil belum dilakukan terhadap API server produksi.

---

## ⚠️ 5. Catatan Penting Portal Pengembang (Prasyarat Wajib)

1. **Persyaratan HTTPS pada Redirect URI (Gunakan Tunnel):**
   - Meta for Developers dan TikTok Developer Portal mewajibkan Redirect URI menggunakan protokol **HTTPS** (bahkan untuk pengujian pada sebagian besar tipe aplikasi).
   - Saat mengembangkan secara lokal di `localhost:8501`, pengembang sangat disarankan menggunakan utilitas tunnel seperti:
     - **ngrok**: `ngrok http 8501` (menghasilkan URL HTTPS seperti `https://xxxx.ngrok-free.app/`)
     - **Cloudflare Tunnel** atau **localtunnel**
   - Masukkan URL HTTPS tersebut ke pengaturan portal pengembang dan ubah `INSTAGRAM_REDIRECT_URI` serta `TIKTOK_REDIRECT_URI` di [`.streamlit/secrets.toml`](file:///D:/streamlit/.streamlit/secrets.toml).

2. **Tinjauan Izin (Scope Review) di TikTok Developer Portal:**
   - Di TikTok for Developers, izin seperti `video.list` atau data profil tertentu berada dalam kategori sensitif/terbatas (*Restricted*).
   - Agar aplikasi dapat mengakses video atau data pengguna publik, aplikasi harus melalui proses **App Review** dan verifikasi organisasi bisnis resmi di portal TikTok. Selama tahap pengembangan (*Sandbox/Staging*), Anda hanya dapat mengotorisasi akun yang didaftarkan sebagai *Test Account*.

---

## 🚀 6. Cara Menjalankan Aplikasi

### Langkah 1: Pasang Dependensi & Jalankan
```powershell
cd D:\streamlit
.\.venv\Scripts\activate
streamlit run app.py
```
*Atau klik dua kali file **`run.bat`**.*

### Langkah 2: Konfigurasi Kredensial
Salin [`.streamlit/secrets.toml.example`](file:///D:/streamlit/.streamlit/secrets.toml.example) ke [`.streamlit/secrets.toml`](file:///D:/streamlit/.streamlit/secrets.toml), kemudian isi:

```toml
# Buat kunci enkripsi 32-byte base64 baru dengan:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY = "YOUR_FERNET_KEY_32_BYTES_BASE64_HERE"
STATE_SIGNING_SECRET = "YOUR_RANDOM_HMAC_SIGNING_SECRET_KEY"

# Meta for Developers (Instagram Login)
INSTAGRAM_APP_ID = "YOUR_INSTAGRAM_APP_ID"
INSTAGRAM_APP_SECRET = "YOUR_INSTAGRAM_APP_SECRET"
INSTAGRAM_REDIRECT_URI = "http://localhost:8501/"

# TikTok for Developers (Login Kit v2)
TIKTOK_CLIENT_KEY = "YOUR_TIKTOK_CLIENT_KEY"
TIKTOK_CLIENT_SECRET = "YOUR_TIKTOK_CLIENT_SECRET"
TIKTOK_REDIRECT_URI = "http://localhost:8501/"
```
