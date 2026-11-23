import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from MasterDownloader import MasterDownloader


def make_downloader(tmpdir):
    """Tao instance khong chay __init__ nang; chi set thuoc tinh can cho dedup."""
    dl = object.__new__(MasterDownloader)
    dl.base_dir = tmpdir
    dl.deleted_md5_file = os.path.join(tmpdir, "deleted_md5.txt")
    dl._deleted_md5 = {}
    return dl


class FileHashTest(unittest.TestCase):
    def test_file_hash_returns_md5_hex(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            p = os.path.join(tmp, "a.bin")
            data = b"hello-master-downloader"
            with open(p, "wb") as f:
                f.write(data)
            digest = dl._file_hash(p)
            self.assertEqual(digest, hashlib.md5(data).hexdigest())
            self.assertEqual(len(digest), 32)

    def test_file_hash_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            self.assertIsNone(dl._file_hash(os.path.join(tmp, "nope.bin")))


class RegistryTest(unittest.TestCase):
    def test_record_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            dl._record_deleted_md5("abc123", 100)
            dl._record_deleted_md5("def456", 200)
            reloaded = dl._load_deleted_md5()
            self.assertIn("abc123", reloaded.get(100, set()))
            self.assertIn("def456", reloaded.get(200, set()))

    def test_record_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            dl._record_deleted_md5("abc123", 100)
            dl._record_deleted_md5("abc123", 100)
            with open(dl.deleted_md5_file, "r", encoding="utf-8") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            self.assertEqual(lines, ["abc123,100"])

    def test_load_ignores_malformed_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            with open(dl.deleted_md5_file, "w", encoding="utf-8") as f:
                f.write("good,123\n")
                f.write("garbage-no-comma\n")
                f.write("md5,notanumber\n")
                f.write("\n")
            loaded = dl._load_deleted_md5()
            self.assertEqual(loaded, {123: {"good"}})

    def test_load_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            self.assertEqual(dl._load_deleted_md5(), {})


class DeletePathsTest(unittest.TestCase):
    def test_delete_records_md5_and_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            p = os.path.join(tmp, "v.mp4")
            data = b"video-bytes-1234"
            with open(p, "wb") as f:
                f.write(data)
            size = os.path.getsize(p)

            deleted, freed = dl.delete_paths([p])

            self.assertEqual(deleted, 1)
            self.assertEqual(freed, size)
            self.assertFalse(os.path.exists(p))
            self.assertIn(hashlib.md5(data).hexdigest(), dl._deleted_md5.get(size, set()))
            self.assertIn(
                f"{hashlib.md5(data).hexdigest()},{size}",
                open(dl.deleted_md5_file, encoding="utf-8").read(),
            )


class FindDuplicatesTest(unittest.TestCase):
    def _write(self, path, data):
        with open(path, "wb") as f:
            f.write(data)

    def test_returns_tuple_and_groups_current_dupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            self._write(os.path.join(tmp, "a.jpg"), b"same-image-content")
            self._write(os.path.join(tmp, "b.jpg"), b"same-image-content")
            groups, resurrected = dl.find_duplicates(directory=tmp)
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]), 2)
            self.assertEqual(resurrected, [])

    def test_detects_resurrected_unique_size_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            data = b"previously-deleted-unique-clip"
            p = os.path.join(tmp, "clip.mp4")
            self._write(p, data)
            dl._record_deleted_md5(hashlib.md5(data).hexdigest(), os.path.getsize(p))
            groups, resurrected = dl.find_duplicates(directory=tmp)
            self.assertEqual(groups, [])
            self.assertEqual(resurrected, [p])

    def test_same_size_different_content_not_resurrected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            p = os.path.join(tmp, "x.png")
            self._write(p, b"AAAAAAAAAA")
            dl._record_deleted_md5("0" * 32, 10)
            groups, resurrected = dl.find_duplicates(directory=tmp)
            self.assertEqual(resurrected, [])

    def test_clean_dir_returns_empty_tuple(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            self.assertEqual(dl.find_duplicates(directory=tmp), ([], []))

    def test_resurrected_file_that_is_also_duplicate_only_in_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            data = b"redownloaded-twice-content"
            p1 = os.path.join(tmp, "one.mp4")
            p2 = os.path.join(tmp, "two.mp4")
            self._write(p1, data)
            self._write(p2, data)
            dl._record_deleted_md5(hashlib.md5(data).hexdigest(), len(data))
            groups, resurrected = dl.find_duplicates(directory=tmp)
            self.assertEqual(len(groups), 1)
            self.assertEqual(resurrected, [])


if __name__ == "__main__":
    unittest.main()
