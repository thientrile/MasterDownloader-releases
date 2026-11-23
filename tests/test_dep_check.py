import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import dep_check

LATEST = {"yt-dlp": "2026.11.20", "gallery-dl": "1.30.0"}
LOCK = "certifi==2026.1.1\ngallery-dl==1.30.0\npyqt6==6.9.0\nyt-dlp==2026.11.20\n"


class DepCheckTest(unittest.TestCase):
    def test_round_trip_normalizes_names(self):
        text = dep_check.format_versions({"gallery_dl": "1.30.0", "PyQt6": "6.9.0", "yt-dlp": "2026.11.20", "certifi": "2026.1.1"})
        self.assertEqual(text, LOCK)
        self.assertEqual(dep_check.parse_versions(text)["gallery-dl"], "1.30.0")

    def test_write_is_full_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "versions.txt")
            dep_check.main(["--write", path])
            with open(path) as f:
                lock = dep_check.parse_versions(f.read())
        # moi goi trong moi truong, khong chi yt-dlp/gallery-dl, de ban va sau ghim duoc
        self.assertIn("requests", lock)
        for p in dep_check.PACKAGES:
            self.assertIn(p, lock)

    def test_needs_build(self):
        self.assertFalse(dep_check.needs_build(LATEST, LOCK))
        self.assertTrue(dep_check.needs_build(LATEST, LOCK.replace("1.30.0", "1.29.9")))
        self.assertTrue(dep_check.needs_build(LATEST, "yt-dlp==2026.11.20\n"))  # thieu goi

    def test_next_patch(self):
        self.assertEqual(dep_check.next_patch("v1.0.9"), "v1.0.10")
        for bad in ("1.0.2", "v1.0", "v1.0.2-rc1"):
            with self.assertRaises(ValueError):
                dep_check.next_patch(bad)

    def _check(self, released):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "versions.txt")
            with open(path, "w") as f:
                f.write(released)
            out = io.StringIO()
            with mock.patch("dep_check.pypi_latest", LATEST.get), redirect_stdout(out):
                dep_check.main(["--check", "--tag", "v1.0.2", "--released", path])
        return out.getvalue()

    def test_main_output(self):
        self.assertEqual(self._check(LOCK), "tag=\n")
        self.assertEqual(self._check(LOCK.replace("2026.11.20", "2026.1.1")),
                         "tag=v1.0.3\npins=yt-dlp==2026.11.20 gallery-dl==1.30.0\n")

    def test_check_requires_released_lock(self):
        # Release chua co versions.txt thi khong tu phat hanh
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            dep_check.main(["--check", "--tag", "v1.0.2"])


if __name__ == "__main__":
    unittest.main()
