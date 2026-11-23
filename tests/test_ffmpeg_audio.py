import os
import sys
import tempfile
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


class AudioOnlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dl = make_downloader()
        self.dl._rate_limit_ydl_opts = lambda: {}

    def tearDown(self):
        self.tmp.cleanup()

    def _opts(self, audio_only):
        self.dl.audio_only = audio_only
        archive = os.path.join(self.tmp.name, "a.txt")
        base = {"format": self.dl._video_format(), "download_archive": archive, "writethumbnails": True,
                "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg"}]}
        with mock.patch("MasterDownloader.yt_dlp.YoutubeDL") as ydl:
            self.dl._prepare_yt_dlp(base, "test")
        return ydl.call_args[0][0], archive

    def test_off_keeps_video_options(self):
        opts, archive = self._opts(False)
        self.assertEqual(opts["format"], self.dl._video_format())
        self.assertEqual(opts["download_archive"], archive)
        self.assertTrue(opts["writethumbnails"])

    def test_on_extracts_mp3_with_app_ffmpeg_and_own_archive(self):
        opts, archive = self._opts(True)
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            def pick(formats):
                # incomplete_formats tinh nhu yt-dlp: chi toan audio hoac toan video
                incomplete = all(f["vcodec"] == "none" for f in formats) or all(f["acodec"] == "none" for f in formats)
                ctx = {"formats": formats, "has_merged_format": False, "incomplete_formats": incomplete}
                return list(ydl.build_format_selector(opts["format"])(ctx))[0]["format_id"]

            music = {"format_id": "audio", "url": "http://x/m", "ext": "mp3", "vcodec": "none", "acodec": "mp3"}
            play = {"format_id": "h264_540p", "url": "http://x/p", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 1024}
            self.assertEqual(pick([music, play]), "h264_540p")  # TikTok video: tieng cua video, khong phai nhac nen
            self.assertEqual(pick([music]), "audio")  # TikTok bai anh: chi co nhac nen
            self.assertEqual(pick(DASH_FORMATS), "a128")  # Facebook/IG DASH: luong audio
        self.assertEqual(opts["postprocessors"], [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}])
        self.assertEqual(opts["ffmpeg_location"], FFMPEG)
        self.assertFalse(opts["writethumbnails"])
        self.assertEqual(opts["download_archive"], os.path.join(self.tmp.name, "a_mp3.txt"))

    def test_gallerydl_filter_drops_images_only_in_audio_mode(self):
        self.assertNotIn("--filter", self.dl._gallerydl_cmd())
        self.dl.audio_only = True
        cmd = self.dl._gallerydl_cmd()
        expr = cmd[cmd.index("--filter") + 1]
        for ext, keep in (("mp4", True), ("mp3", True), ("m4a", True), ("jpg", False), ("webp", False)):
            self.assertEqual(eval(expr, {"extension": ext}), keep, ext)

    def _convert(self, returncode):
        video = os.path.join(self.tmp.name, "clip.mp4")
        old = os.path.join(self.tmp.name, "old.mp4")
        for path in (video, old):
            open(path, "wb").close()
        with mock.patch("MasterDownloader.subprocess.run") as run:
            run.return_value.returncode = returncode
            run.return_value.stderr = "boom"
            errors = self.dl._convert_videos_to_mp3([video, "# " + old, "[tiktok][info] x"])
        return run, video, old, errors

    def test_new_video_converted_then_removed(self):
        run, video, old, errors = self._convert(0)
        run.assert_called_once()
        args = run.call_args[0][0]
        self.assertEqual((args[0], args[args.index("-i") + 1], args[-1]), (FFMPEG, video, video[:-4] + ".mp3"))
        self.assertEqual(errors, [])
        self.assertFalse(os.path.exists(video))
        self.assertTrue(os.path.exists(old))

    def test_failed_conversion_keeps_video_and_reports(self):
        run, video, old, errors = self._convert(1)
        self.assertTrue(os.path.exists(video))
        self.assertEqual(len(errors), 1)
        self.assertIn("boom", errors[0])

    def test_run_gallerydl_fails_when_conversion_fails(self):
        self.dl.audio_only = True
        self.dl.base_dir = self.tmp.name
        self.dl._convert_videos_to_mp3 = lambda lines: ["[mp3][error] x"]
        code, lines = self.dl._run_gallerydl([sys.executable, "-c", "print('hi')"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], "[mp3][error] x")


if __name__ == "__main__":
    unittest.main()
