"""
VK-бот: следит за разделами форума server 35 GROZNY
и пишет о просроченных жалобах во все беседы, где владелец написал «старт».

Команды:
  старт / стоп          — владелец беседы, админ, владелец бота
  /af  (или /аф)        — если раздел по умолчанию установлен — проверяет его,
                          иначе спросит раздел кнопками
  /settings (/настройки) — меню настроек (только админы/владельцы)
  /addadmin <id|@|реплай>   — владелец бота или /addowner-пользователь
  /addowner <id|@|реплай>   — только владелец бота (BOT_OWNER_ID)
  /removeadmin <id|@|реплай> — владелец бота или owner
  /removeowner <id|@|реплай> — только владелец бота
  /admins               — список владельцев и админов

Запуск:  python bot.py

При первом запуске бот сам поставит зависимости
(vk-api, beautifulsoup4, playwright) и Chromium для Playwright.
"""

# ======================= АВТОУСТАНОВКА ЗАВИСИМОСТЕЙ =======================
import importlib
import os as _os_bootstrap
import site as _site_bootstrap
import subprocess as _subprocess_bootstrap
import sys as _sys_bootstrap

_REQUIRED_PACKAGES = {
    "vk_api": "vk-api",
    "bs4": "beautifulsoup4",
    "playwright": "playwright",
}


def _refresh_sys_path() -> None:
    importlib.invalidate_caches()
    try:
        _site_bootstrap.main()
    except Exception:
        pass
    try:
        user_site = _site_bootstrap.getusersitepackages()
    except Exception:
        user_site = ""
    if user_site and user_site not in _sys_bootstrap.path:
        _sys_bootstrap.path.insert(0, user_site)


def _bootstrap_pip_packages() -> None:
    missing = []
    for mod, pkg in _REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return

    print(f"[bootstrap] Не хватает пакетов: {', '.join(missing)}. Устанавливаю...")

    try:
        _subprocess_bootstrap.check_call(
            [_sys_bootstrap.executable, "-m", "pip", "install",
             "--upgrade", "pip", "setuptools", "wheel"]
        )
    except Exception as e:
        print(f"[bootstrap] Не удалось обновить pip: {e}")

    for pkg in missing:
        print(f"[bootstrap] pip install {pkg}")
        try:
            _subprocess_bootstrap.check_call(
                [_sys_bootstrap.executable, "-m", "pip", "install", "--upgrade", pkg]
            )
        except _subprocess_bootstrap.CalledProcessError as e:
            print(f"[bootstrap] Обычная установка {pkg} не удалась ({e}), пробую --user")
            try:
                _subprocess_bootstrap.check_call(
                    [_sys_bootstrap.executable, "-m", "pip", "install",
                     "--user", "--upgrade", pkg]
                )
            except _subprocess_bootstrap.CalledProcessError as e2:
                print(f"[bootstrap] Не смог установить {pkg}: {e2}")
                _sys_bootstrap.exit(1)

    _refresh_sys_path()


def _chromium_binary_path() -> str | None:
    """Возвращает путь к реальному бинарнику Chromium, если он есть."""
    if _os_bootstrap.environ.get("PLAYWRIGHT_BROWSERS_PATH") == "0":
        # Явно указано использовать системный Chromium — не наша забота
        return "system"
    candidates = [
        _os_bootstrap.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "",
        _os_bootstrap.path.expanduser("~/.cache/ms-playwright"),
        _os_bootstrap.path.expanduser("~/Library/Caches/ms-playwright"),
        (
            _os_bootstrap.path.join(_os_bootstrap.environ["LOCALAPPDATA"], "ms-playwright")
            if _os_bootstrap.environ.get("LOCALAPPDATA") else ""
        ),
    ]
    rel_paths = (
        "chrome-linux/chrome",
        "chrome-linux64/chrome",
        "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
        "chrome-win/chrome.exe",
    )
    for d in candidates:
        if not d or not _os_bootstrap.path.isdir(d):
            continue
        try:
            for name in _os_bootstrap.listdir(d):
                if not name.startswith("chromium-"):
                    continue
                base = _os_bootstrap.path.join(d, name)
                for rel in rel_paths:
                    p = _os_bootstrap.path.join(base, rel)
                    if _os_bootstrap.path.isfile(p):
                        return p
        except Exception:
            pass
    return None


def _chromium_installed() -> bool:
    return _chromium_binary_path() is not None


def _install_chromium(force: bool = False) -> bool:
    """Запускает playwright install chromium. Возвращает True при успехе."""
    args = [_sys_bootstrap.executable, "-m", "playwright", "install"]
    if force:
        args.append("--force")
    args.append("chromium")
    print(f"[bootstrap] {'Пере' if force else ''}устанавливаю Chromium: {' '.join(args)}")
    try:
        _subprocess_bootstrap.check_call(args)
        return True
    except Exception as e:
        print(f"[bootstrap] Не удалось установить Chromium: {e}")
        return False


def _bootstrap_chromium() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return

    on_linux = _sys_bootstrap.platform.startswith("linux")

    if on_linux:
        print("[bootstrap] Проверяю системные зависимости Chromium (install-deps)...")
        try:
            r = _subprocess_bootstrap.run(
                [_sys_bootstrap.executable, "-m", "playwright", "install-deps", "chromium"],
                capture_output=True, text=True, timeout=600,
            )
            if r.returncode != 0:
                print(f"[bootstrap] install-deps вернул код {r.returncode}")
                print("[bootstrap] Если Chromium не запустится — установите вручную (sudo):")
                print("  sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 "
                      "libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 "
                      "libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 "
                      "libasound2 libatspi2.0-0")
        except Exception as e:
            print(f"[bootstrap] install-deps не выполнен: {e}")

    if not _chromium_installed():
        _install_chromium()


def _verify_chromium_launch(retry: bool = True) -> bool:
    if _os_bootstrap.environ.get("SKIP_CHROMIUM_VERIFY") == "1":
        return True
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            b.close()
        print("[bootstrap] ✅ Chromium запускается нормально.")
        return True
    except Exception as e:
        err = str(e)
        print(f"[bootstrap] ❌ Chromium НЕ запускается: {err[:500]}")
        low = err.lower()

        if retry and ("executable doesn't exist" in low or "playwright install" in low):
            print("[bootstrap] Chromium отсутствует или повреждён — переустанавливаю...")
            if _install_chromium(force=True):
                return _verify_chromium_launch(retry=False)

        if "asyncio loop" in low:
            print("[bootstrap] ⚠️ Похоже, в этом процессе остался запущенный asyncio-цикл. "
                  "Обычно такого при старте не бывает. Если повторится — перезапустите бота.")
        elif any(k in low for k in ("libnss", "shared object", "cannot open",
                                     "missing dependencies", "error while loading")):
            print("[bootstrap] ⚠️ Не хватает системных библиотек. Выполните под root:")
            print("  sudo python3 -m playwright install-deps chromium")
            print("  или:")
            print("  sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 "
                  "libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 "
                  "libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 "
                  "libasound2 libatspi2.0-0")
        return False


