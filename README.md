# MasterDownloader — bản phát hành

App desktop Windows tải video/ảnh từ TikTok, Instagram, Facebook, kèm quét và xoá file trùng.

Repo này chỉ chứa bản phát hành. Mã nguồn là private.

## Tải về

Vào tab [Releases](https://github.com/thientrile/MasterDownloader-releases/releases/latest):

- `MasterDownloader-Setup.exe`: bộ cài (khuyên dùng), có shortcut Start Menu và gỡ cài đặt trong "Apps & features".
- `MasterDownloader.exe`: bản portable, chạy trực tiếp không cần cài.

App tự kiểm tra và cài bản mới từ đây.

## Kiểm tra checksum (tuỳ chọn)

So với [`SHA256SUMS.txt`](https://github.com/thientrile/MasterDownloader-releases/releases/latest/download/SHA256SUMS.txt):

```powershell
Get-FileHash MasterDownloader-Setup.exe -Algorithm SHA256
```

File exe chưa được ký số, nên lần đầu chạy Windows SmartScreen có thể cảnh báo: bấm **More info → Run anyway**.
