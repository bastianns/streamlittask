import os
import sys
import time
import unittest
import py_compile
import hmac
import hashlib

# Tambahkan direktori root ke sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src import config, storage



class TestCore(unittest.TestCase):
    """
    Kumpulan pengujian inti unit test untuk:
    (a) verify_signed_state: valid, kedaluwarsa, tanda tangan salah
    (b) roundtrip encrypt/decrypt token
    (c) py_compile semua file sumber proyek
    """

    # =========================================================================
    # (a) PENGUJIAN verify_signed_state
    # =========================================================================
    def test_verify_signed_state_valid(self):
        """Memastikan state yang dibuat secara sah diverifikasi sebagai valid."""
        test_platform = "instagram"
        signed_state = config.generate_signed_state(test_platform)
        
        is_valid, platform, err = config.verify_signed_state(signed_state)
        self.assertTrue(is_valid, f"State valid seharusnya berhasil diverifikasi, tetapi gagal: {err}")
        self.assertEqual(platform, test_platform)
        self.assertIsNone(err)

    def test_verify_signed_state_expired(self):
        """Memastikan state yang melebihi batas waktu (kedaluwarsa > 10 menit) ditolak."""
        test_platform = "tiktok"
        # Buat payload dengan timestamp 15 menit yang lalu (900 detik lalu)
        expired_ts = int(time.time()) - 900
        nonce = "abc12345"
        payload = f"{test_platform}:{expired_ts}:{nonce}"
        sig = hmac.new(
            config.STATE_SIGNING_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        expired_state = f"{payload}:{sig}"

        is_valid, platform, err = config.verify_signed_state(expired_state, max_age_seconds=600)
        self.assertFalse(is_valid, "State kedaluwarsa harus ditolak")
        self.assertEqual(platform, test_platform)
        self.assertIsNotNone(err)
        self.assertIn("kedaluwarsa", err.lower())

    def test_verify_signed_state_invalid_signature(self):
        """Memastikan state dengan tanda tangan yang dipalsukan/dimanipulasi ditolak."""
        test_platform = "instagram"
        signed_state = config.generate_signed_state(test_platform)
        parts = signed_state.split(":")
        
        # Manipulasi karakter tanda tangan HMAC
        bad_sig = ("0" if parts[3][0] != "0" else "1") + parts[3][1:]
        tampered_state = f"{parts[0]}:{parts[1]}:{parts[2]}:{bad_sig}"

        is_valid, platform, err = config.verify_signed_state(tampered_state)
        self.assertFalse(is_valid, "State dengan tanda tangan palsu harus ditolak")
        self.assertEqual(platform, test_platform)
        self.assertIsNotNone(err)
        self.assertIn("tidak cocok", err.lower())

    # =========================================================================
    # (b) PENGUJIAN ROUNDTRIP ENCRYPT / DECRYPT TOKEN
    # =========================================================================
    def test_roundtrip_encrypt_decrypt_token(self):
        """Memastikan token dapat dienkripsi dan didekripsi kembali ke nilai aslinya."""
        sample_token = "IGQVJydnJtNXAzcDFKWWxZa3lqSTN4WV9TZA19VbEZAGb1ZA..."
        
        # Enkripsi
        encrypted = storage.encrypt_token(sample_token)
        self.assertIsInstance(encrypted, str)
        self.assertNotEqual(encrypted, sample_token, "Token terenkripsi tidak boleh sama dengan plaintext")

        # Dekripsi
        decrypted = storage.decrypt_token(encrypted)
        self.assertEqual(decrypted, sample_token, "Hasil dekripsi harus identik dengan token plaintext asli")

    def test_roundtrip_empty_token(self):
        """Memastikan penanganan string token kosong aman."""
        self.assertEqual(storage.encrypt_token(""), "")
        self.assertEqual(storage.decrypt_token(""), "")

    # =========================================================================
    # (c) PENGUJIAN py_compile SEMUA FILE
    # =========================================================================
    def test_py_compile_all_files(self):
        """Memastikan seluruh file sumber python proyek bebas dari kesalahan sintaksis."""
        files_to_compile = [
            "app.py",
            os.path.join("src", "__init__.py"),
            os.path.join("src", "config.py"),
            os.path.join("src", "storage.py"),
            os.path.join("src", "token_manager.py"),
            os.path.join("src", "fetcher.py"),
            os.path.join("src", "cookie_manager.py"),
            os.path.join("src", "instagram_cookie_manager.py"),
            os.path.join("tests", "__init__.py"),
            os.path.join("tests", "test_core.py")
        ]

        
        for rel_path in files_to_compile:
            full_path = os.path.join(BASE_DIR, rel_path)
            self.assertTrue(os.path.exists(full_path), f"File {rel_path} tidak ditemukan")
            try:
                py_compile.compile(full_path, doraise=True)
            except py_compile.PyCompileError as e:
                self.fail(f"Gagal mengompilasi {rel_path}: {e}")


if __name__ == "__main__":
    unittest.main()
