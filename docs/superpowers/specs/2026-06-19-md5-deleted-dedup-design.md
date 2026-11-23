# Thiết kế: Sổ MD5 chặn tải lại file đã xoá trùng

**Ngày:** 2026-06-19
**Trạng thái:** Đã duyệt thiết kế, chờ viết plan

## Vấn đề

Ứng dụng đã có chức năng quét file trùng theo nội dung (`find_duplicates`, hiện dùng
SHA-256) và xoá bản sao (`delete_paths`). Nhưng khi một file bị xoá vì trùng, không có
gì ghi nhớ điều đó: các archive tải về (`download-archive` của yt-dlp/gallery-dl) chỉ
chặn theo URL/post-id, nên cùng một nội dung tải lại từ URL khác (repost TikTok ↔
Instagram, story ↔ post) sẽ quay lại đĩa.

Yêu cầu người dùng: file đã bị xoá vì trùng thì **không được tải lại nữa**, dùng **MD5**
của nội dung file làm id để tránh trùng.

## Quyết định đã chốt (qua brainstorming)

1. **Khi nào ghi sổ:** chỉ ghi MD5 khi chạy quét trùng (lúc xoá bản sao). Không ghi MD5
   cho mọi file tải thành công.
2. **Phạm vi sổ:** toàn cục — một sổ duy nhất cho mọi nền tảng/user, để bắt được trùng
   xuyên nền tảng.
3. **Thời điểm chặn:** ở lần quét trùng kế tiếp (không can thiệp vào luồng tải). File
   "quay lại" sẽ bị dọn khi người dùng chạy quét lần sau.
4. **Hàm băm:** đổi hẳn nội dung dedup từ SHA-256 sang MD5 cho nhất quán với id sổ.

## Kiến trúc

### Registry (sổ MD5)
- File toàn cục: `data_dir/archives/deleted_md5.txt`.
- Mỗi dòng: `<md5_hex>,<size_bytes>`.
- Nạp khi khởi tạo `MasterDownloader` thành cấu trúc trong RAM:
  `self._deleted_md5: dict[int, set[str]]` ánh xạ `size -> {md5, ...}`.
- Lý do kèm `size`: dùng làm bộ lọc nhanh. Khi quét, chỉ file có size nằm trong sổ mới
  phải tính MD5; file unique-size bỏ qua, giữ nguyên đường nhanh hiện tại.

### Hàm băm nội dung
- `_file_hash(path)`: đổi từ `hashlib.sha256()` sang `hashlib.md5()`. Trả về MD5 hex
  (32 ký tự). Đây là id chuẩn dùng cho cả gom nhóm trùng lẫn ghi sổ.
- `_quick_signature(path)` (blake2b 64KB): **giữ nguyên** — chỉ là bước lọc sơ bộ trong
  cùng nhóm size, không phải id lưu trữ.

## Luồng dữ liệu

### Ghi sổ — `delete_paths(paths, status_callback)`
Trước khi `os.remove(path)` mỗi file:
1. Tính `md5 = self._file_hash(path)` và `size = os.path.getsize(path)` (file vẫn tồn tại).
2. Nếu thành công, append dòng `md5,size` vào registry qua helper `_record_deleted_md5`.
3. Helper cập nhật set trong RAM trước; chỉ ghi xuống file khi `(size, md5)` chưa có
   (idempotent — không append trùng).
4. Sau đó mới xoá file như cũ.

Đây là nơi duy nhất ghi sổ. `delete_paths` chỉ được gọi từ luồng quét trùng (App.py
`handle_scan_result`).

### Chặn — `find_duplicates(directory, status_callback)`
- Trong cùng vòng `os.walk` đang gom `size_map`, thêm kiểm tra cho mỗi file media:
  nếu `size in self._deleted_md5` thì tính MD5; nếu MD5 nằm trong
  `self._deleted_md5[size]` thì thêm path vào danh sách `resurrected`.
- Phần gom nhóm trùng hiện-có giữ nguyên thuật toán (size → quick sig → MD5 đầy đủ),
  chỉ là `_file_hash` nay trả MD5.
- Trả về `(groups, resurrected)` thay vì chỉ `groups`.
  - `groups`: list các nhóm trùng hiện có; `group[0]` là bản giữ lại (cũ nhất), `group[1:]`
    là bản sao có thể xoá. (Không đổi cấu trúc.)
  - `resurrected`: list path đơn lẻ, mỗi file có MD5 đã từng bị xoá trước đó.

### UI — `App.py`
- `find_duplicates` trả tuple → `DuplicateWorker.run` và `handle_scan_result` cập nhật để
  nhận `(groups, resurrected)`.
- Điều kiện "không có gì": chỉ khi cả `groups` và `resurrected` đều rỗng mới báo
  "Không tìm thấy file trùng".
- `DuplicatesDialog` nhận thêm tham số `resurrected` (mặc định `None`). Nếu có, render
  một mục riêng **"Đã từng xoá trước đây (tải lại)"**: liệt kê từng file, tick sẵn,
  **không có bản giữ lại** (tất cả đều xoá được). `selected_paths()` gộp các mục này.
- Sau xác nhận, `delete_paths` xoá và ghi lại sổ (md5,size đã có nên idempotent).

## Xử lý lỗi & biên

- Registry không đọc được / hỏng dòng: log cảnh báo, coi sổ rỗng, không chặn luồng. Bỏ
  qua dòng không đúng định dạng `md5,size`.
- Registry không ghi được (OSError): log cảnh báo, vẫn xoá file bình thường (chỉ là không
  ghi nhớ được lần này).
- `_file_hash` lỗi (OSError) khi quét hoặc khi xoá: trả `None`, bỏ qua file đó (không ghi
  sổ, không xếp resurrected).
- Idempotent: cùng `(size, md5)` không bao giờ append lần hai.

## Test (`tests/`)

1. **Registry**
   - Append rồi nạp lại → set khớp.
   - Append trùng `(size, md5)` hai lần → file chỉ một dòng.
   - File hỏng / dòng sai định dạng → nạp ra sổ rỗng/bỏ qua dòng lỗi, không raise.
2. **Hàm băm**
   - `_file_hash` trả chuỗi hex dài 32 (MD5), khớp `hashlib.md5` của cùng nội dung.
3. **delete_paths**
   - Xoá 2 file → cả hai md5,size được ghi vào registry; file bị xoá khỏi đĩa.
4. **find_duplicates**
   - (a) Hai file cùng nội dung → một nhóm trong `groups`.
   - (b) File unique-size có MD5 nằm trong sổ → xuất hiện trong `resurrected`.
   - (c) File có size trùng sổ nhưng MD5 khác → KHÔNG vào `resurrected`.
   - (d) Thư mục sạch, sổ rỗng → `([], [])`.

## Phạm vi

Chỉ động vào `MasterDownloader.py` (registry, `_file_hash`, `delete_paths`,
`find_duplicates`, init) và `App.py` (worker + dialog + handler). Không đổi luồng tải,
không đổi archive theo URL hiện có. Không refactor ngoài phạm vi.
