import os
import re
import sys
import time
import random
import itertools
import json
import errno
import threading
import subprocess
import shutil
import hashlib
from urllib.parse import unquote, urlparse
import requests
import yt_dlp
import instaloader
import browser_cookie3
from PIL import Image
import imagehash
from cryptography.fernet import Fernet
from colorama import init, Fore, Style

# --- FIX LỖI HIỂN THỊ TIẾNG VIỆT TRÊN WINDOWS ---
if sys.stdout and sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
# -----------------------------------------------

# Khởi tạo màu sắc
init(autoreset=True)

USER_DATA = ("history.json", "gui_config.json", "secret.key", "ig_credentials.txt", "cookies.json", "sessions", "archives")


def app_data_dir(base_dir):
    """Ban exe Windows luu du lieu o %APPDATA%\\MasterDownloader (cap nhat exe khong dung toi, chay duoc trong Program Files).
    Lan dau chuyen du lieu cu canh file exe sang. Chay tu source: giu canh App.py."""
    appdata = os.environ.get("APPDATA")
    if not (getattr(sys, "frozen", False) and sys.platform == "win32" and appdata):
        return base_dir
    target = os.path.join(appdata, "MasterDownloader")
    os.makedirs(target, exist_ok=True)
    for name in USER_DATA:
        src, dst = os.path.join(base_dir, name), os.path.join(target, name)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
            except OSError as e:
                print(f"Khong chuyen duoc {name} sang {target}: {e}")
    return target

