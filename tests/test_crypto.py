import os
import sys
import unittest

from cryptography.fernet import Fernet

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from MasterDownloader import MasterDownloader


def make_downloader(key):
    dl = object.__new__(MasterDownloader)
    dl.cipher = Fernet(key)
    return dl


class DecryptTest(unittest.TestCase):
    def test_roundtrip(self):
        dl = make_downloader(Fernet.generate_key())
        self.assertEqual(dl._decrypt_text(dl._encrypt_text("user\npass")), "user\npass")

    def test_token_from_other_key_returns_empty(self):
        token = make_downloader(Fernet.generate_key())._encrypt_text("secret")
        self.assertEqual(make_downloader(Fernet.generate_key())._decrypt_text(token), "")

    def test_plain_text_passes_through(self):
        dl = make_downloader(Fernet.generate_key())
        self.assertEqual(dl._decrypt_text("legacy-plain"), "legacy-plain")


if __name__ == "__main__":
    unittest.main()
