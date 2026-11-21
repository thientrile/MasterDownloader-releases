import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from MasterDownloader import MasterDownloader

# Link share that da resolve tu vt.tiktok.com (bot bot tham so chia se), khong goi mang
STORY_SHORT = "https://vt.tiktok.com/ZS9PhJGkqfkVu-3kKvh/"
STORY_RESOLVED = ("https://www.tiktok.com/@chang18102003/video/7710581771921935636"
                  "?_r=1&aweme_type=40&story_type=1&story_uid=6653009287621623809&utm_source=copy")
PHOTO_SHORT = "https://vt.tiktok.com/ZSsJ1rXSN/"
PHOTO_RESOLVED = "https://www.tiktok.com/@linhpntt/photo/7699806432195005748?_r=1&_t=ZS-9Bap8YURX0r"
VIDEO = "https://www.tiktok.com/@linhpntt/video/7699806432195005748"


def make_downloader(root):
    dl = object.__new__(MasterDownloader)
    dl.download_root = root
    dl.base_dir = root
    dl.history = {}
    dl.save_history = lambda: None
    dl.get_manual_cookie = lambda platform: None
    return dl


class UrlKindTest(unittest.TestCase):
    def setUp(self):
        self.dl = make_downloader(tempfile.gettempdir())

    def test_kinds(self):
        cases = {
            VIDEO: "video",
            VIDEO + "?story_type=0&aweme_type=0": "video",
            "https://www.tiktok.com/@linhpntt": "video",
            PHOTO_RESOLVED: "photo",
            STORY_RESOLVED: "story",
            "https://www.tiktok.com/@chang18102003/story/7710581771921935636": "story",
            "https://www.tiktok.com/@chang18102003/stories": "stories",
            "https://www.tiktok.com/@chang18102003/stories/": "stories",
        }
        for url, kind in cases.items():
            self.assertEqual(self.dl._tiktok_url_kind(url), kind, url)

    def test_story_link_maps_to_video(self):
        self.assertEqual(
            self.dl._tiktok_post_url("https://www.tiktok.com/@a.b/story/123?x=1"),
            "https://www.tiktok.com/@a.b/video/123?x=1",
        )
        self.assertEqual(self.dl._tiktok_post_url(PHOTO_RESOLVED), PHOTO_RESOLVED)

    def test_short_link_follows_redirect(self):
        for short, resolved, kind in ((STORY_SHORT, STORY_RESOLVED, "story"), (PHOTO_SHORT, PHOTO_RESOLVED, "photo")):
            with mock.patch("MasterDownloader.requests.get") as get:
                get.return_value.url = resolved
                url = self.dl._resolve_tiktok_short_url(short)
            get.assert_called_once()
            self.assertEqual(url, resolved)
            self.assertEqual(self.dl._tiktok_url_kind(url), kind)

    def test_full_link_is_not_fetched(self):
        with mock.patch("MasterDownloader.requests.get") as get:
            self.assertEqual(self.dl._resolve_tiktok_short_url(VIDEO), VIDEO)
        get.assert_not_called()


class GalleryDlFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dl = make_downloader(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _download(self, short, resolved, runs):
        calls = []

        def fake_run(cmd, progress_callback=None):
            calls.append(cmd)
            return runs[len(calls) - 1]

        progress = []
        with mock.patch("MasterDownloader.requests.get") as get, \
                mock.patch.object(self.dl, "_run_gallerydl", side_effect=fake_run):
            get.return_value.url = resolved
            self.dl.download_tiktok(short, progress_callback=lambda s, m: progress.append(s))
        return calls, progress

    def test_photo_short_link_saves_to_user_folder(self):
        calls, progress = self._download(PHOTO_SHORT, PHOTO_RESOLVED, [(0, ["ok"])])
        self.assertEqual(len(calls), 1)
        cmd = calls[0]
        folder = os.path.join(self.tmp.name, "linhpntt")
        self.assertEqual(cmd[cmd.index("--directory") + 1], folder)
        self.assertTrue(os.path.isdir(folder))
        self.assertTrue(cmd[cmd.index("--download-archive") + 1].startswith(folder))
        self.assertEqual(cmd[-1], PHOTO_RESOLVED)
        self.assertNotIn("extractor.tiktok.filename", " ".join(cmd))
        self.assertEqual(progress[-1], "100%")

    def test_story_short_link_uses_story_filename(self):
        calls, progress = self._download(STORY_SHORT, STORY_RESOLVED, [(0, ["ok"])])
        cmd = calls[0]
        self.assertEqual(cmd[cmd.index("--directory") + 1], os.path.join(self.tmp.name, "chang18102003"))
        self.assertIn("STORY - ", " ".join(cmd))
        self.assertEqual(cmd[-1], STORY_RESOLVED)
        self.assertEqual(progress[-1], "100%")

    def test_profile_stories_retries_403_posts_in_new_process(self):
        post = "https://www.tiktok.com/@chang18102003/video/7710581771921935636"
        fail = (f"[tiktok][error] {post}: Failed to extract post "
                f"(HttpError: '403 Forbidden' for '{post}')")
        stories = "https://www.tiktok.com/@chang18102003/stories"
        calls, progress = self._download(stories, stories, [(4, [fail, "[tiktok][info] No results for " + stories]),
                                                            (0, ["ok"])])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][-1], stories)
        self.assertEqual(calls[1][-1], post)
        self.assertEqual(progress[-1], "100%")

    def test_profile_without_stories_raises_for_gui(self):
        stories = "https://www.tiktok.com/@chang18102003/stories"
        with self.assertRaisesRegex(RuntimeError, "Không có story"):
            self._download(stories, stories, [(0, ["[tiktok][info] No results for " + stories])])

    def test_retry_still_403_is_not_reported_as_no_stories(self):
        post = "https://www.tiktok.com/@chang18102003/video/1"
        fail = f"[tiktok][error] {post}: Failed to extract post (HttpError: '403 Forbidden' for '{post}')"
        stories = "https://www.tiktok.com/@chang18102003/stories"
        no_results = "[tiktok][info] No results for " + stories
        with self.assertRaisesRegex(RuntimeError, r"chặn \(403\)"):
            self._download(stories, stories, [(4, [fail, no_results]), (4, [fail, "[tiktok][info] No results for " + post])])

    def test_other_errors_survive_successful_retry(self):
        post = "https://www.tiktok.com/@chang18102003/video/1"
        fail = f"[tiktok][error] {post}: Failed to extract post (HttpError: '403 Forbidden' for '{post}')"
        other = "[download][error] Failed to download STORY - 2.mp4"
        stories = "https://www.tiktok.com/@chang18102003/stories"
        with self.assertRaisesRegex(RuntimeError, "STORY - 2"):
            self._download(stories, stories, [(4, [fail, other]), (0, ["ok"])])


if __name__ == "__main__":
    unittest.main()
