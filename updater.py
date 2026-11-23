"""Tu cap nhat ban exe Windows tu GitHub Releases (repo public, khong can token)."""
import hashlib
import os
import re
import subprocess
import sys

import requests

# Repo public chua ca ma nguon lan Release
RELEASES_REPO = "thientrile/MasterDownloader-releases"
LATEST_URL = f"https://api.github.com/repos/{RELEASES_REPO}/releases/latest"
EXE_NAME = "MasterDownloader.exe"
SUMS_NAME = "SHA256SUMS.txt"


def can_self_update():
    return getattr(sys, "frozen", False) and sys.platform == "win32"


def parse_version(text):
    """'v1.2.3' -> (1, 2, 3); ban dev/khong hop le -> (0,)."""
    m = re.match(r"v?(\d+(?:\.\d+)*)$", (text or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else (0,)


def check_latest(current_version, timeout=15):
    """Tra ve (tag, exe_url, sums_url) neu Release moi hon ban dang chay, nguoc lai None."""
    resp = requests.get(LATEST_URL, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    data = resp.json()
    tag = data.get("tag_name", "")
    if parse_version(tag) <= parse_version(current_version):
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    if not assets.get(EXE_NAME) or not assets.get(SUMS_NAME):
        return None
    return tag, assets[EXE_NAME], assets[SUMS_NAME]


def expected_sha256(sums_text, name=EXE_NAME):
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def download_verified(exe_url, sums_url, dest, timeout=60):
    """Tai exe ve dest va kiem SHA256 theo SHA256SUMS.txt; sai thi xoa file va raise."""
    sums = requests.get(sums_url, timeout=timeout)
    sums.raise_for_status()
    expected = expected_sha256(sums.text)
    if not expected:
        raise ValueError(f"{SUMS_NAME} khong co dong cho {EXE_NAME}")
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


def relaunch(current_exe):
    # PyInstaller onefile >= 6.10: thieu bien nay thi ban moi dung lai thu muc _MEI (code cu) cua tien trinh cha
    subprocess.Popen([current_exe], close_fds=True, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
