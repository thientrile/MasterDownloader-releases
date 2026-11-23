# MD5 Deleted-Dedup Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ghi MD5 của file bị xoá khi quét trùng vào một sổ toàn cục để lần quét sau tự loại bỏ các file "quay lại" đã từng bị xoá.

**Architecture:** Một registry file `data_dir/archives/deleted_md5.txt` (mỗi dòng `md5,size`) nạp vào dict `size -> set(md5)` trong RAM. `delete_paths` ghi sổ trước khi xoá; `find_duplicates` đối chiếu sổ trong cùng vòng `os.walk` (lọc nhanh theo size) và trả về `(groups, resurrected)`. UI hiển thị mục resurrected để người dùng xác nhận xoá.

**Tech Stack:** Python 3, `hashlib` (MD5), `unittest`, PyQt6 (App.py).

---

## File Structure

- `MasterDownloader.py` (modify): đổi `_file_hash` sang MD5; thêm `_load_deleted_md5` + `_record_deleted_md5`; wire vào `__init__`; sửa `delete_paths` và `find_duplicates`.
- `App.py` (modify): `DuplicateWorker.run` truyền tuple; `handle_scan_result` unpack; `DuplicatesDialog` nhận `resurrected`.
- `tests/test_dedup_md5.py` (create): unit test cho hash, registry, delete_paths, find_duplicates.
- `tests/test_dedup_dialog.py` (create): test UI dialog gộp resurrected (offscreen).

Test runner: `python -m unittest <module> -v` (dự án dùng `unittest`, không có pytest).

---

### Task 1: Đổi `_file_hash` sang MD5

**Files:**
- Modify: `MasterDownloader.py:1844-1853`
- Test: `tests/test_dedup_md5.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/test_dedup_md5.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `python -m unittest tests.test_dedup_md5.FileHashTest -v`
Expected: FAIL ở `test_file_hash_returns_md5_hex` (hiện `_file_hash` trả SHA-256, dài 64).

- [ ] **Step 3: Đổi `_file_hash` sang MD5**

Trong `MasterDownloader.py`, thay thân hàm `_file_hash` (dòng 1844-1853):

```python
    def _file_hash(self, path, chunk=1 << 20):
        """MD5 toan bo noi dung file (doc theo block 1MB)."""
        h = hashlib.md5()
        try:
            with open(path, 'rb') as f:
                for block in iter(lambda: f.read(chunk), b''):
                    h.update(block)
        except OSError:
            return None
        return h.hexdigest()
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run: `python -m unittest tests.test_dedup_md5.FileHashTest -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add MasterDownloader.py tests/test_dedup_md5.py
git commit -m "feat: switch dedup content hash to MD5"
```

---

### Task 2: Registry nạp/ghi sổ MD5

**Files:**
- Modify: `MasterDownloader.py` (thêm 2 method gần `_file_hash`; wire vào `__init__` sau dòng 47)
- Test: `tests/test_dedup_md5.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_dedup_md5.py`:

```python
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
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `python -m unittest tests.test_dedup_md5.RegistryTest -v`
Expected: FAIL với `AttributeError: ... has no attribute '_record_deleted_md5'`.

- [ ] **Step 3: Thêm 2 method và wire vào `__init__`**

Trong `MasterDownloader.py`, thêm ngay TRƯỚC `def _file_hash` (dòng 1844):

```python
    def _load_deleted_md5(self):
        """Nap so MD5 cac file da xoa: tra ve dict size(int) -> set(md5 hex)."""
        registry = {}
        path = getattr(self, "deleted_md5_file", None)
        if not path or not os.path.exists(path):
            return registry
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) != 2:
                        continue
                    md5, size_str = parts[0].strip(), parts[1].strip()
                    try:
                        size = int(size_str)
                    except ValueError:
                        continue
                    if md5:
                        registry.setdefault(size, set()).add(md5)
        except OSError as e:
            print(f"{Fore.YELLOW}⚠️  Khong doc duoc so MD5 {path!r}: {e}")
        return registry

    def _record_deleted_md5(self, md5, size):
        """Ghi (md5,size) vao so neu chua co. Idempotent."""
        if not md5:
            return
        known = self._deleted_md5.setdefault(size, set())
        if md5 in known:
            return
        known.add(md5)
        try:
            with open(self.deleted_md5_file, "a", encoding="utf-8") as f:
                f.write(f"{md5},{size}\n")
        except OSError as e:
            print(f"{Fore.YELLOW}⚠️  Khong ghi duoc so MD5 {self.deleted_md5_file!r}: {e}")
