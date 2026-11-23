import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import updater


class FakeResp:
    def __init__(self, body=b"", json_data=None):
        self.body, self._json, self.text = body, json_data, body.decode("utf-8", "replace")

    def raise_for_status(self):
        pass

    def json(self):
        return self._json

    def iter_content(self, n):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


RELEASE = {
    "tag_name": "v1.2.0",
    "assets": [
        {"name": "MasterDownloader.exe", "browser_download_url": "https://x/exe"},
        {"name": "SHA256SUMS.txt", "browser_download_url": "https://x/sums"},
    ],
}


class SourceRepoTest(unittest.TestCase):
    def test_latest_url_points_at_releases_repo(self):
        self.assertEqual(updater.LATEST_URL,
                         f"https://api.github.com/repos/{updater.RELEASES_REPO}/releases/latest")


class VersionTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v1.10.0"), (1, 10, 0))
        self.assertGreater(updater.parse_version("v1.10.0"), updater.parse_version("1.9.9"))
        self.assertEqual(updater.parse_version("0.0.0-dev"), (0,))

    def test_check_latest_newer(self):
        with mock.patch("updater.requests.get", return_value=FakeResp(json_data=RELEASE)):
            self.assertEqual(updater.check_latest("1.1.0"), ("v1.2.0", "https://x/exe", "https://x/sums"))

    def test_check_latest_same_or_older(self):
        with mock.patch("updater.requests.get", return_value=FakeResp(json_data=RELEASE)):
            self.assertIsNone(updater.check_latest("1.2.0"))
            self.assertIsNone(updater.check_latest("2.0.0"))

    def test_check_latest_missing_assets(self):
        data = dict(RELEASE, assets=[RELEASE["assets"][0]])
        with mock.patch("updater.requests.get", return_value=FakeResp(json_data=data)):
            self.assertIsNone(updater.check_latest("1.0.0"))


class DownloadTest(unittest.TestCase):
    def _get(self, exe, sums):
        return lambda url, **kw: FakeResp(exe if url.endswith("exe") else sums)

    def test_checksum_ok(self):
        exe = b"new-exe-bytes"
        sums = f"{hashlib.sha256(exe).hexdigest()}  MasterDownloader.exe\n".encode()
        with tempfile.TemporaryDirectory() as tmp, mock.patch("updater.requests.get", self._get(exe, sums)):
            dest = os.path.join(tmp, "x.new")
            updater.download_verified("https://x/exe", "https://x/sums", dest)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), exe)

    def test_checksum_mismatch_deletes_file(self):
        sums = f"{'0' * 64}  MasterDownloader.exe\n".encode()
        with tempfile.TemporaryDirectory() as tmp, mock.patch("updater.requests.get", self._get(b"evil", sums)):
            dest = os.path.join(tmp, "x.new")
            with self.assertRaises(ValueError):
                updater.download_verified("https://x/exe", "https://x/sums", dest)
            self.assertFalse(os.path.exists(dest))


class SwapTest(unittest.TestCase):
    def test_swap_then_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            cur, new = os.path.join(tmp, "app.exe"), os.path.join(tmp, "app.exe.new")
            for p, body in ((cur, b"old"), (new, b"new")):
                with open(p, "wb") as f:
                    f.write(body)
            old = updater.swap_exe(new, cur)
            with open(cur, "rb") as f:
                self.assertEqual(f.read(), b"new")
            with open(old, "rb") as f:
                self.assertEqual(f.read(), b"old")
            updater.cleanup_old(cur)
            self.assertFalse(os.path.exists(old))


class RelaunchTest(unittest.TestCase):
    def test_relaunch_resets_pyinstaller_environment(self):
        with mock.patch("updater.subprocess.Popen") as popen:
            updater.relaunch(r"C:\\app\\MasterDownloader.exe")
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [r"C:\\app\\MasterDownloader.exe"])
        self.assertEqual(kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertIn("PATH", kwargs["env"])  # giu nguyen moi truong con lai


class AppDataDirTest(unittest.TestCase):
    def test_source_run_keeps_base_dir(self):
        from MasterDownloader import app_data_dir
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(app_data_dir(tmp), tmp)

    def test_frozen_windows_migrates_once(self):
        from MasterDownloader import app_data_dir
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as appdata, \
                mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"APPDATA": appdata}):
            with open(os.path.join(base, "secret.key"), "w") as f:
                f.write("k")
            os.makedirs(os.path.join(base, "sessions"))
            target = app_data_dir(base)
            self.assertEqual(target, os.path.join(appdata, "MasterDownloader"))
            self.assertTrue(os.path.exists(os.path.join(target, "secret.key")))
            self.assertTrue(os.path.isdir(os.path.join(target, "sessions")))
            self.assertFalse(os.path.exists(os.path.join(base, "secret.key")))
            # Da co ban o APPDATA thi khong ghi de
            with open(os.path.join(base, "secret.key"), "w") as f:
                f.write("other")
            app_data_dir(base)
            with open(os.path.join(target, "secret.key")) as f:
                self.assertEqual(f.read(), "k")


if __name__ == "__main__":
    unittest.main()