class MasterDownloader:
    def __init__(self):
        # Determine if we are running in a bundle or a normal python environment
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        # Thu muc du lieu chung (history, credentials, sessions)
        self.data_dir = app_data_dir(self.base_dir)
        # Thu muc tai khi chua cau hinh: khong ghi canh exe (Program Files khong ghi duoc)
        self.download_root = os.path.join(os.path.expanduser("~"), "Downloads", "MasterDownloader")
        # Thu muc rieng de giu session, de de quan ly va xoa khi can
        self.session_dir = os.path.join(self.data_dir, "sessions")
        os.makedirs(self.session_dir, exist_ok=True)
        # Thu muc luu lich su tai xuong (archives) de tranh trung lap
        self.archive_dir = os.path.join(self.data_dir, "archives")
        os.makedirs(self.archive_dir, exist_ok=True)
        # So MD5 cac file da xoa vi trung, de chan tai lai (toan cuc)
        self.deleted_md5_file = os.path.join(self.archive_dir, "deleted_md5.txt")
        self._deleted_md5 = self._load_deleted_md5()
        # File luu lich su cau hinh thu muc theo platform/user
        self.history_file = os.path.join(self.data_dir, "history.json")
        self.ig = instaloader.Instaloader(
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            max_connection_attempts=3,
            request_timeout=300.0,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
            )
        )
        
        # Crypto setup
        self.key_file = os.path.join(self.data_dir, "secret.key")
        self.cipher = self._load_crypto_key()
        
        self.ig_credentials_file = os.path.join(self.data_dir, "ig_credentials.txt")
        self.cookies_file = os.path.join(self.data_dir, "cookies.json")
        self.ig_username = None  # Nho username da nhap de khong hoi lai
        self.ig_password = None  # Luu password da nhap lan dau
        self.ig_logged_in = False
        # Cau hinh giam nhip de giam 401
        self.ig_profile_backoff = [180, 300, 600]
        self.ig_wait_401_base = 420
        self.ig_wait_401_jitter = (45, 120)
        self.ig_sleep_range = (20, 45)
        self.ig_retry_on_401 = 3
        self.ig_max_posts = 20  # Gioi han so bai tai moi lan de giam risk (None de khong gioi han)
        self.ig_download_stories = False
        self.ig_download_highlights = False
        self.ig_cooldown_until = 0
        self.ig_block_cooldown = 6 * 60 * 60
        self.ig_lock = threading.Lock()
        self.history = self.load_history()
        self.migrate_archives()
        self.migrate_security()

    def _is_ig_block_error(self, error):
        msg = str(error).lower()
        return any(token in msg for token in [
            "401",
            "403",
            "forbidden",
            "unauthorized",
            "too many requests",
            "please wait a few minutes",
            "few minutes",
            "429",
        ])

    def _is_ig_invalid_request_error(self, error):
        msg = str(error).lower()
        return "400 bad request" in msg or '"invalid request"' in msg or "invalid request" in msg

    def _start_ig_cooldown(self, reason):
        self.ig_cooldown_until = time.time() + self.ig_block_cooldown
        wait_hours = self.ig_block_cooldown / 3600
        print(f"{Fore.RED}🛑 IG dang bi chan/rate-limit ({reason}). Tam dung IG khoang {wait_hours:.0f} gio de tranh bi khoa nang hon.")

    def _ig_cooldown_remaining(self):
        return max(0, int(self.ig_cooldown_until - time.time()))

    def _create_isolated_ig_client(self):
        """Create a fresh Instaloader instance so parallel jobs do not share dirname_pattern."""
        client = instaloader.Instaloader(
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            max_connection_attempts=3,
            request_timeout=300.0,
            user_agent=self.ig.context.user_agent,
        )

        # Reuse headers/cookies when possible
        try:
            client.context._session.headers.update(self.ig.context._session.headers)
        except Exception:
            pass

        try:
            client.context._session.cookies.update(self.ig.context._session.cookies)
        except Exception:
            pass

        try:
            self._apply_instagram_browser_session(client.context._session)
        except Exception:
            pass

        # Load session file if we have a logged-in user (keeps Stories/Highlights working)
        if self.ig_username:
            session_path = self.session_file_path(self.ig_username)
            if os.path.exists(session_path):
                try:
                    client.load_session_from_file(self.ig_username, filename=session_path)
                except Exception as e:
                    print(f"{Fore.YELLOW}⚠️  Khong tai duoc session cho IG client moi: {e}")

        return client

    def migrate_security(self):
        """Auto-encrypt plain text credentials on startup."""
        # 1. Credentials
        if os.path.exists(self.ig_credentials_file):
            try:
                with open(self.ig_credentials_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                # Simple check: Fernet tokens are usually long and start with gAAAA
                if not content.startswith("gAAAA"):
                    # It's likely plain text
                    print("🔒 Encrypting legacy credentials file...")
                    self.save_credentials(content.splitlines()[0], content.splitlines()[1])
            except:
                 pass
        
        # 2. Cookies
        if os.path.exists(self.cookies_file):
            changed = False
            try:
                with open(self.cookies_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for k, v in data.items():
                    if v and not v.startswith("gAAAA"):
                        print(f"🔒 Encrypting legacy cookie for {k}...")
                        data[k] = self._encrypt_text(v)
                        changed = True
                
                if changed:
                    with open(self.cookies_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
            except:
                pass

    def _load_crypto_key(self):
        """Load or create encryption key."""
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, "rb") as kf:
                    key = kf.read()
                return Fernet(key)
            except:
                pass # Re-create if corrupt
        
        # Create new key
        key = Fernet.generate_key()
        try:
            with open(self.key_file, "wb") as kf:
                kf.write(key)
        except:
            pass # Fail silently if cannot write
        return Fernet(key)

    def _encrypt_text(self, text):
        if not text: return ""
        try:
            # Need to handle if text is already encrypted? No, we trust caller.
            # But wait, if we are saving, we invoke this.
            return self.cipher.encrypt(text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            print(f"Encryption error: {e}")
            return text

    def _decrypt_text(self, text):
        if not text: return ""
        try:
            return self.cipher.decrypt(text.encode('utf-8')).decode('utf-8')
        except Exception:
            if text.startswith("gAAAA"):
                # Ma hoa bang secret.key khac (vd. khoa da doi): khong tra ve ban ma nhu mat khau/cookie
                print(f"{Fore.YELLOW}⚠️  Khong giai ma duoc du lieu da luu (secret.key da doi). Hay nhap lai tai khoan/cookie.")
                return ""
            # Fallback if text is not encrypted (migration support)
            return text

    def migrate_archives(self):
        """Move legacy downloaded.txt files to new centralized archives folder."""
        if not self.history:
            return

        print(f"{Fore.CYAN}🧹 Checking for legacy history files...")
        
        for key, data in self.history.items():
            folder = data.get("folder")
            if not folder or not os.path.exists(folder):
                continue

            # 1. Migrate yt-dlp downloaded.txt (TikTok/Facebook)
            legacy_file = os.path.join(folder, "downloaded.txt")
            if os.path.exists(legacy_file):
                # Guess platform/username from key
                lower_key = key.lower()
                username = key.split(':')[-1]
                safe_name = "".join(c for c in username if c.isalnum() or c in ('-','_','.',' '))
                
                target_name = None
                if "facebook" in lower_key or "fb" in lower_key:
                    target_name = f"facebook_{safe_name}.txt"
                elif "tiktok" in lower_key:
                    target_name = f"tiktok_{safe_name}.txt"
                else:
                    # heuristic: try to read content?
                    if "tiktok" in folder.lower():
                        target_name = f"tiktok_{safe_name}.txt"
                    elif "facebook" in folder.lower():
                         target_name = f"facebook_{safe_name}.txt"
                
                if target_name:
                    new_path = os.path.join(self.archive_dir, target_name)
                    try:
                        # Append content if target exists
                        if os.path.exists(new_path):
                            with open(legacy_file, 'r', encoding='utf-8', errors='ignore') as f_src, open(new_path, 'a', encoding='utf-8') as f_dst:
                                f_dst.write("\n" + f_src.read())
                            os.remove(legacy_file)
                            print(f"{Fore.GREEN}   -> Merged old history to {target_name}")
                        else:
                            os.rename(legacy_file, new_path)
                            print(f"{Fore.GREEN}   -> Moved old history to {target_name}")
                    except Exception as e:
                        print(f"{Fore.RED}   -> Error migrating {legacy_file}: {e}")

    def session_file_path(self, username):
        return os.path.join(self.session_dir, f"session-{username}")

    def load_history(self):
        if not os.path.exists(self.history_file):
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_history(self):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _touch_archive_file(self, archive_path):
        """Ensure the download archive file exists and is writable."""
        if not archive_path:
            return True

        dir_name = os.path.dirname(archive_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        try:
            with open(archive_path, "a", encoding="utf-8"):
                return True
        except OSError as e:
            print(f"{Fore.YELLOW}⚠️  Khong the mo download archive {archive_path!r}: {e}")
            return False

    def _reset_archive_file(self, archive_path):
        if not archive_path:
            return False
        try:
            with open(archive_path, "w", encoding="utf-8"):
                return True
        except OSError as e:
            print(f"{Fore.YELLOW}⚠️  Reset download archive that bai {archive_path!r}: {e}")
            return False

    def _read_manual_cookie_deprecated(self):
        """Helper to read and clean manual cookie string. DEPRECATED."""
        return self.get_manual_cookie("instagram") or self.get_manual_cookie("tiktok")

    def _sanitize_name(self, value, fallback):
        value = (value or "").strip().strip("@")
        safe = "".join(c for c in value if c.isalnum() or c in ('-', '_', '.', ' ')).strip()
        return safe or fallback

    def _archive_path(self, folder, platform, username, kind="ydl"):
        safe_platform = self._sanitize_name(platform, "site").lower()
        safe_name = self._sanitize_name(username, safe_platform)
        safe_kind = self._sanitize_name(kind, "history").lower()
        return os.path.join(folder, f".masterdownloader_{safe_platform}_{safe_kind}_{safe_name}.txt")

    def _merge_archive_once(self, old_path, new_path):
        if not old_path or not new_path or old_path == new_path or not os.path.exists(old_path):
            return
        try:
            old_lines = []
            with open(old_path, "r", encoding="utf-8", errors="ignore") as src:
                old_lines = [line for line in src if line.strip()]
            if not old_lines:
                return
            existing = set()
            if os.path.exists(new_path):
                with open(new_path, "r", encoding="utf-8", errors="ignore") as dst_read:
                    existing = {line.strip() for line in dst_read if line.strip()}
            with open(new_path, "a", encoding="utf-8") as dst:
                for line in old_lines:
                    stripped = line.strip()
                    if stripped and stripped not in existing:
                        dst.write(stripped + "\n")
                        existing.add(stripped)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️  Khong merge duoc history cu {old_path!r}: {e}")

    def _instagram_url_kind(self, url):
        parsed = urlparse(url if "://" in url else f"https://{url}")
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return "home"
        first = parts[0].lower()
        if first == "stories" and len(parts) > 1 and parts[1].lower() == "highlights":
            return "highlight"
        if first in {"p", "reel", "reels", "tv"}:
            return "post"
        if first == "stories":
            return "story"
        if first in {"explore", "accounts", "direct"}:
            return "other"
        return "profile"

    def _has_usable_instagram_cookie(self):
        cookies = self._parse_cookie_string(self.get_manual_cookie("instagram") or "")
        return bool(cookies.get("sessionid") and cookies.get("ds_user_id"))

    def _edge_cookie_db_exists(self):
        candidates = [
            os.path.expanduser("~/.config/microsoft-edge/Default/Cookies"),
            os.path.expanduser("~/.config/microsoft-edge/Default/Network/Cookies"),
            os.path.expanduser("~/.config/microsoft-edge-dev/Default/Cookies"),
            os.path.expanduser("~/.config/microsoft-edge-dev/Default/Network/Cookies"),
        ]
        return any(os.path.exists(path) for path in candidates)

    def _instagram_web_profile_info(self, username):
        cookie = self.get_manual_cookie("instagram")
        if not cookie:
            return None, "no_cookie"
        headers = self._instagram_browser_headers(cookie, referer=f"https://www.instagram.com/{username}/")
        headers["Cookie"] = cookie
        try:
            response = requests.get(
                "https://www.instagram.com/api/v1/users/web_profile_info/",
                params={"username": username},
                headers=headers,
                timeout=25,
            )
            if response.status_code in (401, 403, 429):
                return None, f"http_{response.status_code}"
            if response.status_code == 404:
                return None, "not_found"
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("user"), None
        except Exception as e:
            return None, str(e)

    def _extract_tiktok_account_from_url(self, url):
        match = re.search(r'(?:tiktok\.com|douyin\.com)/@([^/?#]+)', url, re.IGNORECASE)
        return self._sanitize_name(match.group(1), "tiktok") if match else None

    def _extract_facebook_account_from_url(self, url):
        match = re.search(r"facebook\.com/([^/?#]+)", url, re.IGNORECASE)
        if not match:
            return None
        account = match.group(1)
        if account.lower() in {"watch", "reel", "videos", "share", "story.php", "photo.php"}:
            return None
        return self._sanitize_name(account, "facebook")

    def _resolve_tiktok_short_url(self, url):
        """vt.tiktok.com / vm.tiktok.com / tiktok.com/t/... -> link day du (theo redirect)."""
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.netloc.lower()
        if host not in {"vt.tiktok.com", "vm.tiktok.com"} and not parsed.path.startswith("/t/"):
            return url
        try:
            response = requests.get(url, allow_redirects=True, timeout=20, stream=True)
            response.close()
            return response.url or url
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️  Khong mo duoc link rut gon TikTok {url}: {e}")
            return url

    def _tiktok_url_kind(self, url):
        """video | photo | story (1 story) | stories (tat ca story cua 1 trang ca nhan) | profile."""
        parsed = urlparse(url if "://" in url else f"https://{url}")
        path = parsed.path.lower().rstrip("/")
        # Link share story tro ve /video/{id}?...&story_type=1
        if re.search(r"/@[^/]+/(?:story|stories)/\d+$", path) or re.search(r"(?:^|&)(?:story_type=[1-9]|aweme_type=40(?:&|$))", parsed.query):
            return "story"
        if re.search(r"/@[^/]+/stories$", path):
            return "stories"
        if "/photo/" in path:
            return "photo"
        if re.fullmatch(r"/@[^/]+", path):
            return "profile"
        return "video"

    def _tiktok_post_url(self, url):
        """/@user/story/{id} -> /@user/video/{id} (dang gallery-dl nhan)."""
        return re.sub(r"(/@[^/?#]+)/(?:story|stories)/(\d+)", r"\1/video/\2", url, flags=re.IGNORECASE)

    def _extract_ydl_account(self, url, fallback):
        """Ask yt-dlp for metadata when the account is not present in the URL."""
        try:
            opts = self._rate_limit_ydl_opts()
            opts.update({
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'extract_flat': False,
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return fallback

            candidates = [
                info.get('uploader_id'),
                info.get('uploader'),
                info.get('channel_id'),
                info.get('channel'),
                info.get('creator'),
                info.get('artist'),
            ]
            for candidate in candidates:
                safe = self._sanitize_name(candidate, "")
                if safe:
                    return safe
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️  Khong lay duoc ten tai khoan tu metadata: {e}")
        return fallback

    def _parse_cookie_string(self, cookie_string):
        cookies = {}
        if not cookie_string:
            return cookies
        for pair in cookie_string.split(';'):
            if '=' not in pair:
                continue
            name, val = pair.split('=', 1)
            name = name.strip()
            val = val.strip().strip('"')
            if name:
                cookies[name] = val
        return cookies

    def _instagram_browser_headers(self, cookie_string=None, referer="https://www.instagram.com/"):
        cookies = self._parse_cookie_string(cookie_string or self.get_manual_cookie("instagram") or "")
        csrf_token = cookies.get("csrftoken")
        claim = cookies.get("ig_www_claim")
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'vi,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': referer,
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Prefers-Color-Scheme': 'dark',
            'Sec-Ch-Ua': '"Microsoft Edge";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0'
            ),
            'X-ASBD-ID': '359341',
            'X-IG-App-ID': '936619743392459',
            'X-IG-Max-Touch-Points': '0',
        }
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
        if claim:
            headers['X-IG-WWW-Claim'] = claim
        return headers

    def _apply_instagram_browser_session(self, session, cookie_string=None, referer="https://www.instagram.com/"):
        """Apply browser-like headers/cookies to Instaloader's underlying requests session."""
        cookie_string = cookie_string or self.get_manual_cookie("instagram") or ""
        session.headers.update(self._instagram_browser_headers(cookie_string, referer=referer))
        session.headers.setdefault("DNT", "1")
        for name, val in self._parse_cookie_string(cookie_string).items():
            session.cookies.set(name, val, domain=".instagram.com", path="/")
            session.cookies.set(name, val, domain="www.instagram.com", path="/")

    def _rate_limit_ydl_opts(self):
        """Shared yt-dlp options that slow requests down and retry transient blocks."""
        return {
            'retries': 10,
            'fragment_retries': 10,
            'extractor_retries': 5,
            'sleep_interval': 10,
            'max_sleep_interval': 30,
            'sleep_interval_requests': 5,
            'sleep_interval_subtitles': 5,
            'throttledratelimit': 100 * 1024,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/121.0.0.0 Safari/537.36'
                ),
            },
        }

    def _prepare_yt_dlp(self, ydl_opts, label):
        """Build a YoutubeDL instance with resilient archive handling."""
        opts = self._rate_limit_ydl_opts()
        opts.update(ydl_opts)

        # Tro yt-dlp den ffmpeg (uu tien PATH, fallback imageio-ffmpeg) de merge format/convert
        if not opts.get('ffmpeg_location'):
            ffmpeg = self._get_ffmpeg_exe()
            if ffmpeg:
                opts['ffmpeg_location'] = ffmpeg

        archive_path = opts.get('download_archive')

        if archive_path and not self._touch_archive_file(archive_path):
            print(f"{Fore.YELLOW}⚠️  Tat che do tranh trung cho {label} trong lan nay.")
            opts.pop('download_archive', None)
            archive_path = None

        try:
            return yt_dlp.YoutubeDL(opts)
        except OSError as e:
            if archive_path and e.errno == errno.EINVAL:
                print(f"{Fore.YELLOW}⚠️  Download archive bi loi cho {label}, dang reset...")
                if self._reset_archive_file(archive_path):
                    try:
                        return yt_dlp.YoutubeDL(opts)
                    except OSError as retry_err:
                        if retry_err.errno != errno.EINVAL:
                            raise
                        print(f"{Fore.YELLOW}⚠️  Archive van loi sau khi reset, se tat tranh trung cho {label}.")
                else:
                    print(f"{Fore.YELLOW}⚠️  Khong reset duoc archive, se tat tranh trung cho {label}.")
                opts.pop('download_archive', None)
                return yt_dlp.YoutubeDL(opts)
            raise

    def resolve_folder(self, platform, username, default_folder):
        # Dung chung mot key theo username cho ca IG/TikTok
        key = username
        # Back-compat: neu truoc day co luu kieu platform:username thi lay ra luon
        old_key = f"{platform}:{username}"
        folder = None
        if key in self.history:
            folder = self.history[key].get("folder")
        elif old_key in self.history:
            folder = self.history[old_key].get("folder")

        # Neu chua co thi lay default
        if not folder:
            folder = default_folder

        # Chuan hoa: neu folder cu dang TikTok_username hoac IG_username thi doi ve username thuan
        basename = os.path.basename(folder)
        if (basename.startswith("TikTok_") or basename.startswith("IG_")) and basename.endswith(username):
            folder = os.path.join(os.path.dirname(folder), username)

        # Luu lai mapping moi
        self.history[key] = {"folder": folder}
        self.save_history()
        return folder

    def update_folder(self, platform, username, folder):
        key = username
        self.history[key] = {"folder": folder}
        self.save_history()

    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def load_credentials(self):
        if not os.path.exists(self.ig_credentials_file):
            return None
        try:
            with open(self.ig_credentials_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                
            # Try to decrypt entire content
            decrypted = self._decrypt_text(content)
            
            # If decryption worked or it was plain text, we expect lines
            lines = decrypted.splitlines()
            if len(lines) >= 2:
                # If it was migrated, re-save encrypted immediately?
                # Best to just return.
                return lines[0].strip(), lines[1].strip()
        except Exception:
            return None
        return None

    def save_credentials(self, username, password):
        try:
            content = f"{username}\n{password}"
            encrypted = self._encrypt_text(content)
            with open(self.ig_credentials_file, "w", encoding="utf-8") as f:
                f.write(encrypted)
        except Exception:
            pass

    def get_manual_cookie(self, platform):
        """Get cookie string for platform (instagram/tiktok) from json file."""
        if not os.path.exists(self.cookies_file):
            return None
        try:
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cookie_encrypted = data.get(platform, "")
                if not cookie_encrypted: return None
                
                # Decrypt here
                cookie = self._decrypt_text(cookie_encrypted)
                
                return cookie.strip('"').strip("'").replace('\n', '').strip()
        except:
            return None

    def set_manual_cookie(self, platform, cookie_content):
        """Save cookie string for platform."""
        data = {}
        if os.path.exists(self.cookies_file):
             try:
                 with open(self.cookies_file, 'r', encoding='utf-8') as f:
                     data = json.load(f)
             except: pass
        
        # Encrypt before saving
        data[platform] = self._encrypt_text(cookie_content)
        
        try:
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving cookie: {e}")
            return False

    def load_session_from_manual_file(self):
        """Doc cookie tu cookies.json (dinh dang raw HTTP header)"""
        print(f"{Fore.CYAN}🔄 Dang nap cookie IG tu cookies.json...")
        
        cookie_data = self.get_manual_cookie("instagram")
        if not cookie_data:
            return False

        try:
            # Reset cookie jar de dam bao sach se
            self.ig.context._session.cookies.clear()
            
            parsed_cookies = self._parse_cookie_string(cookie_data)
            user_id_val = parsed_cookies.get('ds_user_id')

            # Update headers/cookies like a normal browser session.
            if 'Cookie' in self.ig.context._session.headers:
                del self.ig.context._session.headers['Cookie']
            self._apply_instagram_browser_session(self.ig.context._session, cookie_data)

            # Prefer the real logged-in username when Instagram accepts the cookie.
            try:
                username = self.ig.test_login()
                if username:
                    self.ig_username = username
                    self.ig.context.username = username
                    self.ig.context._is_logged_in = True
                    self.ig_logged_in = True
                    self.ig.save_session_to_file(filename=self.session_file_path(username))
                    print(f"{Fore.GREEN}✅ Da nap cookie IG va luu session theo username: {username}")
                    return True
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️  test_login voi cookie IG chua thanh cong, fallback sang ds_user_id: {e}")

            # BYPASS: Neu test_login khong duoc nhung cookie co ds_user_id thi van thu tiep
            if user_id_val:
                self.ig_username = user_id_val
                # QUAN TRONG: Set username cho context de instaloader biet dang la ai
                self.ig.context.username = self.ig_username
                self.ig.context._is_logged_in = True
                self.ig_logged_in = True
                print(f"{Fore.GREEN}✅ Da Force Manual Login cho User ID: {self.ig_username}")
                
                # FORCE SAVE: Xoa session cu, chi save cookie jar
                try:
                    session_path = self.session_file_path(self.ig_username)
                    if os.path.exists(session_path):
                        os.remove(session_path)
                    
                    # Chi save session neu khong gay loi
                    self.ig.save_session_to_file(filename=session_path)
                    print(f"{Fore.GREEN}✅ Da cap nhat session file moi cho: {self.ig_username}")
                except Exception as e:
                    # Neu save session fail, ta van tiep tuc vi cookies da nam trong memory roi
                    print(f"{Fore.YELLOW}⚠️ Canh bao: Khong the luu session ra file (khong anh huong tai ve): {e}")
                
                return True

            # Test thu xem login duoc khong (fallback neu khong tim thay user_id)
            print(f"{Fore.CYAN}👉 Dang kiem tra login voi Manual Cookie (khong tim thay User ID)...")
            username = self.ig.test_login()
            if username:
                self.ig_username = username
                self.ig.save_session_to_file(filename=self.session_file_path(username))
                self.ig_logged_in = True
                print(f"{Fore.GREEN}✅ Da nap thanh cong Manual Cookies cho user: {username}")
                return True
            else:
                print(f"{Fore.RED}❌ Cookie IG trong cookies.json khong hop le.")
                return False

        except Exception as e:
            print(f"{Fore.RED}❌ Loi khi doc manual cookie: {e}")
            return False

    def load_session_from_browser(self):
        print(f"{Fore.CYAN}🔄 Dang thu lay cookie tu trinh duyet (Edge)...")
        try:
            # Thu lay tu Edge
            cookies = browser_cookie3.edge(domain_name="instagram.com")
            self.ig.context._session.cookies.update(cookies)
            self._apply_instagram_browser_session(self.ig.context._session)
            
            # Kiem tra xem cookie co hieu luc khong (da login chua)
            username = self.ig.test_login()
            if username:
                self.ig_username = username
                self.ig.save_session_to_file(filename=self.session_file_path(username))
                self.ig_logged_in = True
                print(f"{Fore.GREEN}✅ Da muon cookie tu Edge cho {username} va luu Session.")
                return True
            else:
                print(f"{Fore.YELLOW}⚠️  Tim thay cookie Edge nhung hinh nhu chua dang nhap hoac cookie da het han.")
        except Exception as e:
             print(f"{Fore.YELLOW}⚠️  Khong lay duoc cookie tu Edge: {e}")
             
        return False

    def get_ig_session(self):
        """Đảm bảo đã đăng nhập IG, ưu tiên session lưu và cookie browser."""
        if self.ig.context.is_logged_in:
            self.ig_logged_in = True
            return True

        # 1. Thu Load Manual Cookie truoc (vi nguoi dung moi cung cap no)
        if self.load_session_from_manual_file():
            return True

        if not (self.ig_username and self.ig_password):
            saved = self.load_credentials()
            if saved:
                self.ig_username, self.ig_password = saved

        if self.ig_username:
            try:
                self.ig.load_session_from_file(self.ig_username, filename=self.session_file_path(self.ig_username))
                self.ig_logged_in = True
                print(f"{Fore.GREEN}✅ Da nap Session cua {self.ig_username} tu folder sessions.")
                return True
            except FileNotFoundError:
                pass
            except Exception:
                pass

        if self.load_session_from_browser():
            return True

        if not self.ig_username:
            self.ig_username = input(f"{Fore.WHITE}👉 Nhap Username IG (se luu txt): ").strip()
        if not self.ig_password:
            self.ig_password = input(f"{Fore.WHITE}🔑 Nhap Password IG (se luu txt, hien chu): ").strip()

        if not (self.ig_username and self.ig_password):
            print(f"{Fore.RED}❌ Thieu username hoac password IG.")
            return False

        print(f"{Fore.CYAN}👉 Dang dang nhap cho: {self.ig_username}")
        try:
            self.ig.login(self.ig_username, self.ig_password)
            self.ig.save_session_to_file(filename=self.session_file_path(self.ig_username))
            self.save_credentials(self.ig_username, self.ig_password)
            self.ig_logged_in = True
            print(f"{Fore.GREEN}✅ Dang nhap thanh cong va da luu Session!")
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ Loi dang nhap: {e}")
            return False

    def _video_extensions(self):
        return {".mp4", ".mov", ".mkv", ".webm", ".m4v"}

    def _video_format(self):
        """Tai video kem am thanh (merge bestvideo + bestaudio)."""
        return 'bestvideo*+bestaudio/best'

    def _get_ffmpeg_exe(self):
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    def _handle_ydl_progress(self, d, progress_callback):
        """Helper to handle yt-dlp progress hooks via callback."""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '').strip()
            speed = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            info = d.get('info_dict') or {}
            fname = os.path.basename(d.get('filename') or info.get('_filename') or info.get('filepath') or '')
            if len(fname) > 45:
                fname = fname[:44] + '…'
            msg = f"{percent} | {speed} | ETA: {eta}"
            if fname:
                msg = f"{msg} | {fname}"
            print(f"{Fore.YELLOW}📥 {msg}", end='\r')
            if progress_callback:
                progress_callback(percent, msg)
        elif d['status'] == 'finished':
            msg = "Đang xử lý file..."
            print(f"\n{Fore.GREEN}✅ {msg}")
            if progress_callback:
                progress_callback("100%", msg)

    def _create_temp_cookie_file(self, cookie_string, domain=".tiktok.com"):
        """Creates a temporary Netscape cookie file from a cookie string."""
        if not cookie_string: return None
        
        try:
            temp_file = os.path.join(self.data_dir, "temp_cookies.txt")
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by MasterDownloader\n")
                
                parts = cookie_string.split(';')
                for part in parts:
                    if '=' not in part: continue
                    key, val = part.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    # DOMAIN FLAG PATH SECURE EXPIRY NAME VALUE
                    f.write(f"{domain}\tTRUE\t/\tFALSE\t2147483647\t{key}\t{val}\n")
            return temp_file
        except:
            return None

    def download_tiktok(self, url, output_folder=None, progress_callback=None):
        """Xử lý tải TikTok (Video/Photo)"""
        # Giữ nguyên tham số URL vì Story có thể cần tham số để định danh chính xác
        # url = url.split('?')[0].strip() 
        url = self._resolve_tiktok_short_url(url.strip())
        kind = self._tiktok_url_kind(url)
        if kind not in ("video", "profile"):
            # yt-dlp khong tai duoc anh cua bai /photo/ va khong liet ke story
            return self.download_tiktok_gallerydl(url, kind, output_folder=output_folder, progress_callback=progress_callback)

        candidate_urls = [url]

        username = self._extract_tiktok_account_from_url(url)
        if not username:
            username = self._extract_ydl_account(url, "tiktok")
        
        # Tao thu muc rieng cho user (uu tien lay tu history neu co)
        if output_folder:
             folder = output_folder
        else:
             default_folder = os.path.join(self.download_root, username)
             folder = self.resolve_folder("tiktok", username, default_folder)
        os.makedirs(folder, exist_ok=True)
            
        safe_name = self._sanitize_name(username, "tiktok")
        archive = self._archive_path(folder, "tiktok", safe_name, "ydl")
        self._merge_archive_once(os.path.join(self.archive_dir, f"tiktok_{safe_name}.txt"), archive)
        
        ydl_opts_base = {
            'format': self._video_format(),
            'outtmpl': os.path.join(folder, '%(upload_date)s - %(title|No Title).100s [%(id)s] - %(playlist_index)s.%(ext)s'),
            'download_archive': archive,
            'ignoreerrors': True,
            'writethumbnails': True,
            'postprocessors': [{
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'jpg',
            }],
            'quiet': False,
            'no_warnings': True,
            'force_ipv4': True, # Fix loi 403 CDN TikTok
            'sleep_interval': 5, # Doi 5s giua cac lan tai video
            'max_sleep_interval': 15, # Random toi da 15s
            'sleep_interval_requests': 2, # Doi 2s giua cac request API (tranh 429 khi lay list video)
            # Setup User-Agent mac dinh cua yt-dlp thuong tot hon hardcode
            # 'http_headers': {
            #     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            # },
            # Thanh tien trinh don gian cho TikTok
            'progress_hooks': [
                lambda d: self._handle_ydl_progress(d, progress_callback)
            ],
        }
        if kind == "profile":
            # yt-dlp tai bai anh thanh file m4a chi co nhac; bai anh de gallery-dl tai
            ydl_opts_base['match_filter'] = self._skip_tiktok_photo_post

        print(f"{Fore.CYAN}🚀 Dang quet TikTok cua: {username}")
        if progress_callback: progress_callback("0%", "Đang lấy thông tin...")

        manual_cookie = self.get_manual_cookie("tiktok")
        
        # Chien luoc: 1. Manual Cookie File (Uu tien so 1) -> 2. Browser -> 3. No Cookie
        strategies = []
        
        if manual_cookie:
            # Create temp netscape cookie file
            temp_cookie_path = self._create_temp_cookie_file(manual_cookie)
            if temp_cookie_path:
                strategies.append(("Manual Cookie", {'cookiefile': temp_cookie_path}))
            
        strategies.append(("Browser Cookies", {'cookiesfrombrowser': ('edge',)}))
        strategies.append(("No Cookies", {}))

        for label, extra_opts in strategies:
            opts = ydl_opts_base.copy()
            opts.update(extra_opts)
            
            try:
                if label == "Manual Cookie":
                    print(f"{Fore.CYAN}🍪 Dang dung Manual Cookie tu settings...")
                elif label == "Browser Cookies":
                    # Kiem tra xem co manual cookie khong, neu co ma loi thi moi qua day, in log cho ro
                    print(f"{Fore.CYAN}ℹ️  Dang thu lay cookie tu Edge...")
                
                with self._prepare_yt_dlp(opts, f"TikTok {username}") as ydl:
                    ydl.download(candidate_urls)
                
                # Neu chay OK ma khong loi thi thoat vong lap chien luoc
                break 

            except Exception as e:
                err_msg = str(e)
                # Check loi permission (do mo trinh duyet) hoac loi load cookie
                is_cookie_error = type(e).__name__ == "CookieLoadError" or "Permission denied" in err_msg or "Could not copy" in err_msg
                
                if is_cookie_error:
                    if label == "Browser Cookies":
                        print(f"{Fore.YELLOW}⚠️  Khong doc duoc cookie Edge (do dang mo). Bo qua.")
                    else:
                         print(f"{Fore.RED}❌ Loi cookie: {e}")
                    continue 

                # Check loi 429
                if "429" in err_msg or "Too Many Requests" in err_msg:
                    print(f"{Fore.RED}❌ Bi TikTok chan (429) o che do {label}.")
                    if label == "Manual Cookie":
                         print(f"{Fore.YELLOW}👉 Cookie thu cong co ve da het han hoac bi chan.")
                    continue

                # Cac loi khac thi raise luon
                print(f"{Fore.RED}❌ Loi TikTok: {e}")
                raise e

        if kind == "profile":
            self._download_tiktok_profile_extras(url, folder, progress_callback)

    @staticmethod
    def _skip_tiktok_photo_post(info, incomplete=False):
        formats = info.get("formats")
        if not incomplete and formats and all(f.get("vcodec") == "none" for f in formats):
            return "Bai anh (gallery-dl se tai)"
        return None

    def _download_tiktok_profile_extras(self, url, folder, progress_callback=None):
        """Trang ca nhan: sau video (yt-dlp) tai them bai anh va story qua gallery-dl."""
        base = url.split("?")[0].split("#")[0].rstrip("/")
        notes, errors = [], []
        for kind, part_url in (("photos", base + "/posts"), ("stories", base + "/stories")):
            try:
                self.download_tiktok_gallerydl(part_url, kind, output_folder=folder, progress_callback=progress_callback)
            except RuntimeError as e:
                # Trang khong co bai anh / story dang hien thi la binh thuong, khong phai loi
                (notes if str(e).startswith(("Không có story", "Không có bài ảnh")) else errors).append(str(e))
        if errors:
            raise RuntimeError("Video đã tải; " + " | ".join(errors))
        msg = "Đã tải xong video, bài ảnh và story của trang cá nhân."
        if notes:
            msg = "Đã tải xong trang cá nhân. " + " ".join(notes)
        print(f"{Fore.GREEN}{msg}")
        if progress_callback:
            progress_callback("100%", msg)

    def _gallerydl_cmd(self):
        # Ban exe: sys.executable la chinh app, App.py chuyen tiep --gallery-dl sang gallery_dl
        cmd = [sys.executable, "--gallery-dl"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "gallery_dl"]
        # yt-dlp ben trong gallery-dl chi tim ffmpeg tren PATH (Windows thuong khong co):
        # khong ghep duoc video DASH + audio -> video mat tieng. Dua ffmpeg cua app vao.
        ffmpeg = self._get_ffmpeg_exe()
        if ffmpeg:
            for scope in ("downloader", "extractor"):
                cmd += ["-o", f"{scope}.ytdl.raw-options.ffmpeg_location={ffmpeg}"]
        return cmd

    def _run_gallerydl(self, cmd, progress_callback=None):
        """Chay gallery-dl, in log ra console/progress. Tra ve (exit code, cac dong output)."""
        process = subprocess.Popen(
            cmd,
            cwd=self.base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        lines = []
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            if not line:
                continue
            lines.append(line)
            print(line)
            if progress_callback:
                progress_callback("Running", line[-160:])
        return process.wait(), lines

    def download_tiktok_gallerydl(self, url, kind, output_folder=None, progress_callback=None):
        """TikTok bai anh (/photo/), story le va story cua trang ca nhan, qua gallery-dl."""
        username = self._extract_tiktok_account_from_url(url) or "tiktok"
        if output_folder:
            folder = output_folder
        else:
            default_folder = os.path.join(self.download_root, username)
            folder = self.resolve_folder("tiktok", username, default_folder)
        os.makedirs(folder, exist_ok=True)

        safe_name = self._sanitize_name(username, "tiktok")
        archive_path = os.path.join(folder, f".masterdownloader_tiktok_gallerydl_{safe_name}.sqlite3")
        manual_cookie = self.get_manual_cookie("tiktok")
        cookie_file = self._create_temp_cookie_file(manual_cookie) if manual_cookie else None

        cmd = [
            *self._gallerydl_cmd(),
            "--config-ignore",
            "--no-input",
            "--no-colors",
            "--directory", folder,
            "--download-archive", archive_path,
            "--sleep", "1-3",
            "--sleep-request", "2-5",
            "--retries", "3",
            "--http-timeout", "45",
        ]
        if kind == "photos":
            # Danh sach bai cua trang ca nhan: chi lay bai anh (video da tai bang yt-dlp)
            cmd += ["-o", "extractor.tiktok.videos=false"]
        if kind in ("story", "stories"):
            cmd += ["-o", "extractor.tiktok.filename=STORY - {id}{num:?_//>02} {title[b:150]}{file_id:? [/]/}.{extension}"]
        if cookie_file:
            cmd += ["--cookies", cookie_file]

        label = {"photo": "bài ảnh", "photos": "bài ảnh của trang cá nhân", "story": "story", "stories": "story của trang cá nhân"}.get(kind, kind)
        print(f"{Fore.CYAN}🚀 TikTok {label} cua {username} (gallery-dl)")
        if progress_callback:
            progress_callback("0%", f"Đang tải TikTok {label}...")

        code, lines = self._run_gallerydl(cmd + [self._tiktok_post_url(url)], progress_callback)

        # Sau khi goi API danh sach story, TikTok tra 403 cho trang tung bai trong cung phien;
        # chay lai cac link do trong tien trinh moi thi tai duoc.
        retry_urls, other_errors = [], []
        for line in lines:
            # URL bai viet o dau dong; URL sau "for '...'" la response.url (co the da redirect)
            m = re.search(r"(https?://\S+): Failed to extract post \(HttpError: '403", line)
            if m:
                if m.group(1) not in retry_urls:
                    retry_urls.append(m.group(1))
            elif "][error]" in line:
                other_errors.append(line)
        if retry_urls:
            print(f"{Fore.YELLOW}⚠️  TikTok tra 403 cho {len(retry_urls)} bai, dang thu lai...")
            code, lines = self._run_gallerydl(cmd + retry_urls, progress_callback)
            if other_errors:
                # Loi ngoai nhom 403 khong duoc chay lai: van tinh la that bai
                code, lines = code or 1, lines + other_errors

        output = "\n".join(lines).lower()
        if code == 0 and "no results for" not in output:
            msg = f"Đã tải xong TikTok {label}."
            status = "100%"
        elif "could not extract any stories" in output or ("no results for" in output and kind == "stories" and not retry_urls):
            msg = "Không có story nào đang hiển thị (story chỉ tồn tại 24 giờ). Nếu tài khoản riêng tư, hãy lưu TikTok Cookie."
            status = "Error"
        elif retry_urls and "403" in output:
            msg = f"TikTok chặn (403) {len(retry_urls)} bài kể cả khi thử lại. Hãy đợi một lúc hoặc lưu TikTok Cookie rồi tải lại."
            status = "Error"
        elif kind == "photos" and ("failed to retrieve" in output or "could not extract any posts for this user" in output):
            # API danh sach loi, hoac trang dau tra rong (bi chan / trang chua co bai nao)
            msg = "TikTok không trả danh sách bài của trang (có thể đang chặn). Hãy đợi một lúc hoặc lưu TikTok Cookie rồi tải lại."
            status = "Error"
        elif kind == "photos" and code == 0 and "no results for" in output:
            # Danh sach co bai nhung videos=false loc het: trang chi co video
            msg = "Không có bài ảnh nào."
            status = "Error"
        elif code == 0 and "no results for" in output:
            msg = "Không tìm thấy nội dung ở link này (bài có thể đã bị xoá hoặc ở chế độ riêng tư)."
            status = "Error"
        elif "login" in output or "authorization" in output or "private" in output:
            msg = "TikTok yêu cầu đăng nhập. Hãy lưu TikTok Cookie của tài khoản xem được nội dung này."
            status = "Need Cookie"
        else:
            # Dong cuoi thuong la duong dan file vua tai; bao dong loi cuoi cung neu co
            detail = next((l for l in reversed(lines) if "][error]" in l), lines[-1] if lines else "")
            msg = f"gallery-dl lỗi exit code {code}: {detail} (tải lại link để thử lại phần lỗi)"
            status = "Error"
        print(f"{Fore.GREEN if status == '100%' else Fore.RED}{msg}")
        if progress_callback:
            progress_callback(status, msg)
        if status != "100%":
            # GUI chi danh dau "Lỗi" khi ham nem exception
            raise RuntimeError(msg)

    def download_instagram_with_ytdlp(self, url, target, output_folder=None, progress_callback=None):
        """Try yt-dlp first for Instagram to avoid Instaloader GraphQL profile lookups."""
        if output_folder:
            folder = output_folder
        else:
            default_folder = os.path.join(self.download_root, target or "instagram")
            folder = self.resolve_folder("instagram", target or "instagram", default_folder)
        os.makedirs(folder, exist_ok=True)

        safe_name = self._sanitize_name(target or "instagram", "instagram")
        archive = self._archive_path(folder, "instagram", safe_name, "ydl")
        self._merge_archive_once(os.path.join(self.archive_dir, f"instagram_ytdlp_{safe_name}.txt"), archive)
        manual_cookie = self.get_manual_cookie("instagram")
        temp_cookie_path = self._create_temp_cookie_file(manual_cookie, domain=".instagram.com") if manual_cookie else None
        url_kind = self._instagram_url_kind(url)

        ydl_opts_base = {
            'format': self._video_format(),
            'outtmpl': os.path.join(folder, '%(uploader|instagram)s - %(upload_date>%Y-%m-%d|unknown)s - %(title|No Title).120s [%(id)s].%(ext)s'),
            'download_archive': archive,
            'ignoreerrors': True,
            'writethumbnails': True,
            'quiet': False,
            'no_warnings': False,
            'playlistend': self.ig_max_posts or 20,
            'sleep_interval': 30,
            'max_sleep_interval': 75,
            'sleep_interval_requests': 12,
            'extractor_retries': 1,
            'retries': 3,
            'fragment_retries': 3,
            'http_headers': self._instagram_browser_headers(manual_cookie, referer=f"https://www.instagram.com/{target}/" if target else "https://www.instagram.com/"),
            'progress_hooks': [
                lambda d: self._handle_ydl_progress(d, progress_callback)
            ],
        }

        strategies = []
        if temp_cookie_path:
            strategies.append(("Manual Cookie", {'cookiefile': temp_cookie_path}))
        if self._edge_cookie_db_exists():
            strategies.append(("Browser Cookies", {'cookiesfrombrowser': ('edge',)}))
        elif not temp_cookie_path:
            print(f"{Fore.YELLOW}⚠️  WSL khong thay cookie Edge Linux. Hay luu Instagram Cookie trong Settings de tai profile/private.")

        if url_kind != "profile":
            strategies.append(("No Cookies", {}))
        elif not strategies:
            print(f"{Fore.YELLOW}⚠️  Link Instagram profile can cookie dang nhap. Bo qua No Cookies vi IG se tra ve nhu profile khong ton tai.")
            return False

        for label, extra_opts in strategies:
            opts = ydl_opts_base.copy()
            opts.update(extra_opts)
            try:
                print(f"{Fore.CYAN}📸 IG yt-dlp engine: {label}")
                if progress_callback:
                    progress_callback("0%", f"Instagram yt-dlp: {label}")
                with self._prepare_yt_dlp(opts, f"Instagram {target}") as ydl:
                    code = ydl.download([url])
                if code == 0:
                    print(f"{Fore.GREEN}✅ IG yt-dlp engine hoan tat.")
                    return True
            except Exception as e:
                if self._is_ig_block_error(e):
                    print(f"{Fore.YELLOW}⚠️  IG yt-dlp bi chan voi {label}: {e}")
                    continue
                err_msg = str(e)
                is_cookie_error = type(e).__name__ == "CookieLoadError" or "Permission denied" in err_msg or "Could not copy" in err_msg
                if is_cookie_error:
                    print(f"{Fore.YELLOW}⚠️  Khong doc duoc cookie IG voi {label}: {e}")
                    continue
                print(f"{Fore.YELLOW}⚠️  IG yt-dlp fail voi {label}: {e}")
                continue

        return False

    def _write_gallerydl_cookie_file(self, cookie_string):
        return self._create_temp_cookie_file(cookie_string, domain=".instagram.com")

    def download_instagram_gallerydl(self, url, output_folder=None, progress_callback=None):
        """Instagram v2 engine: use gallery-dl as the sole downloader."""
        url = url.strip().split("?")[0].strip("/")
        target = url.split("/")[-1] or "instagram"
        url_kind = self._instagram_url_kind(url)

        if output_folder:
            folder = output_folder
        else:
            default_folder = os.path.join(self.download_root, target)
            folder = self.resolve_folder("instagram", target, default_folder)
        os.makedirs(folder, exist_ok=True)

        safe_target = self._sanitize_name(target, "instagram")
        archive_path = os.path.join(folder, f".masterdownloader_instagram_gallerydl_{safe_target}.sqlite3")

        manual_cookie = self.get_manual_cookie("instagram")
        cookie_file = self._write_gallerydl_cookie_file(manual_cookie) if manual_cookie else None

        include_modes = {
            "profile": "posts,reels,tagged,stories,highlights",
            "story": "stories",
            "highlight": "highlights",
            "post": "posts",
        }.get(url_kind, "posts,reels,tagged,stories,highlights")
        if not cookie_file:
            print(f"{Fore.YELLOW}⚠️  Khong co Instagram Cookie. gallery-dl van se thu tai, nhung profile/private/stories co the bi han che.")

        cmd = [
            *self._gallerydl_cmd(),
            "--config-ignore",
            "--no-input",
            "--no-colors",
            "--directory", folder,
            "--download-archive", archive_path,
            "--sleep", f"{self.ig_sleep_range[0]}-{self.ig_sleep_range[1]}",
            "--sleep-request", "8-20",
            "--sleep-429", "300-900",
            "--retries", "3",
            "--http-timeout", "45",
            "--user-agent", self.ig.context.user_agent,
            "-o", "extractor.ytdl.module=yt_dlp",
            "-o", "extractor.ytdl.forward-cookies=true",
            "-o", "extractor.ytdl.raw-options.no_color=true",
            "-o", "extractor.ytdl.raw-options.quiet=false",
            "-o", "extractor.ytdl.format=bestvideo*+bestaudio/best",
            "-o", f"extractor.instagram.include={include_modes}",
        ]

        if self.ig_max_posts and url_kind == "profile":
            cmd.extend(["-o", f"extractor.instagram.max-posts={self.ig_max_posts}"])
        if cookie_file:
            cmd.extend(["--cookies", cookie_file])
        cmd.append(url)

        print(f"{Fore.CYAN}📸 IG v2 engine: gallery-dl")
        print(f"{Fore.CYAN}📜 History File: {archive_path}")
        if progress_callback:
            progress_callback("0%", "Instagram v2 gallery-dl đang tải...")

        code, lines = self._run_gallerydl(cmd, progress_callback)
        last_line = lines[-1] if lines else ""

        if code == 0:
            msg = "Instagram v2 gallery-dl hoàn tất."
            print(f"{Fore.GREEN}✅ {msg}")
            if progress_callback:
                progress_callback("100%", msg)
            return

        lowered = last_line.lower()
        if "429" in lowered or "too many requests" in lowered:
            self._start_ig_cooldown("gallery-dl 429")
            if progress_callback:
                progress_callback("Blocked", "Instagram 429 từ gallery-dl. Đã bật cooldown.")
            return
        if "login" in lowered or "cookies" in lowered or "private" in lowered or "forbidden" in lowered:
            msg = "gallery-dl không đọc được IG bằng cookie hiện tại. Hãy copy lại Instagram Cookie từ tài khoản đang xem được profile."
            print(f"{Fore.RED}❌ {msg}")
            if progress_callback:
                progress_callback("Need Cookie", msg)
            return

        msg = f"gallery-dl lỗi exit code {code}: {last_line}"
        print(f"{Fore.RED}❌ {msg}")
        if progress_callback:
            progress_callback("Error", msg)

    def download_instagram(self, url, output_folder=None, progress_callback=None):
        """Xử lý tải Instagram Profile/Post"""
        return self.download_instagram_gallerydl(url, output_folder=output_folder, progress_callback=progress_callback)

        remaining = self._ig_cooldown_remaining()
        if remaining > 0:
            msg = f"Instagram đang cooldown do bị 401/403. Thử lại sau khoảng {remaining // 60} phút."
            print(f"{Fore.YELLOW}⏳ {msg}")
            if progress_callback:
                progress_callback("Cooldown", msg)
            return

        # --- BẢO VỆ RATE LIMIT: CHỈ CHẠY TUẦN TỰ ---
        if self.ig_lock.locked():
            print(f"{Fore.YELLOW}⏳ Một tiến trình Instagram khác đang chạy. Đang đợi lượt... {url}")
            if progress_callback: progress_callback("Wait", "Đang đợi tiến trình IG khác...")

        with self.ig_lock:
            url = url.split('?')[0].strip('/')
            target = url.split('/')[-1]
            url_kind = self._instagram_url_kind(url)

            if url_kind == "profile":
                if not self._has_usable_instagram_cookie():
                    msg = (
                        "Profile Instagram can cookie dang nhap hop le, nhat la profile private/chi follower moi xem duoc. "
                        "Hay vao Settings -> Instagram Cookie, dan full Cookie header tu trinh duyet dang login."
                    )
                    print(f"{Fore.RED}❌ {msg}")
                    if progress_callback:
                        progress_callback("Need Cookie", msg)
                    return

                profile_info, profile_error = self._instagram_web_profile_info(target)
                if profile_error in {"http_401", "http_403", "http_429"}:
                    print(f"{Fore.YELLOW}⚠️  IG web precheck bi {profile_error}; bo qua precheck va thu truc tiep bang Instaloader.")
                    if progress_callback:
                        progress_callback("Precheck Skip", "Bỏ qua precheck IG, thử trực tiếp bằng Instaloader.")
                if profile_error == "not_found":
                    msg = f"Instagram khong thay profile {target}. Kiem tra dung username/link."
                    print(f"{Fore.RED}❌ {msg}")
                    if progress_callback:
                        progress_callback("Not Found", msg)
                    return
                if profile_info:
                    is_private = bool(profile_info.get("is_private"))
                    follows_viewer = bool(profile_info.get("followed_by_viewer") or profile_info.get("follows_viewer"))
                    if is_private and not follows_viewer:
                        msg = f"Profile {target} la private va cookie hien tai chua follow/khong co quyen xem."
                        print(f"{Fore.RED}❌ {msg}")
                        if progress_callback:
                            progress_callback("Private", msg)
                        return
                elif profile_error:
                    print(f"{Fore.YELLOW}⚠️  Khong kiem tra duoc profile qua web API: {profile_error}. Van thu bang Instaloader.")

            print(f"{Fore.CYAN}📸 IG engine: Instaloader + browser cookie/header")
            
            if url_kind == "profile" and not self.get_ig_session():
                msg = "Khong co session IG hop le nen khong quet profile/private."
                print(f"{Fore.RED}❌ {msg}")
                if progress_callback:
                    progress_callback("Need Cookie", msg)
                return

            if url_kind == "post":
                try:
                    post = instaloader.Post.from_shortcode(self.ig.context, target)
                    target = post.owner_username
                except Exception as e:
                    if self._is_ig_block_error(e):
                        self._start_ig_cooldown(e)
                    print(f"{Fore.RED}❌ Khong tim thay bai viet: {e}")
                    return

            print(f"{Fore.MAGENTA}📸 Dang quet Instagram cua: {target}")
            
            ig_client = self._create_isolated_ig_client()
            ig_logged_in = ig_client.context.is_logged_in or self.ig_logged_in
            profile = None
            try:
                profile = instaloader.Profile.from_username(ig_client.context, target)
            except Exception as e:
                if self._is_ig_invalid_request_error(e):
                    print(f"{Fore.RED}❌ IG tra ve 400 invalid request khi doc profile {target}. Cookie co the da het han/khong khop trinh duyet, hoac endpoint GraphQL hien tai khong chap nhan session nay. Khong cooldown vi day khong phai 429.")
                    if progress_callback:
                        progress_callback("Invalid Cookie", "IG trả 400 invalid request. Cập nhật lại Instagram Cookie rồi thử lại.")
                    return
                if self._is_ig_block_error(e):
                    self._start_ig_cooldown(e)
                    if progress_callback:
                        progress_callback("Blocked", "Instagram bị 401/403. Đã bật cooldown, không retry liên tục.")
                    return
                if "does not exist" in str(e).lower() and url_kind == "profile":
                    print(f"{Fore.RED}❌ Instagram khong cho doc profile {target}. Neu ban xem duoc trong trinh duyet, cookie trong Settings chua dung/het han hoac tai khoan cookie khong follow profile private nay.")
                    if progress_callback:
                        progress_callback("Need Cookie", "Cookie IG chua co quyen xem profile nay.")
                    return
                raise

            if profile is None:
                return

            # Thiet lap thu muc luu cho IG (dung chung theo username, uu tien history)
            if output_folder:
                resolved_folder = output_folder
            else:
                default_folder = os.path.join(self.download_root, target)
                resolved_folder = self.resolve_folder("instagram", target, default_folder)
            os.makedirs(resolved_folder, exist_ok=True)
            ig_client.dirname_pattern = resolved_folder

            safe_target = self._sanitize_name(target, "instagram")
            archive_path = self._archive_path(resolved_folder, "instagram", safe_target, "posts")
            self._merge_archive_once(os.path.join(self.archive_dir, f"instagram_{target}.txt"), archive_path)
            
            print(f"{Fore.CYAN}📜 History File: {archive_path}")
            
            # Touch file if not exists
            if not os.path.exists(archive_path):
                with open(archive_path, 'w', encoding='utf-8') as f:
                    pass

            downloaded_shortcodes = set()
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    downloaded_shortcodes = set(line.strip() for line in f if line.strip())
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️  Khong doc duoc history file: {e}")
            # ------------------------------------

            # --- TẢI STORY (Added Feature) ---
            if self.ig_download_stories:
                print(f"{Fore.MAGENTA}🎞️  Dang quet & tai Stories...")
                if progress_callback: progress_callback("Wait", "Đang quét Stories...")
                try:
                    # Lay stories cua user hien tai (can login)
                    if ig_logged_in:
                        stories = ig_client.get_stories(userids=[profile.userid])
                        has_story = False
                        for story in stories:
                            for item in story.get_items():
                                has_story = True
                                
                                # Check Metadata History (Story ID)
                                story_id = str(item.mediaid)
                                if story_id in downloaded_shortcodes:
                                    continue

                                # download_storyitem tra ve True neu tai moi
                                downloaded = ig_client.download_storyitem(item, target=target)

                                # Luu vao history
                                if downloaded:
                                    print(f"{Fore.GREEN}   + Da tai story moi: {item.date_local}")
                                    try:
                                        with open(archive_path, 'a', encoding='utf-8') as f:
                                            f.write(f"{story_id}\n")
                                        downloaded_shortcodes.add(story_id)
                                    except: pass
                                    time.sleep(random.uniform(8, 20))
                                else:
                                    if story_id not in downloaded_shortcodes:
                                        try:
                                            with open(archive_path, 'a', encoding='utf-8') as f:
                                                f.write(f"{story_id}\n")
                                            downloaded_shortcodes.add(story_id)
                                        except: pass
                        
                        if not has_story:
                            print(f"{Fore.YELLOW}   ℹ️  Khong co story nao (hoac khong xem duoc).")
                    else:
                        print(f"{Fore.YELLOW}   ⚠️  Chua login, bo qua quet Story.")

                except Exception as e:
                    if self._is_ig_block_error(e):
                        self._start_ig_cooldown(e)
                        return
                    print(f"{Fore.RED}   ❌ Khong the tai Story (co the do loi API hoac cookies): {e}")
            else:
                print(f"{Fore.YELLOW}🎞️  Bo qua Stories de giam nguy co IG 401/403.")

            # --- TẢI HIGHLIGHTS (Added Feature) ---
            if self.ig_download_highlights:
                print(f"{Fore.MAGENTA}🌟 Dang quet & tai Highlights...")
                try:
                    if ig_logged_in:
                        highlights = ig_client.get_highlights(user=profile)
                        has_highlight = False
                        for highlight in highlights:
                            print(f"{Fore.CYAN}   > Dang quet Highlight: {highlight.title}")
                            for item in highlight.get_items():
                                has_highlight = True
                                if ig_client.download_storyitem(item, target=target):
                                    print(f"{Fore.GREEN}     + Da tai item trong highlight '{highlight.title}': {item.date_local}")
                                    time.sleep(random.uniform(8, 20))
                        
                        if not has_highlight:
                            print(f"{Fore.YELLOW}   ℹ️  Khong co highlight nao.")
                    else:
                        print(f"{Fore.YELLOW}   ⚠️  Chua login, bo qua quet Highlights.")
                except Exception as e:
                    if self._is_ig_block_error(e):
                        self._start_ig_cooldown(e)
                        return
                    print(f"{Fore.RED}   ❌ Khong the tai Highlights: {e}")
            else:
                print(f"{Fore.YELLOW}🌟 Bo qua Highlights de giam nguy co IG 401/403.")

            # retry_on_401 = self.ig_retry_on_401  <-- Khong dung bien cuc bo nay nua, chuyen sang outer loop
            # wait_401_base = self.ig_wait_401_base

            # --- ROBUST LOOP: Bao ve ca qua trinh duyet iterator ---
            outer_retries = 1
            post_count = 0
            while outer_retries > 0:
                try:
                    posts_iter = profile.get_posts()
                    if self.ig_max_posts:
                        posts_iter = itertools.islice(posts_iter, self.ig_max_posts)

                    for post in posts_iter:
                        post_count += 1
                        
                        # --- CHECK HISTORY ---
                        if post.shortcode in downloaded_shortcodes:
                            msg = f"Đã tải {post.shortcode} (History)"
                            print(f"{Fore.YELLOW}🛡️  [Post {post_count}] {msg}           ")
                            if progress_callback: progress_callback("Skipped", msg)
                            break
                        # ---------------------

                        # Hien thi tien trinh (overwrite line)
                        msg_check = f"Đang kiểm tra: {post.shortcode}..."
                        print(f"{Fore.CYAN}⏳ [Post {post_count}] {msg_check}", end='\r')
                        if progress_callback: progress_callback(f"Post {post_count}", msg_check)
                        
                        try:
                            # download_post trả về True nếu tải mới, False nếu bài đã tồn tại
                            downloaded = ig_client.download_post(post, target=target)
                            
                            # Luu vao history NGAY LAP TUC (append mode)
                            try:
                                with open(archive_path, 'a', encoding='utf-8') as f:
                                    f.write(f"{post.shortcode}\n")
                                downloaded_shortcodes.add(post.shortcode)
                            except Exception as e:
                                print(f"{Fore.RED}❌ Loi ghi history: {e}")

                            if downloaded:
                                msg_done = f"Đã tải xong: {post.shortcode}"
                                print(f"{Fore.GREEN}✅ [Post {post_count}] {msg_done}     ")
                                if progress_callback: progress_callback(f"Post {post_count}", "Tải xong")
                                wait_time = random.uniform(*self.ig_sleep_range)
                                time.sleep(wait_time)
                            else:
                                print(f"{Fore.YELLOW}🛡️  [Post {post_count}] Bai cu tren dia ({post.date_local}). Dung quet.             ")
                                # Neu gap bai cu thi coi nhu xong viec cho profile nay (hoac co the bo break neu muon quet het)
                                break 
                        except Exception as inner_e:
                            print(f"\n{Fore.RED}❌ [Post {post_count}] Loi tai: {inner_e}")
                            if self._is_ig_block_error(inner_e):
                                raise inner_e
                            continue
                    
                    # Neu vong for chay xong (hoac break do gap bai cu) -> Thanh cong
                    break

                except Exception as e:
                    # Bat loi gay ra boi next(posts_iter) hoac raise 401 tu ben trong
                    msg = str(e)
                    if self._is_ig_invalid_request_error(e):
                        print(f"{Fore.RED}❌ IG tra ve 400 invalid request khi lay danh sach post. Hay copy lai Instagram Cookie moi tu dung tai khoan dang xem duoc profile nay.")
                        if progress_callback:
                            progress_callback("Invalid Cookie", "Cookie/session IG không được GraphQL chấp nhận.")
                        break
                    if self._is_ig_block_error(e):
                        self._start_ig_cooldown(e)
                        if progress_callback:
                            progress_callback("Blocked", "Instagram bị 401/403/429. Đã dừng IG để tránh bị chặn nặng hơn.")
                        break

                    print(f"{Fore.RED}❌ Loi nghiem trong hoac het luot thu: {e}")
                    break

    def download_facebook(self, url, output_folder=None, progress_callback=None):
        """Xử lý tải Facebook video/post"""
        url = url.strip()
        username = self._extract_facebook_account_from_url(url)
        if not username:
            username = self._extract_ydl_account(url, "facebook")

        # Chi ho tro link video/watch/reel. Link profile se bi FB chan (yt_dlp khong lay duoc).
        if not ("/videos/" in url or "/watch" in url or "/reel/" in url or "fb.watch/" in url):
            print(f"{Fore.RED}❌ Link Facebook nay khong phai video/post. Hay dan link /videos/, /watch?v=... hoac /reel/.")
            return

        if output_folder:
             folder = output_folder
        else:
             default_folder = os.path.join(self.download_root, username)
             folder = self.resolve_folder("facebook", username, default_folder)
        os.makedirs(folder, exist_ok=True)

        safe_name = self._sanitize_name(username, "facebook")
        archive = self._archive_path(folder, "facebook", safe_name, "ydl")
        self._merge_archive_once(os.path.join(self.archive_dir, f"facebook_{safe_name}.txt"), archive)

        ydl_opts = {
            'format': self._video_format(),
            'outtmpl': os.path.join(folder, '%(upload_date)s - %(title|No Title).150s [%(id)s].%(ext)s'),
            'download_archive': archive,
            'ignoreerrors': True,
            'writethumbnails': True,
            'quiet': False,
            'no_warnings': True,
            'progress_hooks': [
                lambda d: self._handle_ydl_progress(d, progress_callback)
            ],
        }

        print(f"{Fore.CYAN}🚀 Dang tai Facebook cua: {username}")
        if progress_callback: progress_callback("0%", "Đang lấy thông tin...")

        strategies = [("Browser Cookies", {'cookiesfrombrowser': ('edge',)}), ("No Cookies", {})]
        last_error = None
        for label, extra_opts in strategies:
            opts = ydl_opts.copy()
            opts.update(extra_opts)
            try:
                if label == "Browser Cookies":
                    print(f"{Fore.CYAN}ℹ️  Dang thu lay cookie Facebook tu Edge...")
                with self._prepare_yt_dlp(opts, f"Facebook {username}") as ydl:
                    ydl.download([url])
                return
            except Exception as e:
                last_error = e
                err_msg = str(e)
                is_cookie_error = type(e).__name__ == "CookieLoadError" or "Permission denied" in err_msg or "Could not copy" in err_msg
                if is_cookie_error:
                    print(f"{Fore.YELLOW}⚠️  Khong doc duoc cookie Edge cho Facebook. Thu tiep khong cookie...")
                    continue
                if "login" in err_msg.lower() or "private" in err_msg.lower():
                    print(f"{Fore.YELLOW}⚠️  Facebook yeu cau dang nhap/cookie hop le cho link nay.")
                    continue
                print(f"{Fore.RED}❌ Loi Facebook voi {label}: {e}")
                continue

        if last_error:
            raise last_error

    def _media_extensions(self):
        """Anh + video duoc tinh khi quet trung lap."""
        return self._video_extensions() | {
            '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.heic', '.tiff', '.avif'
        }

    def _quick_signature(self, path, head=65536):
        """Chu ky nhanh: doc 64KB dau de loc so bo truoc khi hash full."""
        try:
            with open(path, 'rb') as f:
                return hashlib.blake2b(f.read(head), digest_size=16).hexdigest()
        except OSError:
            return None

    def _load_deleted_md5(self):
        """Nap so MD5 cac file da xoa: tra ve dict size(int) -> set(md5 hex)."""
        registry = {}
        path = getattr(self, "deleted_md5_file", None)
        if not path or not os.path.exists(path):
            return registry
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) != 2:
                        continue
                    md5, size_str = parts[0].strip(), parts[1].strip()
                    try:
                        size = int(size_str)
                    except ValueError:
                        continue
                    if md5:
                        registry.setdefault(size, set()).add(md5)
        except OSError as e:
            print(f"{Fore.YELLOW}⚠️  Khong doc duoc so MD5 {path!r}: {e}")
        return registry

    def _record_deleted_md5(self, md5, size):
        """Ghi (md5,size) vao so neu chua co. Idempotent."""
        if not md5:
            return
        known = self._deleted_md5.setdefault(size, set())
        if md5 in known:
            return
        known.add(md5)
        try:
            with open(self.deleted_md5_file, "a", encoding="utf-8") as f:
                f.write(f"{md5},{size}\n")
        except OSError as e:
            print(f"{Fore.YELLOW}⚠️  Khong ghi duoc so MD5 {self.deleted_md5_file!r}: {e}")

    def _file_hash(self, path, chunk=1 << 20):
        """MD5 toan bo noi dung file (doc theo block 1MB)."""
        h = hashlib.md5()
        try:
            with open(path, 'rb') as f:
                for block in iter(lambda: f.read(chunk), b''):
                    h.update(block)
        except OSError:
            return None
        return h.hexdigest()

    def find_duplicates(self, directory=None, status_callback=None):
        """
        Tim file (anh + video) trung lap theo NOI DUNG (MD5), khong nham lan.
        Toi uu: gom theo kich thuoc -> chu ky 64KB -> hash full, chi hash khi can.
        :return: list cac nhom trung, moi nhom la list duong dan da sort theo mtime
                 (phan tu [0] la file cu nhat = ban nen giu lai).
        """
        if directory is None:
            directory = self.base_dir

        def log(msg):
            print(msg)
            if status_callback:
                status_callback(msg)

        log(f"{Fore.CYAN}🔍 Bắt đầu quét file trùng (ảnh + video) trong: {directory}...")

        media_exts = self._media_extensions()

        # Buoc 1: gom theo kich thuoc (file unique size khong the trung)
        size_map = {}
        resurrected = []
        scanned = 0
        for root, _, files in os.walk(directory):
            if "sessions" in root or "__pycache__" in root or ".git" in root or "archives" in root:
                continue
            for filename in files:
                if os.path.splitext(filename)[1].lower() not in media_exts:
                    continue
                path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size == 0:
                    continue
                scanned += 1
                size_map.setdefault(size, []).append(path)
                # File "quay lai": size co trong so -> tinh MD5 -> doi chieu
                if size in self._deleted_md5:
                    fh = self._file_hash(path)
                    if fh is not None and fh in self._deleted_md5[size]:
                        resurrected.append(path)

        log(f"{Fore.CYAN}📂 Đã quét {scanned} file media. Đang đối chiếu nội dung...")

        # Buoc 2 + 3: trong moi nhom cung size -> loc theo chu ky 64KB -> hash full
        groups = []
        for size, paths in size_map.items():
            if len(paths) < 2:
                continue
            quick_map = {}
            for p in paths:
                sig = self._quick_signature(p)
                if sig is not None:
                    quick_map.setdefault(sig, []).append(p)
            for sig, candidates in quick_map.items():
                if len(candidates) < 2:
                    continue
                full_map = {}
                for p in candidates:
                    fh = self._file_hash(p)
                    if fh is not None:
                        full_map.setdefault(fh, []).append(p)
                for fh, dupes in full_map.items():
                    if len(dupes) > 1:
                        dupes.sort(key=lambda x: (os.path.getmtime(x), x))
                        groups.append(dupes)
                        log(f"{Fore.YELLOW}⚠️  Nhóm trùng ({len(dupes)} bản): {os.path.basename(dupes[0])}")

        total_dupes = sum(len(g) - 1 for g in groups)
        # Tranh liet ke trung: bo resurrected da xuat hien trong groups
        in_groups = {p for g in groups for p in g}
        resurrected = [p for p in resurrected if p not in in_groups]
        if total_dupes == 0 and not resurrected:
            log(f"{Fore.GREEN}✨ Không tìm thấy file trùng nào.")
        else:
            log(f"{Fore.GREEN}✅ Tìm thấy {len(groups)} nhóm, {total_dupes} bản sao "
                f"+ {len(resurrected)} file đã từng xoá.")
        return groups, resurrected

    def delete_paths(self, paths, status_callback=None):
        """Xoa danh sach file, ghi MD5 vao so de chan tai lai. Tra ve (so_file_da_xoa, tong_byte)."""
        deleted = 0
        freed = 0
        for path in paths:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            # Ghi so MD5 truoc khi xoa (file con ton tai de tinh hash)
            md5 = self._file_hash(path)
            if md5 is not None and size > 0:
                self._record_deleted_md5(md5, size)
            try:
                os.remove(path)
                deleted += 1
                freed += size
                if status_callback:
                    status_callback(f"🗑️  Đã xóa: {os.path.basename(path)}")
            except Exception as e:
                if status_callback:
                    status_callback(f"❌ Lỗi xóa {os.path.basename(path)}: {e}")
        return deleted, freed

    def run(self):
        self.clear_screen()
        print(f"{Fore.GREEN}{'='*50}")
        print(f"{Fore.GREEN}   SIEU CONG CU TAI TIKTOK & INSTAGRAM (2026)")
        print(f"{Fore.GREEN}{'='*50}\n")
        try:
            print(f"{Fore.YELLOW}ℹ️  yt-dlp version: {yt_dlp.version.__version__}")
            print(f"{Fore.YELLOW}ℹ️  Instaloader version: {instaloader.__version__}")
        except Exception:
            pass

        while True:
            print(f"\n{Fore.WHITE}{'-'*50}")
            link = input(f"{Fore.CYAN}🔗 Dan link (TikTok/IG) hoac go 'exit' de thoat: ").strip()
            
            if link.lower() == 'exit':
                break
            
            if "tiktok.com" in link:
                self.download_tiktok(link)
            elif "facebook.com" in link:
                self.download_facebook(link)
            elif "instagram.com" in link:
                if not self.get_ig_session():
                    print(f"{Fore.RED}❌ Dang nhap IG that bai. Thu lai sau.")
                    continue

                self.download_instagram(link)
            else:
                print(f"{Fore.RED}❓ Link khong hop le bro oi!")
            
            print(f"\n{Fore.GREEN}✅ Xong! Tiep bai khac nao...")

if __name__ == "__main__":
    try:
        app = MasterDownloader()
        app.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 Bye bro!")