```

Trong `__init__`, ngay SAU dòng 47 (`os.makedirs(self.archive_dir, exist_ok=True)`), thêm:

```python
        # So MD5 cac file da xoa vi trung, de chan tai lai (toan cuc)
        self.deleted_md5_file = os.path.join(self.archive_dir, "deleted_md5.txt")
        self._deleted_md5 = self._load_deleted_md5()
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run: `python -m unittest tests.test_dedup_md5.RegistryTest -v`
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add MasterDownloader.py tests/test_dedup_md5.py
git commit -m "feat: add deleted-MD5 registry load/record"
```

---

### Task 3: `delete_paths` ghi sổ trước khi xoá

**Files:**
- Modify: `MasterDownloader.py:1926-1944`
- Test: `tests/test_dedup_md5.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_dedup_md5.py`:

```python
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
            # Da ghi xuong file so
            self.assertIn(
                f"{hashlib.md5(data).hexdigest()},{size}",
                open(dl.deleted_md5_file, encoding="utf-8").read(),
            )
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `python -m unittest tests.test_dedup_md5.DeletePathsTest -v`
Expected: FAIL (MD5 chưa được ghi vào `_deleted_md5`).

- [ ] **Step 3: Sửa `delete_paths`**

Thay phần đầu vòng lặp trong `delete_paths` (dòng 1930-1934) để tính + ghi MD5 trước khi xoá. Hàm đầy đủ sau khi sửa:

