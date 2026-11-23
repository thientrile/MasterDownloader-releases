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


class DepCheckTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(dep_check.parse_versions(dep_check.format_versions(LATEST)), LATEST)

    def test_needs_build(self):
        same = dep_check.format_versions(LATEST)
        self.assertFalse(dep_check.needs_build(LATEST, same))
        self.assertTrue(dep_check.needs_build(LATEST, same.replace("1.30.0", "1.29.9")))
        self.assertTrue(dep_check.needs_build(LATEST, "yt-dlp==2026.11.20\n"))  # thieu goi
        self.assertTrue(dep_check.needs_build(LATEST, None))  # Release cu khong co versions.txt

    def test_next_patch(self):
        self.assertEqual(dep_check.next_patch("v1.0.9"), "v1.0.10")
        for bad in ("1.0.2", "v1.0", "v1.0.2-rc1"):
            with self.assertRaises(ValueError):
                dep_check.next_patch(bad)

    def _check(self, released):
        argv = ["--check", "--tag", "v1.0.2"]
        with tempfile.TemporaryDirectory() as tmp:
            if released is not None:
                path = os.path.join(tmp, "versions.txt")
                with open(path, "w") as f:
                    f.write(released)
                argv += ["--released", path]
            out = io.StringIO()
            with mock.patch("dep_check.pypi_latest", LATEST.get), redirect_stdout(out):
                dep_check.main(argv)
        return out.getvalue()

    def test_main_output(self):
        self.assertEqual(self._check(dep_check.format_versions(LATEST)), "tag=\n")
        self.assertEqual(self._check("yt-dlp==2026.1.1\ngallery-dl==1.30.0\n"), "tag=v1.0.3\n")
        self.assertEqual(self._check(None), "tag=v1.0.3\n")


if __name__ == "__main__":
    unittest.main()
