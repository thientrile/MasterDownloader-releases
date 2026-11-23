import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import third_party_licenses as tpl


class FfmpegLicenseTest(unittest.TestCase):
    def test_config_to_license(self):
        self.assertEqual(tpl.ffmpeg_license("--enable-gpl --enable-version3"), "GPL-3.0-or-later")
        self.assertEqual(tpl.ffmpeg_license("--enable-gpl"), "GPL-2.0-or-later")
        self.assertEqual(tpl.ffmpeg_license("--enable-version3"), "LGPL-3.0-or-later")
        self.assertEqual(tpl.ffmpeg_license(""), "LGPL-2.1-or-later")
        self.assertIn("nonfree", tpl.ffmpeg_license("--enable-gpl --enable-nonfree"))


class GenerateTest(unittest.TestCase):
    def test_lists_bundled_packages_with_license_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "THIRD_PARTY_LICENSES.txt")
            tpl.main(dest)
            with open(dest, encoding="utf-8") as f:
                text = f.read()
        for name in ("Python ", "yt-dlp ", "gallery_dl ", "PyQt6 ", "requests ", "pyinstaller "):
            self.assertRegex(text, rf"(?im)^{name}", name)
        self.assertIn("GNU GENERAL PUBLIC LICENSE", text)  # van ban giay phep, khong chi ten


if __name__ == "__main__":
    unittest.main()
