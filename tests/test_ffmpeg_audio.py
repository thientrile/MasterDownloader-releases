import os
import sys
import unittest
from unittest import mock

import yt_dlp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from MasterDownloader import MasterDownloader

FFMPEG = r"C:\app\_MEI1\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v9.0.2.exe"

# Kieu DASH cua Facebook/Instagram: video va audio tach rieng, kem 1 ban progressive co tieng
DASH_FORMATS = [
    {"format_id": "sd", "url": "http://x/sd", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 360, "tbr": 500},
    {"format_id": "v1080", "url": "http://x/v", "ext": "mp4", "vcodec": "h264", "acodec": "none", "height": 1080, "tbr": 3000},
    {"format_id": "a128", "url": "http://x/a", "ext": "m4a", "vcodec": "none", "acodec": "aac", "tbr": 128},
]


def make_downloader():
    dl = object.__new__(MasterDownloader)
    dl._get_ffmpeg_exe = lambda: FFMPEG
    return dl


class FormatTest(unittest.TestCase):
    def _select(self, formats):
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            selector = ydl.build_format_selector(make_downloader()._video_format())
            return list(selector({"formats": formats, "has_merged_format": False}))[0]

    def test_dash_picks_video_plus_audio(self):
        chosen = self._select(DASH_FORMATS)
        self.assertEqual(chosen["format_id"], "v1080+a128")

    def test_combined_only_keeps_audio(self):
        chosen = self._select([DASH_FORMATS[0]])
        self.assertEqual(chosen["acodec"], "aac")


class FfmpegLocationTest(unittest.TestCase):
    def test_in_process_yt_dlp_gets_ffmpeg(self):
        dl = make_downloader()
        dl._rate_limit_ydl_opts = lambda: {}
        with mock.patch("MasterDownloader.yt_dlp.YoutubeDL") as ydl:
            dl._prepare_yt_dlp({"format": dl._video_format()}, "test")
        self.assertEqual(ydl.call_args[0][0]["ffmpeg_location"], FFMPEG)

    def test_gallerydl_subprocess_gets_ffmpeg(self):
        cmd = make_downloader()._gallerydl_cmd()
        for scope in ("downloader", "extractor"):
            self.assertIn(f"{scope}.ytdl.raw-options.ffmpeg_location={FFMPEG}", cmd)

    def test_frozen_exe_calls_itself(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            cmd = make_downloader()._gallerydl_cmd()
        self.assertEqual(cmd[:2], [sys.executable, "--gallery-dl"])

    def test_no_ffmpeg_no_option(self):
        dl = make_downloader()
        dl._get_ffmpeg_exe = lambda: None
        self.assertNotIn("-o", dl._gallerydl_cmd())


if __name__ == "__main__":
    unittest.main()