_bootstrap_pip_packages()
_bootstrap_chromium()
_verify_chromium_launch()
# ===========================================================================


# ---------------------- ОБЫЧНЫЕ ИМПОРТЫ ----------------------
import json
import logging
import os
import queue
import re
import threading
import time

import vk_api
from bs4 import BeautifulSoup
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.exceptions import ApiError
from vk_api.utils import get_random_id

# ======================= НАСТРОЙКИ =======================
VK_TOKEN = os.getenv("VK_TOKEN", "vk1.a.qTmbvDqtUaMY-v3WUAFCttrgbdC0pGgKRM97ls8g-INfMxhV9RW4jl_bzqoa5-evzCRVrEaFx4vI9dC9QHDvygT5f2OHaa8rrx77gqorzwt6H3TZ3shuFieOFrGds09ksldW8nXefrrmMy_kr9SW8zOl6OjdjfOPRyeA_clm7tcZbZM6Uc_BCR-leDG55phFCEoHRQhNl34oYCqT66b6HQ")

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "877246890"))

SECTION_URLS = {
    "obzhalovanie": os.getenv(
        "FORUM_URL_OBZHALOVANIE",
        "https://forum.blackrussia.online/forums/Обжалование-наказаний.1615/",
    ),
    "admins": os.getenv(
        "FORUM_URL_ADMINS",
        "https://forum.blackrussia.online/forums/Жалобы-на-администрацию.1612/",
    ),
    "players": os.getenv(
        "FORUM_URL_PLAYERS",
        "https://forum.blackrussia.online/forums/Жалобы-на-игроков.1614/",
    ),
}

SECTION_LABELS = {
    "obzhalovanie": "Обжалование",
    "admins": "Жалобы на администрацию",
    "players": "Жалобы на игроков",
}

FORUM_COOKIES = os.getenv("FORUM_COOKIES", "")
if not FORUM_COOKIES and os.path.exists("cookies.txt"):
    with open("cookies.txt", encoding="utf-8") as _f:
        FORUM_COOKIES = _f.read().strip()

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

DEADLINE_HOURS = float(os.getenv("DEADLINE_HOURS", "72"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))
RENOTIFY_HOURS = float(os.getenv("RENOTIFY_HOURS", "24"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "8"))
MAX_AGE_DAYS = float(os.getenv("MAX_AGE_DAYS", "30"))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "15"))
AUTO_NOTIFY = os.getenv("AUTO_NOTIFY", "0") == "1"
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "180"))
AF_COOLDOWN = int(os.getenv("AF_COOLDOWN", "15"))
SERVER_LABEL = "💚 Сервер №35"
API_VERSION = "5.199"
CHECK_PREFIXES = ["ожидание", "на рассмотрении", "главному администратору"]
# =========================================================

NOTIFIED_FILE = "notified.json"
CHATS_FILE = "chats.json"
OWNERS_FILE = "owners.json"
ADMINS_FILE = "admins.json"
SETTINGS_FILE = "settings.json"
BROWSER_STATE = "browser_state.json"
HEADLESS = os.getenv("HEADLESS", "1") == "1"
BASE_URL = "https://forum.blackrussia.online"

EMPTY_INLINE_KB = {"inline": True, "buttons": []}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot")


# ---------------------- настройки ----------------------
DEFAULT_SETTINGS = {
    "active_section": None,
    "sections": {
        "obzhalovanie": {"deadline_hours": DEADLINE_HOURS},
        "admins": {"deadline_hours": DEADLINE_HOURS},
        "players": {"deadline_hours": DEADLINE_HOURS},
    },
}
settings_lock = threading.Lock()


def get_settings() -> dict:
    with settings_lock:
        raw = load_json(SETTINGS_FILE, {})
        result = json.loads(json.dumps(DEFAULT_SETTINGS))
        if isinstance(raw, dict):
            if "active_section" in raw and raw["active_section"] in SECTION_LABELS:
                result["active_section"] = raw["active_section"]
            for k, v in (raw.get("sections") or {}).items():
                if k in result["sections"] and isinstance(v, dict):
                    result["sections"][k].update(v)
        return result


def save_settings(s: dict) -> None:
    with settings_lock:
        save_json(SETTINGS_FILE, s)


def get_active_section() -> str | None:
    return get_settings().get("active_section")


def get_deadline_hours(section: str) -> float:
    try:
        return float(get_settings()["sections"][section]["deadline_hours"])
    except Exception:
        return float(DEADLINE_HOURS)


def get_section_url(section: str) -> str:
    return SECTION_URLS[section]


def section_url_is_configured(section: str) -> bool:
    return "ЗАМЕНИ_НА_ID" not in get_section_url(section)


# ---------------------- форум ----------------------
def parse_cookies(raw: str) -> dict:
    cookies = {}
    raw = re.sub(r"^\s*cookie:\s*", "", raw.replace("\n", " "), flags=re.I)
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k] = v
    return cookies


class Browser:
    """Настоящий Chromium: проходит JS-проверку анти-DDoS защиты форума."""

    def __init__(self):
        from playwright.sync_api import sync_playwright

        self._pw = None
        self._browser = None

        try:
            self._pw = sync_playwright().start()
            launch_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]

            try:
                self._browser = self._pw.chromium.launch(
                    headless=HEADLESS, args=launch_args,
                )
            except Exception as launch_err:
                le = str(launch_err).lower()
                # Chromium не установлен — установим и попробуем снова
                if "executable doesn't exist" in le or "playwright install" in le:
                    log.warning("Chromium не найден, устанавливаю и пробую снова...")
                    if _install_chromium():
                        self._browser = self._pw.chromium.launch(
                            headless=HEADLESS, args=launch_args,
                        )
                    else:
                        raise
                else:
                    raise
        except Exception as e:
            try:
                if self._pw is not None:
                    self._pw.stop()
            except Exception:
                pass
            # Почистим возможный висящий asyncio-loop
            try:
                import asyncio
                asyncio.set_event_loop(None)
            except Exception:
                pass

            err_lower = str(e).lower()
            if "asyncio loop" in err_lower:
                raise RuntimeError(
                    "Playwright в этом процессе сломан (asyncio loop). "
                    "Перезапустите бота."
                ) from e
            if "executable doesn't exist" in err_lower:
                raise RuntimeError(
                    "Chromium не установлен. Выполните: python -m playwright install chromium"
                ) from e
            raise RuntimeError(
                "Chromium не удалось запустить. На Linux обычно не хватает системных "
                "библиотек. Выполните под root:\n"
                "  sudo python3 -m playwright install-deps chromium\n"
                f"Исходная ошибка: {e}"
            ) from e

        kwargs = {
            "user_agent": USER_AGENT,
            "locale": "ru-RU",
            "viewport": {"width": 1280, "height": 900},
        }
        has_state = os.path.exists(BROWSER_STATE)
        if has_state:
            kwargs["storage_state"] = BROWSER_STATE
        self.ctx = self._browser.new_context(**kwargs)
        if not has_state:
            cookies = [
                {"name": k, "value": v, "url": BASE_URL}
                for k, v in parse_cookies(FORUM_COOKIES).items()
            ]
            if cookies:
                self.ctx.add_cookies(cookies)
        self.page = self.ctx.new_page()

    def get_html(self, url: str) -> tuple[str, str]:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        html = ""
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                html = self.page.content()
            except Exception:
                html = ""
            if "data-logged-in" in html:
                break
            self.page.wait_for_timeout(1500)
        else:
            log.warning("Защита форума не пропустила за 60 сек.")
        try:
            self.page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        try:
            self.page.wait_for_selector("div.structItem, div.node, .blockMessage", timeout=10000)
        except Exception:
            pass
        try:
            html = self.page.content()
        except Exception:
            pass
        try:
            self.ctx.storage_state(path=BROWSER_STATE)
        except Exception:
            pass
        return self.page.url, html

    def close(self) -> None:
        for obj in (self.ctx, self._browser):
            try:
                obj.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass


