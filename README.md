# MasterDownloader — bản phát hành / releases

App Windows miễn phí tải video/ảnh từ TikTok, Instagram, Facebook, kèm quét và xoá file trùng.
Free Windows app to download videos/photos from TikTok, Instagram and Facebook, with a duplicate-file finder.

Repo này chỉ chứa bản phát hành. / This repository only hosts releases.

## Tải về / Download

Vào [Releases](https://github.com/thientrile/MasterDownloader-releases/releases/latest):

- `MasterDownloader-Setup.exe`: bộ cài theo người dùng, không cần quyền admin (khuyên dùng). Có shortcut Start Menu và gỡ cài đặt trong **Settings → Apps**. Gỡ cài đặt không xoá dữ liệu của bạn. / Per-user installer, no admin needed (recommended).
- `MasterDownloader.exe`: bản portable / portable build.
- [`SHA256SUMS.txt`](https://github.com/thientrile/MasterDownloader-releases/releases/latest/download/SHA256SUMS.txt), `THIRD_PARTY_LICENSES.txt`, `TERMS.txt`.

App tự kiểm tra và cài bản mới từ đây. / The app updates itself from here.

## Điều khoản và miễn trừ trách nhiệm

- **Mục đích:** công cụ tải nội dung cho mục đích cá nhân. Chỉ tải nội dung bạn có quyền tải (của chính bạn, được chủ sở hữu cho phép, hoặc pháp luật cho phép). Bạn tự chịu trách nhiệm tuân thủ luật bản quyền và Điều khoản dịch vụ của từng nền tảng.
- **Không liên kết:** không liên kết, không được bảo trợ bởi TikTok, ByteDance, Meta (Facebook, Instagram), Google (YouTube) hay nền tảng nào khác. Tên và nhãn hiệu thuộc về chủ sở hữu tương ứng.
- **Không bảo hành:** phần mềm được cung cấp "NGUYÊN TRẠNG" (AS IS), không có bất kỳ bảo đảm nào. Tác giả không chịu trách nhiệm về thiệt hại phát sinh từ việc sử dụng phần mềm, trong phạm vi tối đa pháp luật cho phép.
- **Dữ liệu:** không thu thập dữ liệu. Tài khoản và cookie chỉ lưu trên máy bạn (`%APPDATA%\MasterDownloader`). App chỉ kết nối tới nền tảng bạn tải và tới GitHub để kiểm tra cập nhật.
- **Chưa ký số:** Windows SmartScreen sẽ cảnh báo ở lần chạy đầu (bấm **More info → Run anyway**). Kiểm tính toàn vẹn bằng `Get-FileHash <file> -Algorithm SHA256` rồi so với `SHA256SUMS.txt`.
- **Giấy phép:** phần mềm miễn phí, mã đóng, mọi quyền được bảo lưu (xem `TERMS.txt`). Thành phần bên thứ ba theo giấy phép riêng của chúng: `THIRD_PARTY_LICENSES.txt`.
- **Liên hệ, gỡ nội dung, khiếu nại:** mở [Issue ở repo releases](https://github.com/thientrile/MasterDownloader-releases/issues).

**English:** Personal-use download tool. Download only content you have the right to; you are responsible for complying with copyright law and each platform's Terms of Service. Not affiliated with or endorsed by TikTok, ByteDance, Meta, Google/YouTube or any other platform; trademarks belong to their owners. Provided "AS IS" without warranty; no liability to the extent permitted by law. No data collection: credentials and cookies stay on your computer. Unsigned executable: expect a SmartScreen warning; verify with `SHA256SUMS.txt`. Freeware, all rights reserved (`TERMS.txt`); third-party licenses in `THIRD_PARTY_LICENSES.txt`. Contact/takedown: open an issue in the releases repo.
