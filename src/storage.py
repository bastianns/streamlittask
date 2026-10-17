import sqlite3
import os
import time
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import sys
BASE_DIR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR_ROOT not in sys.path:
    sys.path.insert(0, BASE_DIR_ROOT)

from src.config import TOKEN_ENCRYPTION_KEY, BASE_DIR

DB_FILE = os.environ.get("TOKENS_DB_PATH", os.path.join(BASE_DIR, "tokens.db"))


def _get_cipher() -> Fernet:
    """Mengembalikan objek Fernet untuk enkripsi dan dekripsi token."""
    key = TOKEN_ENCRYPTION_KEY
    if not key:
        raise ValueError("TOKEN_ENCRYPTION_KEY belum dikonfigurasi. Atur variabel lingkungan ini terlebih dahulu.")
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)

def init_db():
    """Menginisialisasi skema tabel database SQLite jika belum ada."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                platform TEXT PRIMARY KEY,
                account_id TEXT,
                username TEXT,
                access_token_enc TEXT NOT NULL,
                refresh_token_enc TEXT,
                expires_at INTEGER NOT NULL,
                scopes TEXT,
                created_at INTEGER NOT NULL
            )
        """)
        conn.commit()

# Inisialisasi DB saat modul pertama kali diimpor
init_db()

def encrypt_token(plain_token: str) -> str:
    """Mengenkripsi token menggunakan Fernet."""
    if not plain_token:
        return ""
    cipher = _get_cipher()
    return cipher.encrypt(plain_token.encode("utf-8")).decode("utf-8")

def decrypt_token(encrypted_token: str) -> str:
    """Mendekripsi token menggunakan Fernet."""
    if not encrypted_token:
        return ""
    cipher = _get_cipher()
    return cipher.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")

def save_token(
    platform: str,
    account_id: str,
    username: str,
    access_token: str,
    refresh_token: Optional[str],
    expires_at: int,
    scopes: str
) -> None:
    """
    Menyimpan token yang telah dienkripsi ke database SQLite.
    PENTING: Jangan pernah mencetak atau me-log nilai token dalam bentuk apa pun.
    """
    platform = platform.lower().strip()
    access_token_enc = encrypt_token(access_token)
    refresh_token_enc = encrypt_token(refresh_token) if refresh_token else None
    created_at = int(time.time())

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tokens (
                platform, account_id, username, access_token_enc, refresh_token_enc, expires_at, scopes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform) DO UPDATE SET
                account_id=excluded.account_id,
                username=excluded.username,
                access_token_enc=excluded.access_token_enc,
                refresh_token_enc=excluded.refresh_token_enc,
                expires_at=excluded.expires_at,
                scopes=excluded.scopes,
                created_at=excluded.created_at
        """, (
            platform,
            account_id,
            username,
            access_token_enc,
            refresh_token_enc,
            expires_at,
            scopes,
            created_at
        ))
        conn.commit()

def get_token_record(platform: str) -> Optional[Dict[str, Any]]:
    """
    Membaca record token dari SQLite dan mendekripsi access_token serta refresh_token.
    Mengembalikan dictionary data atau None jika tidak ditemukan.
    """
    platform = platform.lower().strip()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tokens WHERE platform = ?", (platform,))
        row = cursor.fetchone()
        if not row:
            return None

        # Dekripsi token
        access_token = decrypt_token(row["access_token_enc"])
        refresh_token = decrypt_token(row["refresh_token_enc"]) if row["refresh_token_enc"] else None

        return {
            "platform": row["platform"],
            "account_id": row["account_id"],
            "username": row["username"],
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": row["expires_at"],
            "scopes": row["scopes"],
            "created_at": row["created_at"]
        }

def get_token_metadata(platform: str) -> Optional[Dict[str, Any]]:
    """
    Membaca metadata token tanpa mengekspos token plaintext (aman untuk tampilan UI).
    """
    platform = platform.lower().strip()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT platform, account_id, username, expires_at, scopes, created_at,
                   (refresh_token_enc IS NOT NULL) AS has_refresh_token
            FROM tokens WHERE platform = ?
        """, (platform,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

def delete_token(platform: str) -> bool:
    """Menghapus token platform dari database (Disconnect)."""
    platform = platform.lower().strip()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tokens WHERE platform = ?", (platform,))
        conn.commit()
        return cursor.rowcount > 0