```python
    def delete_paths(self, paths, status_callback=None):
        """Xoa danh sach file, ghi MD5 vao so de chan tai lai. Tra ve (so_file_da_xoa, tong_byte)."""
        deleted = 0
        freed = 0
        for path in paths:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            # Ghi so MD5 truoc khi xoa (file con ton tai de tinh hash)
            md5 = self._file_hash(path)
            if md5 is not None:
                self._record_deleted_md5(md5, size)
            try:
                os.remove(path)
                deleted += 1
                freed += size
                if status_callback:
                    status_callback(f"🗑️  Đã xóa: {os.path.basename(path)}")
            except Exception as e:
                if status_callback:
                    status_callback(f"❌ Lỗi xóa {os.path.basename(path)}: {e}")
        return deleted, freed
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run: `python -m unittest tests.test_dedup_md5.DeletePathsTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add MasterDownloader.py tests/test_dedup_md5.py
git commit -m "feat: record MD5 of deleted duplicates"
```

---

### Task 4: `find_duplicates` phát hiện resurrected + trả tuple

**Files:**
- Modify: `MasterDownloader.py:1855-1924`
- Test: `tests/test_dedup_md5.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_dedup_md5.py`:

```python
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
            # Gia lap: file nay tung bi xoa
            dl._record_deleted_md5(hashlib.md5(data).hexdigest(), os.path.getsize(p))
            groups, resurrected = dl.find_duplicates(directory=tmp)
            self.assertEqual(groups, [])
            self.assertEqual(resurrected, [p])

    def test_same_size_different_content_not_resurrected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            p = os.path.join(tmp, "x.png")
            self._write(p, b"AAAAAAAAAA")  # 10 bytes
            # So co size 10 nhung md5 khac
            dl._record_deleted_md5("0" * 32, 10)
            groups, resurrected = dl.find_duplicates(directory=tmp)
            self.assertEqual(resurrected, [])

    def test_clean_dir_returns_empty_tuple(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl = make_downloader(tmp)
            self.assertEqual(dl.find_duplicates(directory=tmp), ([], []))
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `python -m unittest tests.test_dedup_md5.FindDuplicatesTest -v`
Expected: FAIL — `find_duplicates` hiện trả `groups` (list), không phải tuple.

- [ ] **Step 3: Sửa `find_duplicates`**

(a) Thêm khởi tạo `resurrected` ngay sau `scanned = 0` (dòng 1876). Phần đầu hàm thành:

```python
        media_exts = self._media_extensions()

        # Buoc 1: gom theo kich thuoc (file unique size khong the trung)
        size_map = {}
        resurrected = []
        scanned = 0
```

(b) Trong vòng `os.walk`, ngay sau `size_map.setdefault(size, []).append(path)` (dòng 1891), thêm phát hiện resurrected:

```python
                size_map.setdefault(size, []).append(path)
                # File "quay lai": size co trong so -> tinh MD5 -> doi chieu
                if size in self._deleted_md5:
                    fh = self._file_hash(path)
                    if fh is not None and fh in self._deleted_md5[size]:
                        resurrected.append(path)
```

(c) Thay đoạn kết hàm (dòng 1919-1924) để loại path đã nằm trong groups và trả tuple:

```python
        total_dupes = sum(len(g) - 1 for g in groups)
        # Tranh liet ke trung: bo resurrected da xuat hien trong groups
        in_groups = {p for g in groups for p in g}
        resurrected = [p for p in resurrected if p not in in_groups]
        if total_dupes == 0 and not resurrected:
            log(f"{Fore.GREEN}✨ Không tìm thấy file trùng nào.")
        else:
            log(f"{Fore.GREEN}✅ Tìm thấy {len(groups)} nhóm, {total_dupes} bản sao "
                f"+ {len(resurrected)} file đã từng xoá.")
        return groups, resurrected
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run: `python -m unittest tests.test_dedup_md5 -v`
Expected: PASS toàn bộ (Task 1-4).

- [ ] **Step 5: Commit**

```bash
git add MasterDownloader.py tests/test_dedup_md5.py
git commit -m "feat: detect resurrected deleted files in find_duplicates"
```

---

### Task 5: App.py — worker, handler, dialog hiển thị resurrected

**Files:**
- Modify: `App.py:321-325` (worker), `App.py:1343-1366` (handler), `App.py:347-446` (dialog)
- Test: `tests/test_dedup_dialog.py`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/test_dedup_dialog.py`:

```python
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PyQt6.QtWidgets import QApplication
    import App
    _HAVE_QT = True
except Exception:
    _HAVE_QT = False


@unittest.skipUnless(_HAVE_QT, "PyQt6 khong san co")
class DialogResurrectedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_resurrected_files_are_selectable(self):
        groups = [["/keep/a.jpg", "/dup/a.jpg"]]
        resurrected = ["/old/clip.mp4"]
        dlg = App.DuplicatesDialog(groups, resurrected=resurrected)
        selected = dlg.selected_paths()
        # Ban sao trong nhom + file resurrected deu duoc tick san
        self.assertIn("/dup/a.jpg", selected)
        self.assertIn("/old/clip.mp4", selected)
        self.assertNotIn("/keep/a.jpg", selected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_dedup_dialog -v`
Expected: FAIL — `DuplicatesDialog.__init__` chưa nhận kwarg `resurrected`.

- [ ] **Step 3a: Sửa `DuplicateWorker.run` (App.py:321-325)**

Đổi để truyền nguyên tuple ra signal:

```python
            groups, resurrected = self.downloader.find_duplicates(
                directory=self.directory,
                status_callback=callback
            )
            self.signals.result.emit((groups, resurrected))
```

- [ ] **Step 3b: Sửa `handle_scan_result` (App.py:1343-1366)**

```python
    def handle_scan_result(self, result):
        groups, resurrected = result
        if not groups and not resurrected:
            self.log("Quét xong. Không tìm thấy file trùng.", "SUCCESS")
            QMessageBox.information(self, "Hoàn tất", "Không tìm thấy file trùng nào.")
            return

        dlg = DuplicatesDialog(groups, self, resurrected=resurrected)
        if not dlg.exec():
            self.log("Đã hủy xóa file trùng.", "INFO")
            return

        paths = dlg.selected_paths()
        if not paths:
            self.log("Không có mục nào được chọn để xóa.", "INFO")
            return

        deleted, freed = self.downloader.delete_paths(
            paths, status_callback=lambda m: self.log(m, "INFO")
        )
        self.log(f"Đã xóa {deleted} file trùng, giải phóng {human_size(freed)}.", "SUCCESS")
        QMessageBox.information(
            self, "Hoàn tất",
            f"Đã xóa {deleted} file trùng.\nGiải phóng {human_size(freed)}."
        )
```

- [ ] **Step 3c: Sửa `DuplicatesDialog.__init__` (App.py:349)**

Đổi chữ ký và lưu `resurrected`. Dòng `def __init__(self, groups, parent=None):` thành:

```python
    def __init__(self, groups, parent=None, resurrected=None):
        super().__init__(parent)
        self.groups = groups
        self.resurrected = resurrected or []
```

(Giữ nguyên các dòng còn lại của `__init__`.)

- [ ] **Step 3d: Hiển thị mục resurrected trong `_populate` (App.py:409-424)**

Thêm vào CUỐI method `_populate`, sau vòng `for i, group ...`:

```python
        if self.resurrected:
            top = QTreeWidgetItem(
                self.tree,
                [f"🔁 Đã từng xoá trước đây — {len(self.resurrected)} file", "", ""],
            )
            top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            top.setExpanded(True)
            for p in self.resurrected:
                child = QTreeWidgetItem(top, [p, human_size(self._size(p)), self._mtime(p)])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Checked)
                child.setData(0, Qt.ItemDataRole.UserRole, p)
```

(`selected_paths` đã duyệt mọi top-level item nên tự gộp các mục này — không cần sửa.)

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_dedup_dialog -v`
Expected: PASS (hoặc SKIP nếu môi trường không có PyQt6).

- [ ] **Step 5: Commit**

```bash
git add App.py tests/test_dedup_dialog.py
git commit -m "feat: show resurrected deleted files in duplicates dialog"
```

---

### Task 6: Chạy toàn bộ test + kiểm tra hồi quy

- [ ] **Step 1: Chạy toàn bộ test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`
Expected: tất cả PASS (test_requirements, test_dedup_md5, test_dedup_dialog).

- [ ] **Step 2: Smoke import App**

Run: `QT_QPA_PLATFORM=offscreen python -c "import App; print('ok')"`
Expected: in `ok`, không lỗi import.

- [ ] **Step 3: Commit (nếu có chỉnh sửa nhỏ)**

```bash
git add -A
git commit -m "test: verify md5 deleted-dedup end to end" || echo "nothing to commit"
```
