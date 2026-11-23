"""Ban va tu dong: yt-dlp/gallery-dl tren PyPI co moi hon ban trong Release moi nhat khong.

  --write FILE                    ghi version dang cai (luc build) -> asset versions.txt
  --check --tag vX.Y.Z [--released FILE]
                                  in 'tag=vX.Y.Z+1' neu can phat hanh, 'tag=' neu khong (cho GITHUB_OUTPUT)
"""
import argparse
import json
import re
import sys
import urllib.request
from importlib import metadata

PACKAGES = ("yt-dlp", "gallery-dl")


def parse_versions(text):
    return dict(line.strip().split("==", 1) for line in text.splitlines() if "==" in line)


def format_versions(versions):
    return "".join(f"{p}=={versions[p]}\n" for p in PACKAGES)


def needs_build(latest, released_text):
    """Release cu khong co versions.txt (None) thi coi nhu can build."""
    if released_text is None:
        return True
    released = parse_versions(released_text)
    return any(released.get(p) != latest[p] for p in PACKAGES)


def next_patch(tag):
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        raise ValueError(f"Tag khong dang vX.Y.Z: {tag!r}")
    major, minor, patch = map(int, m.groups())
    return f"v{major}.{minor}.{patch + 1}"


def pypi_latest(package):
    with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=30) as r:
        return json.load(r)["info"]["version"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tag")
    ap.add_argument("--released")
    a = ap.parse_args(argv)
    if a.write:
        with open(a.write, "w", encoding="utf-8") as f:
            f.write(format_versions({p: metadata.version(p) for p in PACKAGES}))
        return
    if not (a.check and a.tag):
        ap.error("can --write FILE hoac --check --tag TAG")
    released = None
    if a.released:
        with open(a.released, encoding="utf-8") as f:
            released = f.read()
    latest = {p: pypi_latest(p) for p in PACKAGES}
    print(f"PyPI: {latest}; Release {a.tag}: {released!r}", file=sys.stderr)
    print(f"tag={next_patch(a.tag) if needs_build(latest, released) else ''}")


if __name__ == "__main__":
    main()
