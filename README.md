# MasterDownloader

App desktop (PyQt6) tải video/ảnh từ TikTok, Instagram, Facebook, kèm quét và xoá file trùng (MD5).

Đây là repo mã nguồn và bản phát hành của MasterDownloader. Giấy phép: **GPL-3.0**.
This is the source code and release repository of MasterDownloader. License: **GPL-3.0**.

## Tải bản Windows

Vào [Releases](https://github.com/thientrile/MasterDownloader-releases/releases), tải `MasterDownloader.exe`. Kiểm tra checksum (tuỳ chọn):

```powershell
Get-FileHash MasterDownloader.exe -Algorithm SHA256   # so với SHA256SUMS.txt
```

Dữ liệu (lịch sử, session, tài khoản IG đã mã hoá, `secret.key`) nằm ở `%APPDATA%\MasterDownloader`; dữ liệu cũ cạnh file exe được chuyển sang tự động ở lần chạy đầu. `secret.key` được tạo riêng trên từng máy, không có trong repo và không có trong bản release.

## Tự cập nhật

Bản exe kiểm tra GitHub Release mới khi mở app (tối đa 1 lần/ngày) hoặc khi bấm **Cài đặt → Kiểm tra cập nhật**. App hỏi trước khi cài (Cập nhật ngay / Để sau / Bỏ qua bản này), không cài khi đang có lượt tải, kiểm SHA256 theo `SHA256SUMS.txt`, thay exe rồi tự khởi động lại.

## Điều khoản và miễn trừ trách nhiệm

- **Mục đích:** công cụ tải nội dung cho mục đích cá nhân. Chỉ tải nội dung bạn có quyền tải (của chính bạn, được chủ sở hữu cho phép, hoặc pháp luật cho phép). Bạn tự chịu trách nhiệm tuân thủ luật bản quyền và Điều khoản dịch vụ của từng nền tảng.
- **Không liên kết:** không liên kết, không được bảo trợ bởi TikTok, ByteDance, Meta (Facebook, Instagram), Google (YouTube) hay nền tảng nào khác. Tên và nhãn hiệu thuộc về chủ sở hữu tương ứng.
- **Không bảo hành:** phần mềm được cung cấp "NGUYÊN TRẠNG" (AS IS), không có bất kỳ bảo đảm nào. Tác giả không chịu trách nhiệm về thiệt hại phát sinh từ việc sử dụng phần mềm, trong phạm vi tối đa pháp luật cho phép.
- **Dữ liệu:** không thu thập dữ liệu. Tài khoản và cookie chỉ lưu trên máy bạn (`%APPDATA%\MasterDownloader`). App chỉ kết nối tới nền tảng bạn tải và tới GitHub để kiểm tra cập nhật.
- **Chưa ký số:** Windows SmartScreen sẽ cảnh báo ở lần chạy đầu (bấm **More info → Run anyway**). Kiểm tính toàn vẹn bằng `Get-FileHash <file> -Algorithm SHA256` rồi so với `SHA256SUMS.txt`.
- **Giấy phép: GPL-3.0** (toàn văn trong `LICENSE`). Mã nguồn: [thientrile/MasterDownloader-releases](https://github.com/thientrile/MasterDownloader-releases). Thành phần bên thứ ba theo giấy phép riêng của chúng: `THIRD_PARTY_LICENSES.txt`. Lưu ý pháp lý đầy đủ: `DISCLAIMER.txt`.
- **Liên hệ, gỡ nội dung, khiếu nại:** mở [Issue ở repo releases](https://github.com/thientrile/MasterDownloader-releases/issues).

**English:** Personal-use download tool. Download only content you have the right to; you are responsible for complying with copyright law and each platform's Terms of Service. Not affiliated with or endorsed by TikTok, ByteDance, Meta, Google/YouTube or any other platform; trademarks belong to their owners. Provided "AS IS" without warranty; no liability to the extent permitted by law. No data collection: credentials and cookies stay on your computer. Unsigned executable: expect a SmartScreen warning; verify with `SHA256SUMS.txt`. License: GPL-3.0 (`LICENSE`), source code at https://github.com/thientrile/MasterDownloader-releases; third-party licenses in `THIRD_PARTY_LICENSES.txt`; full notice in `DISCLAIMER.txt`. Contact/takedown: open an issue in the releases repo.

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
