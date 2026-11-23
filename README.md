# MasterDownloader

App desktop (PyQt6) tải video/ảnh từ TikTok, Instagram, Facebook, kèm quét và xoá file trùng (MD5).

## Tải bản Windows

Vào [Releases](https://github.com/thientrile/MasterDownloader-releases/releases/latest) (repo public chỉ chứa bản phát hành):

- **`MasterDownloader-Setup.exe`** (khuyên dùng): bộ cài theo người dùng, không cần quyền admin. Cài vào `%LOCALAPPDATA%\Programs\MasterDownloader`, có shortcut Start Menu (tuỳ chọn Desktop) và gỡ cài đặt trong **Settings → Apps**. Gỡ cài đặt không xoá dữ liệu ở `%APPDATA%\MasterDownloader`.
- `MasterDownloader.exe`: bản portable, chạy trực tiếp không cần cài.

File exe chưa ký số nên lần đầu chạy Windows SmartScreen sẽ cảnh báo: bấm **More info → Run anyway**.

Kiểm tra checksum (tuỳ chọn):

```powershell
Get-FileHash MasterDownloader-Setup.exe -Algorithm SHA256   # so với SHA256SUMS.txt
```

Dữ liệu (lịch sử, session, tài khoản IG đã mã hoá, `secret.key`) nằm ở `%APPDATA%\MasterDownloader`; dữ liệu cũ cạnh file exe được chuyển sang tự động ở lần chạy đầu. `secret.key` được tạo riêng trên từng máy, không có trong repo và không có trong bản release.

## Tự cập nhật

Bản exe kiểm tra GitHub Release mới khi mở app (tối đa 1 lần/ngày) hoặc khi bấm **Cài đặt → Kiểm tra cập nhật**. App hỏi trước khi cài (Cập nhật ngay / Để sau / Bỏ qua bản này), không cài khi đang có lượt tải, kiểm SHA256 theo `SHA256SUMS.txt` rồi tự khởi động lại. Bản cài đặt tải `MasterDownloader-Setup.exe` mới và cài im lặng; bản portable thay file exe tại chỗ.

## Chạy từ source

```bash
./StartApp.sh        # Linux/WSL, tự tạo .venv
StartApp.bat         # Windows
```

Test: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests`

## Build và phát hành

- `build.bat` build `dist\MasterDownloader.exe` (PyInstaller onefile), giống hệt CI.
- Mỗi push/PR: GitHub Actions chạy test và build exe trên Windows (artifact `MasterDownloader-windows`).
- Push tag `vX.Y.Z` tạo GitHub Release đính kèm `MasterDownloader.exe` và `SHA256SUMS.txt`:

```bash
git tag v1.0.0 && git push origin v1.0.0
```