def to_int(text: str) -> int:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else 0


def parse_threads(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    threads = []

    items = soup.select("div.structItem--thread") or soup.select("div.structItem")
    for item in items:
        links = [
            a for a in item.select("div.structItem-title a")
            if "labelLink" not in (a.get("class") or [])
        ]
        if not links:
            continue
        title_a = links[-1]
        href = title_a.get("href", "")
        m = re.search(r"\.(\d+)/?", href)
        if not m:
            continue
        thread_id = m.group(1)

        prefix_el = item.select_one("a.labelLink .label, .structItem-title .label")
        prefix = re.sub(r"\s+", " ", prefix_el.get_text(" ", strip=True)) if prefix_el else ""

        start_time = None
        t = item.select_one("li.structItem-startDate time")
        if t and t.get("data-time"):
            start_time = int(t["data-time"])
        if start_time is None:
            continue

        author = item.get("data-author", "")
        if not author:
            a = item.select_one(".structItem-minor a.username, a.username")
            author = a.get_text(strip=True) if a else ""

        replies = 0
        meta = item.select_one("div.structItem-cell--meta dd")
        if meta:
            replies = to_int(meta.get_text())

        last = item.select_one("div.structItem-cell--latest a.username")
        last_poster = last.get_text(strip=True) if last else ""

        locked = bool(item.select_one(".structItem-status--locked"))

        threads.append({
            "id": thread_id,
            "title": title_a.get_text(strip=True),
            "url": BASE_URL + href if href.startswith("/") else href,
            "prefix": prefix,
            "created": start_time,
            "author": author,
            "replies": replies,
            "last_poster": last_poster,
            "locked": locked,
        })
    return threads


def fetch_threads(browser: "Browser", section_url: str) -> list[dict]:
    result = []
    for page in range(1, MAX_PAGES + 1):
        url = section_url if page == 1 else f"{section_url}page-{page}"
        final_url, html = browser.get_html(url)
        page_threads = parse_threads(html)

        soup_dbg = BeautifulSoup(html, "html.parser")
        title = soup_dbg.title.get_text(strip=True) if soup_dbg.title else "нет <title>"
        logged_in = 'data-logged-in="true"' in html
        log.info(
            "Страница %d: итоговый URL=%s, title=%r, залогинен=%s, тем=%d",
            page, final_url, title, logged_in, len(page_threads),
        )
        if not page_threads and page > 1:
            log.info("Страницы раздела закончились на странице %d", page - 1)
            break
        if not page_threads:
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            log.warning("Тем не найдено, HTML сохранён в debug_page.html (длина %d)", len(html))
            text = re.sub(r"\s+", " ", soup_dbg.get_text(" ", strip=True))
            log.warning("Видимый текст страницы: %s", text[:700])
            nodes = soup_dbg.select("div.node-body a[href*='/forums/'], h3.node-title a")
            if nodes:
                log.warning("Найдены подразделы (%d):", len(nodes))
                seen = set()
                for a in nodes:
                    href = a.get("href", "")
                    if href in seen:
                        continue
                    seen.add(href)
                    log.warning("  - %s -> %s", a.get_text(strip=True), href)
                    if len(seen) >= 30:
                        break
            if 'data-logged-in="false"' in html:
                if os.path.exists(BROWSER_STATE):
                    os.remove(BROWSER_STATE)
                raise RuntimeError("Cookies устарели: форум не видит вас залогиненным")
            break
        known = {t["id"] for t in result}
        new = [t for t in page_threads if t["id"] not in known]
        if not new:
            break
        result.extend(new)
        time.sleep(1.5)
    return result


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower().replace("ё", "е")


def is_pending(th: dict) -> bool:
    prefix = norm(th["prefix"])
    return any(norm(p) in prefix for p in CHECK_PREFIXES)


# ---------------------- вспомогательное ----------------------
def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append(f"{d} д.")
    if h:
        parts.append(f"{h} ч.")
    if m and not d:
        parts.append(f"{m} мин.")
    return " ".join(parts) or "0 мин."


def load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            log.warning("Не удалось прочитать %s, начинаю заново", path)
    return default


def save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------- права доступа ----------------------
owners_lock = threading.Lock()
admins_lock = threading.Lock()


def is_bot_owner(uid: int) -> bool:
    return uid == BOT_OWNER_ID


def is_owner(uid: int) -> bool:
    if is_bot_owner(uid):
        return True
    return uid in load_json(OWNERS_FILE, [])


def is_admin(uid: int) -> bool:
    if is_owner(uid):
        return True
    return uid in load_json(ADMINS_FILE, [])


def add_owner(uid: int) -> bool:
    with owners_lock:
        lst = load_json(OWNERS_FILE, [])
        if uid in lst:
            return False
        lst.append(uid)
        save_json(OWNERS_FILE, lst)
        return True


def remove_owner(uid: int) -> bool:
    with owners_lock:
        lst = load_json(OWNERS_FILE, [])
        if uid not in lst:
            return False
        lst.remove(uid)
        save_json(OWNERS_FILE, lst)
        return True


def add_admin(uid: int) -> bool:
    with admins_lock:
        lst = load_json(ADMINS_FILE, [])
        if uid in lst:
            return False
        lst.append(uid)
        save_json(ADMINS_FILE, lst)
        return True


def remove_admin(uid: int) -> bool:
    with admins_lock:
        lst = load_json(ADMINS_FILE, [])
        if uid not in lst:
            return False
        lst.remove(uid)
        save_json(ADMINS_FILE, lst)
        return True


def get_user_name(vk, uid: int) -> str:
    try:
        users = vk.users.get(user_ids=uid)
        if users:
            u = users[0]
            name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
            return name or f"id{uid}"
    except Exception:
        pass
    return f"id{uid}"


def parse_target_id(msg: dict) -> int | None:
    reply = msg.get("reply_message") or {}
    rid = reply.get("from_id")
    if rid:
        return int(rid)
    raw = msg.get("text", "")
    m = re.search(r"\[id(\d+)\|", raw)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d{5,})\b", raw)
    if m:
        return int(m.group(1))
    return None


