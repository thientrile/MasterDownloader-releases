"""Chup anh man hinh cho README: python tools/screenshots.py [docs/images]

Chay app tu ban sao ma nguon trong thu muc tam (khong doc config, cookie, lich su that canh App.py),
dien du lieu gia (link vi du, duong dan gia) roi QWidget.grab() tung trang. Can QT_QPA_PLATFORM=offscreen
neu khong co man hinh. Tren WSL/Windows dung font Segoe UI cua Windows cho giong app that.
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ("App.py", "MasterDownloader.py", "updater.py", "version.py")
FAKE_FOLDER = r"D:\Videos\MasterDownloader"
VERSION = "1.0.2"  # ban phat hanh dau tien o repo nay; anh khong phu thuoc version.py dang build
ROWS = [
    ("https://www.tiktok.com/@example/video/7300000000000000001", "TikTok", "Hoàn tất", 100),
    ("https://www.tiktok.com/@example/photo/7300000000000000002", "TikTok", "Đang tải", 64),
    ("https://www.tiktok.com/@example", "TikTok", "Đang chờ", 0),
    ("https://www.instagram.com/p/EXAMPLE123/", "Instagram", "Hoàn tất", 100),
    ("https://www.facebook.com/watch/?v=1000000000000001", "Facebook", "Lỗi", 30),
]
LOG = [
    ("Đã thêm https://www.tiktok.com/@example/video/7300000000000000001", "INFO"),
    ("Hoàn tất: 1 video", "SUCCESS"),
    ("Đang tải https://www.tiktok.com/@example/photo/7300000000000000002 (5 ảnh)", "INFO"),
]


def load_windows_fonts(QFontDatabase):
    for d in (r"C:\Windows\Fonts", "/mnt/c/Windows/Fonts"):
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisym.ttf", "consola.ttf"):
            path = os.path.join(d, name)
            if os.path.exists(path):
                QFontDatabase.addApplicationFont(path)


def main(out_dir):
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="md-shots-")
    for name in SOURCES:
        shutil.copy(os.path.join(ROOT, name), tmp)
    with open(os.path.join(tmp, "version.py"), "w") as f:
        f.write(f'__version__ = "{VERSION}"\n')
    # Khong de app tim thu muc Downloads that (WSL hoi cmd.exe lay %USERPROFILE%)
    os.environ.pop("WSL_DISTRO_NAME", None)
    os.environ["HOME"] = tmp
    sys.path.insert(0, tmp)
    os.chdir(tmp)

    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtWidgets import QApplication
    import App

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    load_windows_fonts(QFontDatabase)
    w = App.MainWindow()
    w.resize(1180, 760)
    w.txt_default_folder.setText(FAKE_FOLDER)
    w.folder_input.clear()
    styles = {"Hoàn tất": App.PROGRESS_STYLE_SUCCESS, "Lỗi": App.PROGRESS_STYLE_ERROR}
    for url, platform, status, pct in ROWS:
        w.add_table_row(url, platform, FAKE_FOLDER + "\\example", auto_start=False, status=status)
        bar = w.table.cellWidget(w.table.rowCount() - 1, 3)
        bar.setValue(pct)
        bar.setStyleSheet(styles.get(status, App.PROGRESS_STYLE_DEFAULT))
    w.url_input.setText("https://www.tiktok.com/@example/video/7300000000000000003")
    w.show()

    def shot(name, widget=w):
        app.processEvents()
        widget.grab().save(os.path.join(out_dir, name), "PNG", 0)  # 0 = nen manh nhat
        print(name, os.path.getsize(os.path.join(out_dir, name)) // 1024, "KB")

    w.nav.setCurrentRow(0)
    shot("download.png")
    w.log_output.clear()
    for msg, level in LOG:
        w.log(msg, level)
    w.set_log_visible(True)
    shot("main.png")
    w.set_log_visible(False)

    w.nav.setCurrentRow(1)
    shot("duplicates.png")
    groups = [
        [FAKE_FOLDER + r"\example\7300000000000000001.mp4", FAKE_FOLDER + r"\example\7300000000000000001 (1).mp4"],
        [FAKE_FOLDER + r"\example\photo_01.jpg", FAKE_FOLDER + r"\example\photo_01 (1).jpg",
         FAKE_FOLDER + r"\example\photo_01 (2).jpg"],
    ]
    App.DuplicatesDialog._size = staticmethod(lambda p: 4_812_000 if p.endswith(".mp4") else 512_000)
    App.DuplicatesDialog._mtime = staticmethod(lambda p: "2026-11-20 09:15")
    dlg = App.DuplicatesDialog(groups, parent=w)
    dlg.show()
    shot("duplicates-dialog.png", dlg)
    dlg.close()

    w.nav.setCurrentRow(2)
    w.resize(1180, 1180)  # du cao de thay ca phan cookie va cap nhat
    shot("settings.png")
    w.close()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "images"))
