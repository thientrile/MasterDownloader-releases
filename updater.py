"""Tu cap nhat ban exe Windows tu GitHub Releases (repo public, khong can token)."""
import hashlib
import os
import re
import subprocess
import sys
import tempfile

import requests

# Repo public chua ca ma nguon lan Release
RELEASES_REPO = "thientrile/MasterDownloader-releases"
LATEST_URL = f"https://api.github.com/repos/{RELEASES_REPO}/releases/latest"
EXE_NAME = "MasterDownloader.exe"
SETUP_NAME = "MasterDownloader-Setup.exe"
SUMS_NAME = "SHA256SUMS.txt"


def can_self_update():
    return getattr(sys, "frozen", False) and sys.platform == "win32"


def is_installed(exe):
    """Ban cai bang Inno Setup co unins000.exe canh exe; khong co la ban portable."""
    return os.path.exists(os.path.join(os.path.dirname(exe), "unins000.exe"))


def parse_version(text):
    """'v1.2.3' -> (1, 2, 3); ban dev/khong hop le -> (0,)."""
    m = re.match(r"v?(\d+(?:\.\d+)*)$", (text or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else (0,)


def check_latest(current_version, asset=EXE_NAME, timeout=15):
    """Tra ve (tag, asset_url, sums_url) neu Release moi hon ban dang chay, nguoc lai None."""
    resp = requests.get(LATEST_URL, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    data = resp.json()
    tag = data.get("tag_name", "")
    if parse_version(tag) <= parse_version(current_version):
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    if not assets.get(asset) or not assets.get(SUMS_NAME):
        return None
    return tag, assets[asset], assets[SUMS_NAME]


def expected_sha256(sums_text, name=EXE_NAME):
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def download_verified(exe_url, sums_url, dest, name=EXE_NAME, timeout=60):
    """Tai file `name` ve dest va kiem SHA256 theo SHA256SUMS.txt; sai thi xoa file va raise."""
    sums = requests.get(sums_url, timeout=timeout)
    sums.raise_for_status()
    expected = expected_sha256(sums.text, name)
    if not expected:
        raise ValueError(f"{SUMS_NAME} khong co dong cho {name}")
    digest = hashlib.sha256()
    with requests.get(exe_url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                digest.update(chunk)
    if digest.hexdigest() != expected:
        os.remove(dest)
        raise ValueError("Checksum SHA256 khong khop, da huy cap nhat")
    return dest


def swap_exe(new_exe, current_exe):
    """Windows cho doi ten exe dang chay: current -> .old, new -> current. Loi thi khoi phuc."""
    old = current_exe + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.replace(current_exe, old)
    try:
        os.replace(new_exe, current_exe)
    except OSError:
        os.replace(old, current_exe)
        raise
    return old


def cleanup_old(current_exe):
    """Goi luc khoi dong: xoa ban .old cua lan cap nhat truoc."""
    try:
        os.remove(current_exe + ".old")
    except OSError:
        pass


def download_setup(setup_url, sums_url):
    """Ban cai dat: tai Setup moi vao thu muc tam, da kiem SHA256."""
    dest = os.path.join(tempfile.gettempdir(), SETUP_NAME)
    return download_verified(setup_url, sums_url, dest, name=SETUP_NAME)


def _reset_env():
    # PyInstaller onefile >= 6.10: thieu bien nay thi ban moi dung lai thu muc _MEI (code cu) cua tien trinh cha
    return {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}


def relaunch(current_exe):
    subprocess.Popen([current_exe], close_fds=True, env=_reset_env())


def run_setup(setup_path):
    """Cai im lang roi Setup tu mo lai app (/relaunch=1, xem installer.iss); app phai thoat ngay sau do."""
    # App do Setup mo thua huong env nay, nen cung can reset _MEI
    subprocess.Popen([setup_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/relaunch=1"],
                     close_fds=True, env=_reset_env())