# ---------------------- активные беседы ----------------------
chats_lock = threading.Lock()
job_queue: "queue.Queue[dict]" = queue.Queue()
cache = {"time": 0.0, "threads": [], "section": None}
last_af: dict = {}


def get_chats() -> list[int]:
    with chats_lock:
        return list(load_json(CHATS_FILE, []))


def add_chat(peer_id: int) -> bool:
    with chats_lock:
        chats = load_json(CHATS_FILE, [])
        if peer_id in chats:
            return False
        chats.append(peer_id)
        save_json(CHATS_FILE, chats)
        return True


def remove_chat(peer_id: int) -> bool:
    with chats_lock:
        chats = load_json(CHATS_FILE, [])
        if peer_id not in chats:
            return False
        chats.remove(peer_id)
        save_json(CHATS_FILE, chats)
        return True


# ---------------------- VK ----------------------
def send_vk(vk, peer_id: int, text: str, format_data: str = None, keyboard: str = None) -> None:
    params = dict(
        peer_id=peer_id,
        message=text,
        random_id=get_random_id(),
        dont_parse_links=1,
    )
    if format_data:
        params["format_data"] = format_data
    if keyboard:
        params["keyboard"] = keyboard
    vk.messages.send(**params)


def send_inline(vk, peer_id: int, text: str, keyboard: dict) -> None:
    send_vk(vk, peer_id, text, keyboard=json.dumps(keyboard, ensure_ascii=False))


def edit_inline(vk, peer_id: int, conv_msg_id: int, text: str, keyboard: dict = None) -> None:
    if keyboard is None:
        keyboard = EMPTY_INLINE_KB
    params = dict(
        peer_id=peer_id,
        conversation_message_id=conv_msg_id,
        message=text,
        keyboard=json.dumps(keyboard, ensure_ascii=False),
        dont_parse_links=1,
    )
    try:
        vk.messages.edit(**params)
    except ApiError as e:
        log.warning("Не удалось отредактировать сообщение (%s), отправляю новое", e)
        try:
            vk.messages.send(
                peer_id=peer_id,
                message=text,
                random_id=get_random_id(),
                keyboard=json.dumps(keyboard, ensure_ascii=False),
                dont_parse_links=1,
            )
        except Exception:
            log.exception("Не удалось отправить новое сообщение")


def get_owner_id(vk, peer_id: int):
    resp = vk.messages.getConversationsById(peer_ids=peer_id)
    items = resp.get("items", [])
    if items:
        return (items[0].get("chat_settings") or {}).get("owner_id")
    return None


START_WORDS = {"старт", "start"}
STOP_WORDS = {"стоп", "stop"}
AF_WORDS = {"af", "аф"}
SETTINGS_WORDS = {"settings", "настройки"}

ADDOWNER_WORDS = {"addowner", "добавитьвладельца", "добавьвладельца"}
ADDADMIN_WORDS = {"addadmin", "добавитьадмина", "добавьадмина"}
REMOVEOWNER_WORDS = {"removeowner", "удалитьвладельца", "удаливладельца"}
REMOVEADMIN_WORDS = {"removeadmin", "удалитьадмина", "удалиадмина"}
ADMINS_LIST_WORDS = {"admins"}


# ---------------------- клавиатуры ----------------------
def kb_settings_main() -> dict:
    return {
        "inline": True,
        "buttons": [
            [
                {"action": {"type": "callback", "label": "1. Раздел по умолчанию",
                            "payload": json.dumps({"cmd": "settings_active"})}},
                {"action": {"type": "callback", "label": "2. Время просрока",
                            "payload": json.dumps({"cmd": "settings_time"})}},
            ],
            [
                {"action": {"type": "callback", "label": "3. Убрать раздел по умолчанию",
                            "payload": json.dumps({"cmd": "settings_clear_active"})}},
            ],
        ],
    }


def kb_section_choice(next_cmd: str) -> dict:
    return {
        "inline": True,
        "buttons": [
            [
                {"action": {"type": "callback", "label": SECTION_LABELS["obzhalovanie"],
                            "payload": json.dumps({"cmd": next_cmd, "section": "obzhalovanie"})}},
                {"action": {"type": "callback", "label": SECTION_LABELS["admins"],
                            "payload": json.dumps({"cmd": next_cmd, "section": "admins"})}},
            ],
            [
                {"action": {"type": "callback", "label": SECTION_LABELS["players"],
                            "payload": json.dumps({"cmd": next_cmd, "section": "players"})}},
            ],
            [
                {"action": {"type": "callback", "label": "◀ Назад",
                            "payload": json.dumps({"cmd": "settings_menu"})}},
            ],
        ],
    }


def kb_time_choice(section: str) -> dict:
    return {
        "inline": True,
        "buttons": [
            [
                {"action": {"type": "callback", "label": "24ч",
                            "payload": json.dumps({"cmd": "settings_pick_time", "section": section, "hours": 24})}},
                {"action": {"type": "callback", "label": "48ч",
                            "payload": json.dumps({"cmd": "settings_pick_time", "section": section, "hours": 48})}},
                {"action": {"type": "callback", "label": "72ч",
                            "payload": json.dumps({"cmd": "settings_pick_time", "section": section, "hours": 72})}},
            ],
            [
                {"action": {"type": "callback", "label": "◀ Назад",
                            "payload": json.dumps({"cmd": "settings_time"})}},
            ],
        ],
    }


def kb_confirm(yes_payload: dict, back_cmd: str = "settings_menu") -> dict:
    return {
        "inline": True,
        "buttons": [
            [
                {"action": {"type": "callback", "label": "Да",
                            "payload": json.dumps(yes_payload)}},
                {"action": {"type": "callback", "label": "Нет",
                            "payload": json.dumps({"cmd": back_cmd})}},
            ],
        ],
    }


def kb_af_sections() -> dict:
    return {
        "inline": True,
        "buttons": [
            [
                {"action": {"type": "callback", "label": SECTION_LABELS["obzhalovanie"],
                            "payload": json.dumps({"cmd": "af_run", "section": "obzhalovanie"})}},
                {"action": {"type": "callback", "label": SECTION_LABELS["admins"],
                            "payload": json.dumps({"cmd": "af_run", "section": "admins"})}},
            ],
            [
                {"action": {"type": "callback", "label": SECTION_LABELS["players"],
                            "payload": json.dumps({"cmd": "af_run", "section": "players"})}},
            ],
        ],
    }


