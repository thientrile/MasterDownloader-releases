"""Sinh THIRD_PARTY_LICENSES.txt tu moi truong build that (chay sau pip install, truoc PyInstaller).

Liet ke: Python, cac goi runtime (bao dong tu requirements.txt, tru PyInstaller vi chi la cong cu build),
bootloader PyInstaller, va ban ffmpeg ma imageio-ffmpeg dong goi. Kem van ban giay phep tu tung goi.
"""
import os
import platform
import re
import subprocess
import sys
from importlib import metadata

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_ONLY = {"pyinstaller"}
LICENSE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE)[^/]*$", re.I)


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_closure(top_level):
    """Ten cac distribution can luc chay: top_level + phu thuoc bat buoc (marker danh gia theo may build)."""
    env = default_environment()
    seen, stack = {}, list(top_level)
    while stack:
        name = norm(stack.pop())
        if name in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # vd. goi chi danh cho he dieu hanh khac
        seen[name] = dist
        for spec in dist.requires or []:
            req = Requirement(spec)
            if req.marker is None or req.marker.evaluate({**env, "extra": ""}):
                stack.append(req.name)
    return seen


def license_name(dist):
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    lic = (md.get("License") or "").strip()
    if lic and "\n" not in lic and len(lic) < 120:
        return lic
    classifiers = [c.split(" :: ")[-1] for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    return "; ".join(classifiers) or "xem van ban ben duoi / see text below"


def license_texts(dist):
    out = []
    for f in dist.files or []:
        if LICENSE_FILE.search(str(f)):
            try:
                out.append((str(f), f.locate().read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    return out


def project_url(dist):
    md = dist.metadata
    urls = [u.split(",", 1)[-1].strip() for u in md.get_all("Project-URL") or []]
    return md.get("Home-page") or (urls[0] if urls else f"https://pypi.org/project/{dist.metadata['Name']}/")


def ffmpeg_license(config):
    """Giay phep cua ban ffmpeg theo dong 'configuration:'."""
    if "--enable-nonfree" in config:
        return "nonfree (KHONG duoc phan phoi lai / not redistributable)"
    if "--enable-gpl" in config:
        return "GPL-3.0-or-later" if "--enable-version3" in config else "GPL-2.0-or-later"
    return "LGPL-3.0-or-later" if "--enable-version3" in config else "LGPL-2.1-or-later"


def section(title, lines):
    return "\n".join(["=" * 78, title, "=" * 78, *lines, ""])


def build(top_level):
    parts = [
        "THIRD-PARTY SOFTWARE NOTICES / GIAY PHEP PHAN MEM BEN THU BA",
        "MasterDownloader dong goi cac phan mem duoi day; moi phan mem thuoc ve chu so huu cua no",
        "va duoc phan phoi theo giay phep rieng cua no.",
        "MasterDownloader bundles the software below; each belongs to its owners and is",
        "distributed under its own license.",
        "",
        section(f"Python {platform.python_version()}", [
            "License: PSF-2.0 (Python Software Foundation License)",
            "URL: https://docs.python.org/3/license.html",
        ]),
    ]
    dists = runtime_closure(top_level)
    try:
        dists["pyinstaller"] = metadata.distribution("pyinstaller")  # bootloader nam trong exe
    except metadata.PackageNotFoundError:
        pass
    for name in sorted(dists):
        d = dists[name]
        lines = [f"License: {license_name(d)}", f"URL: {project_url(d)}"]
        if name == "pyinstaller":
            lines.append("Note: only the bootloader is bundled (GPL-2.0-or-later with bootloader exception).")
        for path, text in license_texts(d):
            lines += ["", f"--- {path} ---", text.rstrip()]
        parts.append(section(f"{d.metadata['Name']} {d.version}", lines))
    if "imageio-ffmpeg" in dists:
        import imageio_ffmpeg
        out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-version"], capture_output=True, text=True).stdout
        config = next((l for l in out.splitlines() if l.startswith("configuration:")), "")
        parts.append(section(f"FFmpeg ({out.splitlines()[0] if out else 'unknown'})", [
            f"License: {ffmpeg_license(config)}",
            "Binary shipped by imageio-ffmpeg: https://github.com/imageio/imageio-ffmpeg",
            "FFmpeg source: https://ffmpeg.org/download.html  |  License: https://ffmpeg.org/legal.html",
            config,
        ]))
    return "\n".join(parts)


def main(dest):
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        top = [Requirement(l).name for l in f.read().splitlines() if l.strip() and not l.startswith("#")]
    text = build([n for n in top if norm(n) not in BUILD_ONLY])
    with open(dest, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main(sys.argv[1])