# ---------------------- меню настроек ----------------------
def send_settings_menu(vk, peer_id: int, conv_msg_id: int = None) -> None:
    s = get_settings()
    active = s.get("active_section")
    active_str = SECTION_LABELS.get(active, "не установлен")
    deadlines = [
        f"• {SECTION_LABELS[sec]}: {s['sections'][sec]['deadline_hours']:g}ч"
        for sec in ("obzhalovanie", "admins", "players")
    ]
    lines = [
        "⚙️ Настройки",
        "",
        f"Раздел по умолчанию: {active_str}",
        "",
        "Время просрока:",
        *deadlines,
        "",
        "1. Установить раздел по умолчанию",
        "2. Назначить время просрока",
        "3. Убрать раздел по умолчанию",
    ]
    text = "\n".join(lines)
    kb = kb_settings_main()
    if conv_msg_id:
        edit_inline(vk, peer_id, conv_msg_id, text, kb)
    else:
        send_inline(vk, peer_id, text, kb)


# ---------------------- /af ----------------------
def handle_af(vk, peer_id: int, sender_id: int = 0) -> None:
    if not is_admin(sender_id) and peer_id not in get_chats():
        send_vk(vk, peer_id, "Бот выключен в этой беседе. Владелец беседы должен написать «старт».")
        return
    now = time.time()
    if now - last_af.get(peer_id, 0) < AF_COOLDOWN:
        return
    last_af[peer_id] = now

    section = get_active_section()
    if section:
        send_vk(
            vk, peer_id,
            f"⏳ Проверяю раздел «{SECTION_LABELS[section]}», это займёт около минуты...",
        )
        job_queue.put({"type": "af", "peer": peer_id, "section": section})
    else:
        send_inline(
            vk, peer_id,
            "Какой раздел проверить на просроченные жалобы?\n\n"
            "💡 Раздел по умолчанию можно установить через /settings.",
            kb_af_sections(),
        )


# ---------------------- callback ----------------------
def _cb_field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def handle_callback(vk, event_object) -> None:
    try:
        peer_id = int(_cb_field(event_object, "peer_id"))
        user_id = int(_cb_field(event_object, "user_id"))
        event_id = _cb_field(event_object, "event_id")
        conv_msg_id = int(_cb_field(event_object, "conversation_message_id"))
        raw_payload = _cb_field(event_object, "payload") or "{}"
    except Exception:
        log.exception("Некорректный callback-объект")
        return

    try:
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else (raw_payload or {})
    except Exception:
        payload = {}
    cmd = payload.get("cmd")

    answer = {"type": "show_snackbar", "text": "Готово"}

    try:
        is_settings_cmd = bool(cmd) and cmd.startswith("settings_")

        if is_settings_cmd and not is_admin(user_id):
            answer = {"type": "show_snackbar", "text": "Недостаточно прав"}

        elif cmd == "settings_menu":
            send_settings_menu(vk, peer_id, conv_msg_id)

        elif cmd == "settings_active":
            edit_inline(
                vk, peer_id, conv_msg_id,
                "Выберите раздел, который хотите установить по умолчанию:",
                kb_section_choice("settings_pick_active"),
            )

        elif cmd == "settings_pick_active":
            section = payload.get("section")
            if section in SECTION_LABELS:
                text = (
                    "Вы подтверждаете свои действия?\n\n"
                    f"Установить раздел по умолчанию: {SECTION_LABELS[section]}"
                )
                yes = {"cmd": "settings_set_active", "section": section}
                edit_inline(vk, peer_id, conv_msg_id, text, kb_confirm(yes, "settings_active"))
            else:
                answer = {"type": "show_snackbar", "text": "Неверный раздел"}

        elif cmd == "settings_set_active":
            section = payload.get("section")
            if section in SECTION_LABELS:
                s = get_settings()
                s["active_section"] = section
                save_settings(s)
                edit_inline(
                    vk, peer_id, conv_msg_id,
                    "✅ Изменения были внесены!\n\n"
                    f"Раздел по умолчанию: {SECTION_LABELS[section]}",
                    EMPTY_INLINE_KB,
                )
            else:
                answer = {"type": "show_snackbar", "text": "Неверные данные"}

        elif cmd == "settings_time":
            edit_inline(
                vk, peer_id, conv_msg_id,
                "Выберите раздел, для которого хотите установить время просрока:",
                kb_section_choice("settings_pick_time_section"),
            )

        elif cmd == "settings_pick_time_section":
            section = payload.get("section")
            if section in SECTION_LABELS:
                edit_inline(
                    vk, peer_id, conv_msg_id,
                    f"Выберите время просрока для раздела «{SECTION_LABELS[section]}»:",
                    kb_time_choice(section),
                )
            else:
                answer = {"type": "show_snackbar", "text": "Неверный раздел"}

        elif cmd == "settings_pick_time":
            section = payload.get("section")
            hours = payload.get("hours")
            if section in SECTION_LABELS and hours in (24, 48, 72):
                text = (
                    "Вы подтверждаете свои действия?\n\n"
                    f"Раздел: {SECTION_LABELS[section]}\n"
                    f"Время просрока: {hours}ч"
                )
                yes = {"cmd": "settings_set_time", "section": section, "hours": hours}
                edit_inline(vk, peer_id, conv_msg_id, text,
                            kb_confirm(yes, "settings_pick_time_section"))
            else:
                answer = {"type": "show_snackbar", "text": "Неверные параметры"}

        elif cmd == "settings_set_time":
            section = payload.get("section")
            hours = payload.get("hours")
            if section in SECTION_LABELS and hours in (24, 48, 72):
                s = get_settings()
                s["sections"][section]["deadline_hours"] = float(hours)
                save_settings(s)
                edit_inline(
                    vk, peer_id, conv_msg_id,
                    "✅ Изменения были внесены!\n\n"
                    f"Раздел «{SECTION_LABELS[section]}»: время просрока {hours}ч",
                    EMPTY_INLINE_KB,
                )
            else:
                answer = {"type": "show_snackbar", "text": "Неверные данные"}

        elif cmd == "settings_clear_active":
            active = get_active_section()
            if not active:
                edit_inline(
                    vk, peer_id, conv_msg_id,
                    "ℹ️ Раздел по умолчанию и так не установлен.",
                    EMPTY_INLINE_KB,
                )
            else:
                text = (
                    "Вы подтверждаете свои действия?\n\n"
                    f"Убрать раздел по умолчанию: {SECTION_LABELS[active]}"
                )
                yes = {"cmd": "settings_do_clear_active"}
                edit_inline(vk, peer_id, conv_msg_id, text, kb_confirm(yes, "settings_menu"))

        elif cmd == "settings_do_clear_active":
            s = get_settings()
            s["active_section"] = None
            save_settings(s)
            edit_inline(
                vk, peer_id, conv_msg_id,
                "✅ Изменения были внесены!\n\n"
                "Раздел по умолчанию убран.",
                EMPTY_INLINE_KB,
            )

        elif cmd == "af_run":
            section = payload.get("section")
            if section not in SECTION_LABELS:
                answer = {"type": "show_snackbar", "text": "Неверный раздел"}
            elif not is_admin(user_id) and peer_id not in get_chats():
                answer = {"type": "show_snackbar", "text": "Бот выключен в этой беседе"}
            else:
                edit_inline(
                    vk, peer_id, conv_msg_id,
                    f"⏳ Проверяю раздел «{SECTION_LABELS[section]}», это займёт около минуты...",
                    EMPTY_INLINE_KB,
                )
                job_queue.put({"type": "af", "peer": peer_id, "section": section})
                answer = {"type": "show_snackbar", "text": "Проверяю..."}

        else:
            answer = {"type": "show_snackbar", "text": "Неизвестная команда"}
    except Exception:
        log.exception("Ошибка обработки callback")
        answer = {"type": "show_snackbar", "text": "Ошибка"}

    try:
        vk.messages.sendMessageEventAnswer(
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps(answer, ensure_ascii=False),
        )
    except Exception:
        log.exception("Не удалось ответить на callback")


# ---------------------- команды управления доступом ----------------------
def handle_add_owner_cmd(vk, peer_id: int, sender_id: int, msg: dict) -> None:
    if not is_bot_owner(sender_id):
        send_vk(vk, peer_id, "⛔ Только владелец бота (BOT_OWNER_ID) может выдавать /addowner.")
        return
    target = parse_target_id(msg)
    if not target or target < 0:
        send_vk(vk, peer_id, "Укажите пользователя: ответьте на его сообщение, "
                             "упомяните через @ или напишите его числовой ID.")
        return
    if target == BOT_OWNER_ID:
        send_vk(vk, peer_id, "Владелец бота уже имеет максимальные права.")
        return
    name = get_user_name(vk, target)
    if add_owner(target):
        send_vk(vk, peer_id, f"✅ {name} теперь владелец.\n"
                             f"Может: /addadmin, /removeadmin, старт/стоп, /af, /settings.")
        log.info("Добавлен владелец %s", target)
    else:
        send_vk(vk, peer_id, f"{name} уже в списке владельцев.")


def handle_add_admin_cmd(vk, peer_id: int, sender_id: int, msg: dict) -> None:
    if not is_owner(sender_id):
        send_vk(vk, peer_id, "⛔ Только владелец бота или /addowner-пользователь может выдавать /addadmin.")
        return
    target = parse_target_id(msg)
    if not target or target < 0:
        send_vk(vk, peer_id, "Укажите пользователя: ответьте на его сообщение, "
                             "упомяните через @ или напишите его числовой ID.")
        return
    if target == BOT_OWNER_ID:
        send_vk(vk, peer_id, "Владелец бота уже имеет максимальные права.")
        return
    name = get_user_name(vk, target)
    if add_admin(target):
        send_vk(vk, peer_id, f"✅ {name} теперь админ.\n"
                             f"Может: старт/стоп в любой беседе и /af в любой беседе.")
        log.info("Добавлен админ %s", target)
    else:
        send_vk(vk, peer_id, f"{name} уже в списке админов.")


def handle_remove_owner_cmd(vk, peer_id: int, sender_id: int, msg: dict) -> None:
    if not is_bot_owner(sender_id):
        send_vk(vk, peer_id, "⛔ Только владелец бота (BOT_OWNER_ID) может снимать владельцев.")
        return
    target = parse_target_id(msg)
    if not target or target < 0:
        send_vk(vk, peer_id, "Укажите пользователя: ответьте на его сообщение, "
                             "упомяните через @ или напишите его числовой ID.")
        return
    if target == BOT_OWNER_ID:
        send_vk(vk, peer_id, "Владельца бота снять нельзя.")
        return
    name = get_user_name(vk, target)
    if remove_owner(target):
        send_vk(vk, peer_id, f"⛔ {name} больше не владелец.")
        log.info("Снят владелец %s", target)
    else:
        send_vk(vk, peer_id, f"{name} не в списке владельцев.")


def handle_remove_admin_cmd(vk, peer_id: int, sender_id: int, msg: dict) -> None:
    if not is_owner(sender_id):
        send_vk(vk, peer_id, "⛔ Только владелец бота или /addowner-пользователь может снимать админов.")
        return
    target = parse_target_id(msg)
    if not target or target < 0:
        send_vk(vk, peer_id, "Укажите пользователя: ответьте на его сообщение, "
                             "упомяните через @ или напишите его числовой ID.")
        return
    if target == BOT_OWNER_ID:
        send_vk(vk, peer_id, "Владельца бота снять нельзя.")
        return
    name = get_user_name(vk, target)
    if remove_admin(target):
        send_vk(vk, peer_id, f"⛔ {name} больше не админ.")
        log.info("Снят админ %s", target)
    else:
        send_vk(vk, peer_id, f"{name} не в списке админов.")


def handle_list_admins(vk, peer_id: int, sender_id: int) -> None:
    if not is_admin(sender_id):
        send_vk(vk, peer_id, "⛔ Недостаточно прав.")
        return
    owners = load_json(OWNERS_FILE, [])
    admins = load_json(ADMINS_FILE, [])
    all_ids = list({BOT_OWNER_ID, *owners, *admins})

    names: dict = {}
    try:
        for u in vk.users.get(user_ids=all_ids):
            names[u["id"]] = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
    except Exception:
        pass

    def fmt(uid: int) -> str:
        n = names.get(uid)
        return f"{n} (id{uid})" if n else f"id{uid}"

    lines = [f"👑 Владелец бота: {fmt(BOT_OWNER_ID)}"]
    if owners:
        lines.append("Владельцы:\n  - " + "\n  - ".join(fmt(x) for x in owners))
    if admins:
        lines.append("Админы:\n  - " + "\n  - ".join(fmt(x) for x in admins))
    if not owners and not admins:
        lines.append("Кроме владельца бота — никого.")
    send_vk(vk, peer_id, "\n".join(lines))


# ---------------------- обработка сообщений ----------------------
def handle_message(vk, msg: dict) -> None:
    peer_id = msg.get("peer_id", 0)
    if peer_id <= 2000000000:
        return

    sender_id = msg.get("from_id", 0)
    raw = msg.get("text", "")

    cmd_text = re.sub(r"\[club\d+\|[^\]]*\]", "", raw)
    cmd_text = cmd_text.strip().lstrip("/").strip().lower()
    parts = cmd_text.split()
    cmd = parts[0] if parts else ""

    if cmd in SETTINGS_WORDS:
        if not is_admin(sender_id):
            send_vk(vk, peer_id, "⛔ Только админы/владельцы могут менять настройки.")
            return
        send_settings_menu(vk, peer_id)
        return

    if cmd in ADDOWNER_WORDS:
        handle_add_owner_cmd(vk, peer_id, sender_id, msg)
        return
    if cmd in ADDADMIN_WORDS:
        handle_add_admin_cmd(vk, peer_id, sender_id, msg)
        return
    if cmd in REMOVEOWNER_WORDS:
        handle_remove_owner_cmd(vk, peer_id, sender_id, msg)
        return
    if cmd in REMOVEADMIN_WORDS:
        handle_remove_admin_cmd(vk, peer_id, sender_id, msg)
        return
    if cmd in ADMINS_LIST_WORDS:
        handle_list_admins(vk, peer_id, sender_id)
        return

    if cmd in AF_WORDS:
        handle_af(vk, peer_id, sender_id)
        return

    if cmd_text not in START_WORDS | STOP_WORDS:
        return

    try:
        owner_id = get_owner_id(vk, peer_id)
    except ApiError as e:
        log.warning("Не удалось определить владельца беседы %s: %s", peer_id, e)
        owner_id = None

    has_privileges = is_admin(sender_id)

    if owner_id is None and not has_privileges:
        send_vk(vk, peer_id, "Не могу определить владельца беседы. "
                             "Сделайте сообщество администратором беседы и повторите.")
        return
    if sender_id != owner_id and not has_privileges:
        send_vk(vk, peer_id, "Включать и выключать бота может только владелец беседы "
                             "(или пользователь с правами админа/владельца бота).")
        return

    if cmd_text in START_WORDS:
        if add_chat(peer_id):
            send_vk(vk, peer_id,
                    "✅ Бот включён. Буду сообщать о просроченных жалобах. "
                    "Раздел и время настраиваются через /settings. Выключить - «стоп».")
            log.info("Беседа %s включена", peer_id - 2000000000)
            if AUTO_NOTIFY and get_active_section():
                job_queue.put({"type": "auto"})
        else:
            send_vk(vk, peer_id, "Бот уже включён в этой беседе.")
    else:
        if remove_chat(peer_id):
            send_vk(vk, peer_id, "⛔ Бот выключен. Включить снова - «старт».")
            log.info("Беседа %s выключена", peer_id - 2000000000)
        else:
            send_vk(vk, peer_id, "Бот и так выключен в этой беседе.")


def listen(vk_session, vk) -> None:
    try:
        resp = vk.groups.getById()
        if isinstance(resp, dict):
            resp = resp.get("groups", [])
        group_id = resp[0]["id"]
    except Exception as e:
        raise SystemExit(
            f"Не удалось получить ID сообщества ({e}). "
            "Нужен ключ СООБЩЕСТВА (не личной страницы) с правом «сообщения»."
        )
    log.info("Слушаю команды в сообществе %s", group_id)

    while True:
        try:
            longpoll = VkBotLongPoll(vk_session, group_id)
            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    try:
                        handle_message(vk, event.message)
                    except Exception:
                        log.exception("Ошибка обработки сообщения")
                elif event.type == VkBotEventType.MESSAGE_EVENT:
                    try:
                        handle_callback(vk, event.object)
                    except Exception:
                        log.exception("Ошибка обработки callback")
        except Exception:
            log.exception("Long Poll отвалился, переподключаюсь через 5 сек.")
            time.sleep(5)


# ---------------------- проверка форума ----------------------
def notify_chat(vk, chat_id: int, items: list, st: dict, now: float,
                section: str, deadline_hours: float) -> None:
    total = len(items)
    items = items[:MAX_PER_RUN]
    label = SECTION_LABELS.get(section, "раздел")
    header = (
        f"⚠ Просроченные жалобы в разделе «{label}» (GROZNY) - {total} шт.\n"
        f"Срок рассмотрения: {fmt_duration(deadline_hours * 3600)}"
    )
    for i in range(0, len(items), 10):
        chunk = items[i:i + 10]
        lines = [
            f"[{th['prefix']}] {th['title'][:70]}\n"
            f"{th['url']}\n"
            f"Подана: {fmt_duration(age)} назад | ⏰ просрок: {fmt_duration(overdue)}"
            for overdue, th, age in chunk
        ]
        send_vk(vk, chat_id, header + "\n\n" + "\n\n".join(lines))
        for _, th, _ in chunk:
            st[th["id"]] = now
        time.sleep(1)
    log.info("Беседа %s: отправлено %d из %d", chat_id - 2000000000, len(items), total)


def check(browser, vk, notified: dict) -> None:
    chats = get_chats()
    if not chats:
        log.info("Нет включённых бесед (владелец беседы должен написать «старт»)")
        return

    section = get_active_section()
    if not section:
        log.info("Раздел по умолчанию не установлен, авто-проверка пропущена.")
        return
    if not section_url_is_configured(section):
        log.error("URL для раздела «%s» не настроен (ЗАМЕНИ_НА_ID).", section)
        return

    section_url = get_section_url(section)
    deadline_hours = get_deadline_hours(section)

    now = time.time()
    threads = fetch_threads(browser, section_url)
    log.info("Получено тем: %d (раздел: %s)", len(threads), SECTION_LABELS.get(section, section))

    from collections import Counter
    prefixes = Counter(t["prefix"] or "(без префикса)" for t in threads)
    log.info("Префиксы в разделе: %s", dict(prefixes.most_common(12)))

    pending_ids = set()
    overdue_items = []
    n_too_old = n_not_yet = 0
    for th in threads:
        if not is_pending(th):
            continue
        pending_ids.add(th["id"])
        age = now - th["created"]
        if MAX_AGE_DAYS and age > MAX_AGE_DAYS * 86400:
            n_too_old += 1
            continue
        overdue = age - deadline_hours * 3600
        if overdue <= 0:
            n_not_yet += 1
            continue
        overdue_items.append((overdue, th, age))
    overdue_items.sort(key=lambda x: x[0], reverse=True)
    log.info(
        "С нужным префиксом: %d | старше %g дн. (пропущено): %d | "
        "ещё в пределах срока: %d | просрочено: %d",
        len(pending_ids), MAX_AGE_DAYS, n_too_old, n_not_yet, len(overdue_items),
    )

    seen_ids = {t["id"] for t in threads}
    for chat_id in chats:
        st = notified.setdefault(str(chat_id), {})
        fresh = [x for x in overdue_items
                 if now - st.get(x[1]["id"], 0) >= RENOTIFY_HOURS * 3600]
        if fresh:
            try:
                notify_chat(vk, chat_id, fresh, st, now, section, deadline_hours)
            except ApiError as e:
                log.error("Беседа %s: ошибка VK: %s", chat_id - 2000000000, e)
                if e.code == 917:
                    remove_chat(chat_id)
                    log.warning("Беседа %s отключена: нет доступа", chat_id - 2000000000)
            except Exception:
                log.exception("Беседа %s: не удалось отправить", chat_id - 2000000000)
        for tid in list(st):
            if tid in seen_ids and tid not in pending_ids:
                del st[tid]


# ---------------------- отчёт по /af ----------------------
def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def overdue_rows(threads: list, now: float, deadline_hours: float) -> list:
    rows = []
    for th in threads:
        if not is_pending(th):
            continue
        age = now - th["created"]
        if age <= deadline_hours * 3600:
            continue
        if MAX_AGE_DAYS and age > MAX_AGE_DAYS * 86400:
            continue
        rows.append((age, th))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def build_messages(rows: list, section: str, deadline_hours: float,
                   with_links: bool = True, per_message: int = 40) -> list:
    label = SECTION_LABELS.get(section, "Раздел")
    head = f"⚜️ {label} (>{deadline_hours:g}ч)\n\n{SERVER_LABEL}\n"
    chunks = [rows[i:i + per_message] for i in range(0, len(rows), per_message)] or [[]]
    out, n = [], 0
    for ci, chunk in enumerate(chunks):
        text = head if ci == 0 else ""
        items = []
        if not rows:
            text += "✅ Просроченных обращений нет\n"
        for age, th in chunk:
            n += 1
            text += f"🖥️ {n}. {int(age // 3600)}ч - "
            prefix_label = th["prefix"]
            if with_links:
                items.append({
                    "type": "url",
                    "offset": utf16_len(text),
                    "length": utf16_len(prefix_label),
                    "url": th["url"],
                })
                text += prefix_label + "\n"
            else:
                text += f"{prefix_label}\n{th['url']}\n"
        fd = None
        if with_links and items:
            fd = json.dumps({"version": "1", "items": items}, ensure_ascii=False)
        out.append((text.rstrip("\n"), fd))
    return out


def send_report(vk, peer_id: int, rows: list, section: str, deadline_hours: float) -> None:
    try:
        for text, fd in build_messages(rows, section, deadline_hours, with_links=True):
            send_vk(vk, peer_id, text, fd)
            time.sleep(0.5)
    except ApiError as e:
        if e.code == 917:
            raise
        log.warning("Не сработало форматирование ссылок (%s), шлю обычным текстом", e)
        for text, _ in build_messages(rows, section, deadline_hours, with_links=False):
            send_vk(vk, peer_id, text)
            time.sleep(0.5)


def run_af(browser, vk, peer_id: int, section: str) -> None:
    if not section_url_is_configured(section):
        send_vk(
            vk, peer_id,
            f"⚠️ Для раздела «{SECTION_LABELS[section]}» не задана ссылка. "
            f"Настройте SECTION_URLS в коде.",
        )
        return
    section_url = get_section_url(section)
    deadline_hours = get_deadline_hours(section)

    if cache.get("section") != section or time.time() - cache["time"] > CACHE_SECONDS:
        cache["threads"] = fetch_threads(browser, section_url)
        cache["time"] = time.time()
        cache["section"] = section

    rows = overdue_rows(cache["threads"], time.time(), deadline_hours)
    log.info("/af в беседе %s: раздел %s, просроченных %d",
             peer_id - 2000000000, section, len(rows))
    send_report(vk, peer_id, rows, section, deadline_hours)


def worker_loop(vk) -> None:
    browser = None
    notified = load_json(NOTIFIED_FILE, {})
    next_auto = 0.0
    browser_broken = False          # сломан ли playwright в этом процессе
    browser_broken_notified = False # сообщили ли уже про поломку

    while True:
        timeout = max(1.0, next_auto - time.time()) if AUTO_NOTIFY else None
        try:
            job = job_queue.get(timeout=timeout)
        except queue.Empty:
            job = {"type": "auto"}
        peer = job.get("peer")
        if job["type"] == "auto":
            if not AUTO_NOTIFY:
                continue
            next_auto = time.time() + CHECK_INTERVAL

        try:
            # Пытаемся инициализировать браузер (если он нужен и ещё не инициализирован)
            if browser is None and not browser_broken and (job["type"] == "af" or get_chats()):
                try:
                    browser = Browser()
                except Exception as be:
                    be_lower = str(be).lower()
                    if "asyncio loop" in be_lower or "playwright в этом процессе" in be_lower:
                        browser_broken = True
                        log.error("Playwright сломан в этом процессе, браузер больше не запустится "
                                  "до перезапуска бота: %s", be)
                        if not browser_broken_notified:
                            for target in get_chats():
                                try:
                                    send_vk(
                                        vk, target,
                                        "❗ Playwright в этом процессе сломался (asyncio loop). "
                                        "Перезапустите бота, чтобы продолжить проверки.",
                                    )
                                except Exception:
                                    pass
                            browser_broken_notified = True
                        if peer:
                            try:
                                send_vk(vk, peer,
                                        "❗ Playwright сломан. Перезапустите бота.")
                            except Exception:
                                pass
                        continue
                    raise

            if browser is None and browser_broken:
                continue

            if job["type"] == "af":
                run_af(browser, vk, peer, job["section"])
            elif get_chats():
                check(browser, vk, notified)
                save_json(NOTIFIED_FILE, notified)
        except Exception as e:
            log.exception("Ошибка: %s", e)
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
                browser = None
            err_msg = str(e) or type(e).__name__
            stale = "Cookies устарели" in err_msg
            if stale:
                text = "❗ Бот: cookies форума устарели, обновите cookies.txt."
            else:
                short = err_msg[:400]
                text = (f"⚠ Не удалось получить данные с форума.\n\n"
                        f"Детали: {short}\n\n"
                        f"Если речь о Chromium/playwright — на Linux выполните под root:\n"
                        f"sudo python3 -m playwright install-deps chromium")
            if peer or stale:
                for target in ([peer] if peer else get_chats()):
                    try:
                        send_vk(vk, target, text)
                    except Exception:
                        pass


def main() -> None:
    vk_session = vk_api.VkApi(token=VK_TOKEN, api_version=API_VERSION)
    vk = vk_session.get_api()
    vk_worker = vk_api.VkApi(token=VK_TOKEN, api_version=API_VERSION).get_api()

    log.info("Бот запущен. Владелец: id%s. Авто-уведомления: %s",
             BOT_OWNER_ID, "вкл" if AUTO_NOTIFY else "выкл")
    log.info("Раздел по умолчанию: %s",
             SECTION_LABELS.get(get_active_section(), "не установлен"))
    threading.Thread(target=worker_loop, args=(vk_worker,), daemon=True).start()
    listen(vk_session, vk)


if __name__ == "__main__":
    main()
