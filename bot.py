"""
VK-бот: следит за разделами форума forum.blackrussia.online (сервер 35 GROZNY)
и пишет о просроченных обращениях в беседы, где владелец беседы написал «старт»
(выключить - «стоп»).

Разделы (ссылки вставляются в блок SECTIONS ниже):
  • Обжалование наказаний
  • Жалобы на администрацию
  • Жалобы на игроков

Команды:
  старт / стоп         — владелец беседы, админ, владелец бота
  /af  (или /аф)       — спросит раздел кнопками (или сразу покажет «постоянный» раздел).
                         В активной беседе, а также админы/владельцы в любой беседе
  /setting (/настройки) — настройки беседы: постоянный раздел, срок рассмотрения.
                         Владелец беседы, админы и владельцы бота
  /addadmin <id|@|реплай>   — владелец бота или /addowner-пользователь
  /addowner <id|@|реплай>   — только владелец бота (BOT_OWNER_ID)
  /removeadmin <id|@|реплай> — владелец бота или owner
  /removeowner <id|@|реплай> — только владелец бота
  /admins              — список владельцев и админов (только для админов/владельцев)

Запуск:  python bot.py
"""
import json
import logging
import os
import queue
import re
import subprocess  # нужен, чтобы скачать Chromium, если хостинг его не поставил
import sys
import threading
import time
import asyncio

import vk_api
from bs4 import BeautifulSoup
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.exceptions import ApiError
from vk_api.utils import get_random_id

# ======================= НАСТРОЙКИ =======================
# Токен сообщества VK. НЕ вставляйте его прямо в код.
# Положите его в переменную окружения VK_TOKEN на хостинге
# или в файл token.txt рядом с bot.py (одной строкой).
VK_TOKEN = os.getenv("VK_TOKEN", "vk1.a.qTmbvDqtUaMY-v3WUAFCttrgbdC0pGgKRM97ls8g-INfMxhV9RW4jl_bzqoa5-evzCRVrEaFx4vI9dC9QHDvygT5f2OHaa8rrx77gqorzwt6H3TZ3shuFieOFrGds09ksldW8nXefrrmMy_kr9SW8zOl6OjdjfOPRyeA_clm7tcZbZM6Uc_BCR-leDG55phFCEoHRQhNl34oYCqT66b6HQ")
if not VK_TOKEN and os.path.exists("token.txt"):
    with open("token.txt", encoding="utf-8") as _f:
        VK_TOKEN = _f.read().strip()

# --- ВЛАДЕЛЕЦ БОТА ---
# Может всё: /addowner, /addadmin, /remove*, старт/стоп, /af, /admins, /setting.
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "877246890"))

# Cookies вашего админ-аккаунта из браузера (строка целиком).
FORUM_COOKIES = os.getenv("FORUM_COOKIES", "")
if not FORUM_COOKIES and os.path.exists("cookies.txt"):
    with open("cookies.txt", encoding="utf-8") as _f:
        FORUM_COOKIES = _f.read().strip()

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

DEADLINE_HOURS = float(os.getenv("DEADLINE_HOURS", "72"))   # срок по умолчанию (можно менять в /setting)
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

# Какие сроки (в часах) можно выбрать кнопками в /setting
DEADLINE_CHOICES = [24, 48, 72, 96]

# ---------------------- РАЗДЕЛЫ ФОРУМА ----------------------
# >>> СЮДА ВСТАВЛЯЙТЕ ССЫЛКИ НА РАЗДЕЛЫ <<<
# Вместо ВСТАВЬТЕ_ССЫЛКУ_СЮДА впишите ссылку на раздел (в кавычках).
# Ссылка должна начинаться с https:// . Слэш в конце бот добавит сам.
#
# "prefixes" - какие префиксы тем считаются «ждёт ответа».
# Для жалоб на админов/игроков префиксы могут отличаться - тогда поправьте список.
SECTIONS = {
    "appeal": {
        "title": "Обжалование наказаний",
        "button": "Обжалование",
        "icon": "⚜️",
        "url": os.getenv(
            "FORUM_SECTION_URL",
            "https://forum.blackrussia.online/forums/Обжалование-наказаний.1615/",
        ),
        "prefixes": CHECK_PREFIXES,
    },
    "admin": {
        "title": "Жалобы на администрацию",
        "button": "Жалобы на администрацию",
        "icon": "🛡️",
        "url": os.getenv("ADMIN_COMPLAINTS_URL", "https://forum.blackrussia.online/forums/Жалобы-на-администрацию.1612/"),
        "prefixes": CHECK_PREFIXES,
    },
    "players": {
        "title": "Жалобы на игроков",
        "button": "Жалобы на игроков",
        "icon": "👤",
        "url": os.getenv("PLAYER_COMPLAINTS_URL", "https://forum.blackrussia.online/forums/Жалобы-на-игроков.1614/"),
        "prefixes": CHECK_PREFIXES,
    },
}
# =========================================================

NOTIFIED_FILE = "notified.json"
CHATS_FILE = "chats.json"
OWNERS_FILE = "owners.json"   # кто может /addadmin, /removeadmin, старт/стоп, /af
ADMINS_FILE = "admins.json"   # кто может старт/стоп и /af
SETTINGS_FILE = "settings.json"  # настройки каждой беседы (/setting)
BROWSER_STATE = "browser_state.json"
HEADLESS = os.getenv("HEADLESS", "1") == "1"
BASE_URL = "https://forum.blackrussia.online"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot")


def section_ready(key: str) -> bool:
    """True, если для раздела вставлена настоящая ссылка."""
    return SECTIONS[key]["url"].strip().lower().startswith("http")


# ---------------------- форум ----------------------
def parse_cookies(raw: str) -> dict:
    cookies = {}
    raw = re.sub(r"^\s*cookie:\s*", "", raw.replace("\n", " "), flags=re.I)
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k] = v
    return cookies


def install_chromium() -> None:
    """Скачивает Chromium, если хостинг не поставил его при сборке."""
    log.warning("Chromium не найден, скачиваю (это займёт 1-3 минуты)...")
    try:
        # Браузер + системные библиотеки (нужны права root)
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
            check=True,
            timeout=900,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # Если системные библиотеки поставить не вышло, качаем хотя бы браузер
        log.warning("Не вышло с системными библиотеками, пробую только браузер")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            timeout=900,
        )
    log.info("Chromium установлен")


class Browser:
    """Настоящий Chromium: проходит JS-проверку анти-DDoS защиты форума."""

    def __init__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        launch_args = dict(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        try:
            try:
                self._browser = self._pw.chromium.launch(**launch_args)
            except Exception as e:
                # Браузера нет - скачиваем и пробуем ещё раз
                if "Executable doesn't exist" not in str(e):
                    raise
                install_chromium()
                self._browser = self._pw.chromium.launch(**launch_args)
        except Exception:
            # Обязательно останавливаем Playwright, иначе при следующей
            # попытке будет ошибка про asyncio loop
            try:
                self._pw.stop()
            except Exception:
                pass
            raise
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
    """Читает все страницы раздела по ссылке section_url."""
    section_url = section_url.strip()
    if not section_url.endswith("/"):
        section_url += "/"  # без слэша страницы page-2 и далее не откроются
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
            log.warning(
                "Элементов: structItem=%d, node=%d, blockMessage=%d",
                len(soup_dbg.select("div.structItem")),
                len(soup_dbg.select("div.node")),
                len(soup_dbg.select(".blockMessage")),
            )
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


def is_pending(th: dict, prefixes: list = None) -> bool:
    prefix = norm(th["prefix"])
    return any(norm(p) in prefix for p in (prefixes or CHECK_PREFIXES))


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
    """Достаёт ID из реплая, упоминания [id123|..] или простого числа."""
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
cache: dict = {}      # кэш тем по разделам: {ключ_раздела: {"time": ..., "threads": [...]}}
last_af: dict = {}    # защита от спама командой /af и кнопками


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


# ---------------------- настройки бесед (/setting) ----------------------
settings_lock = threading.Lock()


def get_settings(peer_id: int) -> dict:
    """Настройки беседы. Если ничего не меняли - берутся значения по умолчанию."""
    with settings_lock:
        data = load_json(SETTINGS_FILE, {})
    st = {"pinned": False, "section": "appeal", "deadline": DEADLINE_HOURS}
    st.update(data.get(str(peer_id), {}))
    if st["section"] not in SECTIONS:
        st["section"] = "appeal"
    return st


def update_settings(peer_id: int, **changes) -> None:
    with settings_lock:
        data = load_json(SETTINGS_FILE, {})
        data.setdefault(str(peer_id), {}).update(changes)
        save_json(SETTINGS_FILE, data)


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


def edit_vk(vk, peer_id: int, conversation_message_id: int, text: str, keyboard: str = None) -> None:
    """Меняет текст и кнопки уже отправленного сообщения бота."""
    params = dict(
        peer_id=peer_id,
        conversation_message_id=conversation_message_id,
        message=text,
        dont_parse_links=1,
    )
    if keyboard:
        params["keyboard"] = keyboard
    vk.messages.edit(**params)


def answer_event(vk, event_id: str, user_id: int, peer_id: int, text: str = None) -> None:
    """Отвечает на нажатие кнопки (иначе у кнопки будет бесконечная загрузка).
    text - всплывающая подсказка (до 90 символов)."""
    params = dict(event_id=event_id, user_id=user_id, peer_id=peer_id)
    if text:
        params["event_data"] = json.dumps(
            {"type": "show_snackbar", "text": text[:90]}, ensure_ascii=False
        )
    vk.messages.sendMessageEventAnswer(**params)


def get_owner_id(vk, peer_id: int):
    resp = vk.messages.getConversationsById(peer_ids=peer_id)
    items = resp.get("items", [])
    if items:
        return (items[0].get("chat_settings") or {}).get("owner_id")
    return None


def can_manage(vk, peer_id: int, uid: int) -> bool:
    """Кто может менять настройки: админы/владельцы бота и владелец беседы."""
    if is_admin(uid):
        return True
    try:
        return get_owner_id(vk, peer_id) == uid
    except ApiError:
        return False


START_WORDS = {"старт", "start"}
STOP_WORDS = {"стоп", "stop"}
AF_WORDS = {"af", "аф"}  # латиницей и кириллицей
SETTING_WORDS = {"setting", "settings", "настройки", "настройка"}

ADDOWNER_WORDS = {"addowner", "добавитьвладельца", "добавьвладельца"}
ADDADMIN_WORDS = {"addadmin", "добавитьадмина", "добавьадмина"}
REMOVEOWNER_WORDS = {"removeowner", "удалитьвладельца", "удаливладельца"}
REMOVEADMIN_WORDS = {"removeadmin", "удалитьадмина", "удалиадмина"}
ADMINS_LIST_WORDS = {"admins"}


# ---------------------- кнопки и экраны ----------------------
LINE = "━━━━━━━━━━━━━━━━━━"


def cb_button(label: str, payload: dict, color: str = "secondary") -> dict:
    """Кнопка, встроенная в сообщение. color: primary, secondary, positive, negative."""
    return {
        "action": {
            "type": "callback",
            "label": label[:40],
            "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
        "color": color,
    }


def make_keyboard(rows: list) -> str:
    return json.dumps({"inline": True, "buttons": rows}, ensure_ascii=False)


def af_menu_screen() -> tuple[str, str]:
    """Сообщение «Какой раздел хотите проверить?» с кнопками разделов."""
    text = (
        "⚜️ ПРОВЕРКА ПРОСРОЧЕК\n"
        f"{LINE}\n\n"
        "Какой раздел хотите проверить?\n\n"
        "👇 Выберите раздел кнопкой ниже"
    )
    buttons = [
        cb_button(sec["button"], {"c": "af", "s": key}, "primary")
        for key, sec in SECTIONS.items()
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]  # по две кнопки в ряд
    return text, make_keyboard(rows)


def settings_screen(peer_id: int) -> tuple[str, str]:
    """Главный экран /setting."""
    st = get_settings(peer_id)
    pinned = st["pinned"]
    hours = float(st["deadline"])
    if pinned:
        pin_line = f"✅ Включено → «{SECTIONS[st['section']]['button']}»"
    else:
        pin_line = "❌ Выключено (бот спрашивает раздел)"
    text = (
        "⚙️ НАСТРОЙКИ БОТА\n"
        f"{LINE}\n\n"
        "📌 Сделать раздел постоянным\n"
        "(не спрашивать раздел каждый раз при /af)\n"
        f"Сейчас: {pin_line}\n"
        "Нажмите «Да», чтобы выбрать раздел\n\n"
        "⏱ Срок рассмотрения (часов)\n"
        "(через сколько часов обращение считается просроченным)\n"
        f"Сейчас: {hours:g} ч.\n\n"
        f"{LINE}\n"
        "👇 Нажмите кнопку, чтобы изменить"
    )
    rows = [
        [
            cb_button("✅ Да" if pinned else "Да", {"c": "pin", "v": 1},
                      "positive" if pinned else "secondary"),
            cb_button("Нет" if pinned else "✅ Нет", {"c": "pin", "v": 0},
                      "secondary" if pinned else "negative"),
        ],
        [
            cb_button(f"✅ {h}" if float(h) == hours else f"{h}", {"c": "dl", "v": h},
                      "primary" if float(h) == hours else "secondary")
            for h in DEADLINE_CHOICES
        ],
    ]
    return text, make_keyboard(rows)


def sections_screen(peer_id: int) -> tuple[str, str]:
    """Экран «Настройки разделов» (после нажатия «Да»)."""
    st = get_settings(peer_id)
    current = SECTIONS[st["section"]]["button"] if st["pinned"] else "не выбран"
    text = (
        "📂 НАСТРОЙКИ РАЗДЕЛОВ\n"
        f"{LINE}\n\n"
        "Выберите раздел, просрочки которого бот будет\n"
        "показывать сразу по команде /af.\n\n"
        f"Сейчас выбран: {current}\n\n"
        "👇 Выберите раздел кнопкой ниже"
    )
    buttons = []
    for key, sec in SECTIONS.items():
        chosen = st["pinned"] and key == st["section"]
        buttons.append(cb_button(
            f"✅ {sec['button']}" if chosen else sec["button"],
            {"c": "sec", "s": key},
            "positive" if chosen else "primary",
        ))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([cb_button("◀ Назад", {"c": "home"}, "secondary")])
    return text, make_keyboard(rows)


shown_screens: dict = {}  # что сейчас показано в сообщении (чтобы не править его одинаково дважды)


def show_screen(vk, peer_id: int, cmid, screen: tuple[str, str]) -> None:
    """Обновляет сообщение с настройками. Если не вышло - отправляет новое."""
    text, kb = screen
    key = (peer_id, cmid)
    if cmid:
        if shown_screens.get(key) == (text, kb):
            return  # уже так показано
        try:
            edit_vk(vk, peer_id, cmid, text, kb)
            if len(shown_screens) > 500:
                shown_screens.clear()
            shown_screens[key] = (text, kb)
            return
        except ApiError as e:
            log.warning("Не удалось изменить сообщение (%s), отправляю новое", e)
    send_vk(vk, peer_id, text, keyboard=kb)


# ---------------------- запуск проверки /af ----------------------
def start_af(vk, peer_id: int, key: str) -> tuple[bool, str]:
    """Ставит проверку раздела в очередь. Возвращает (запущено, текст-подсказка)."""
    sec = SECTIONS[key]
    if not section_ready(key):
        return False, f"⚠ Ссылка раздела «{sec['button']}» не задана в bot.py"
    now = time.time()
    since = now - last_af.get(("run", peer_id), 0)
    if since < AF_COOLDOWN:
        return False, f"Подождите {int(AF_COOLDOWN - since) + 1} сек."
    last_af[("run", peer_id)] = now
    hours = float(get_settings(peer_id)["deadline"])
    if now - cache.get(key, {}).get("time", 0.0) > CACHE_SECONDS:
        send_vk(vk, peer_id, f"⏳ Проверяю раздел «{sec['button']}», это займёт около минуты...")
    job_queue.put({"type": "af", "peer": peer_id, "section": key, "hours": hours})
    return True, f"⏳ Проверяю раздел «{sec['button']}»..."


def handle_af(vk, peer_id: int, sender_id: int = 0) -> None:
    # админ/владелец может /af в любой беседе, обычный юзер — только в активной
    if not is_admin(sender_id) and peer_id not in get_chats():
        send_vk(vk, peer_id, "Бот выключен в этой беседе. Владелец беседы должен написать «старт».")
        return
    now = time.time()
    if now - last_af.get(("cmd", peer_id), 0) < AF_COOLDOWN:
        return
    last_af[("cmd", peer_id)] = now

    st = get_settings(peer_id)
    if st["pinned"]:
        # раздел выбран постоянно - сразу проверяем его, ничего не спрашивая
        started, text = start_af(vk, peer_id, st["section"])
        if not started:
            send_vk(vk, peer_id, text)
        return
    text, kb = af_menu_screen()
    send_vk(vk, peer_id, text, keyboard=kb)


def handle_settings_cmd(vk, peer_id: int, sender_id: int) -> None:
    if not can_manage(vk, peer_id, sender_id):
        send_vk(vk, peer_id, "⛔ Настройки могут менять только владелец беседы и админы бота.")
        return
    text, kb = settings_screen(peer_id)
    send_vk(vk, peer_id, text, keyboard=kb)


# ---------------------- нажатия на кнопки ----------------------
def process_button(vk, peer_id: int, user_id: int, cmid, payload: dict) -> str | None:
    """Выполняет действие кнопки. Возвращает текст всплывающей подсказки."""
    cmd = payload.get("c")

    # --- кнопки выбора раздела под сообщением /af ---
    if cmd == "af":
        key = payload.get("s")
        if key not in SECTIONS:
            return "Неизвестный раздел"
        if not is_admin(user_id) and peer_id not in get_chats():
            return "Бот выключен в этой беседе"
        return start_af(vk, peer_id, key)[1]

    # --- кнопки настроек ---
    if cmd not in ("pin", "sec", "dl", "home"):
        return None
    if not can_manage(vk, peer_id, user_id):
        return "⛔ Менять настройки может только владелец беседы или админ"
    st = get_settings(peer_id)

    if cmd == "pin":
        if payload.get("v"):  # нажали «Да» - показываем выбор раздела
            show_screen(vk, peer_id, cmid, sections_screen(peer_id))
            return "Выберите раздел"
        if not st["pinned"]:
            return "Уже выбрано"
        update_settings(peer_id, pinned=False)  # нажали «Нет»
        show_screen(vk, peer_id, cmid, settings_screen(peer_id))
        return "Теперь бот будет спрашивать раздел"

    if cmd == "sec":
        key = payload.get("s")
        if key not in SECTIONS:
            return "Неизвестный раздел"
        update_settings(peer_id, pinned=True, section=key)
        show_screen(vk, peer_id, cmid, settings_screen(peer_id))
        return f"✅ Постоянный раздел: {SECTIONS[key]['button']}"

    if cmd == "dl":
        try:
            hours = int(payload.get("v"))
        except (TypeError, ValueError):
            return None
        if hours not in DEADLINE_CHOICES:
            return None
        if float(st["deadline"]) == hours:
            return "Уже выбрано"
        update_settings(peer_id, deadline=hours)
        show_screen(vk, peer_id, cmid, settings_screen(peer_id))
        return f"✅ Срок рассмотрения: {hours} ч."

    if cmd == "home":  # кнопка «Назад»
        show_screen(vk, peer_id, cmid, settings_screen(peer_id))
    return None


def handle_event(vk, ev) -> None:
    """Обработка нажатия на callback-кнопку."""
    peer_id = ev.get("peer_id", 0)
    user_id = ev.get("user_id", 0)
    event_id = ev.get("event_id")
    cmid = ev.get("conversation_message_id")
    payload = ev.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {}

    note = None
    try:
        note = process_button(vk, peer_id, user_id, cmid, payload)
    except Exception:
        log.exception("Ошибка обработки кнопки")
        note = "⚠ Ошибка, попробуйте ещё раз"
    try:
        answer_event(vk, event_id, user_id, peer_id, note)
    except Exception:
        log.warning("Не удалось ответить на нажатие кнопки", exc_info=True)


# --- команды управления доступом ---
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
                             f"Может: /addadmin, /removeadmin, старт/стоп в любой беседе, /af.")
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


def handle_message(vk, msg: dict) -> None:
    peer_id = msg.get("peer_id", 0)
    if peer_id <= 2000000000:  # только беседы, не личка
        return

    sender_id = msg.get("from_id", 0)
    raw = msg.get("text", "")

    # нормализованный текст для определения команды (без @-упоминания сообщества)
    no_mention = re.sub(r"\[club\d+\|[^\]]*\]", "", raw).strip()
    has_slash = no_mention.startswith("/")
    cmd_text = no_mention.lstrip("/").strip().lower()
    parts = cmd_text.split()
    cmd = parts[0] if parts else ""

    # --- команды управления доступом ---
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

    # --- /setting (только со слэшем, чтобы не срабатывало на обычное слово «настройки») ---
    if cmd in SETTING_WORDS and has_slash:
        handle_settings_cmd(vk, peer_id, sender_id)
        return

    # --- /af ---
    if cmd in AF_WORDS:
        handle_af(vk, peer_id, sender_id)
        return

    # --- старт / стоп ---
    if cmd_text not in START_WORDS | STOP_WORDS:
        return

    try:
        owner_id = get_owner_id(vk, peer_id)
    except ApiError as e:
        log.warning("Не удалось определить владельца беседы %s: %s", peer_id, e)
        owner_id = None

    has_privileges = is_admin(sender_id)  # владелец бота и /addadmin-пользователи

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
                    "✅ Бот включён. Буду сообщать о просроченных жалобах "
                    "в разделе обжалований (GROZNY). Выключить - «стоп».")
            log.info("Беседа %s включена", peer_id - 2000000000)
            if AUTO_NOTIFY:
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
                etype = getattr(event.type, "value", event.type)
                if event.type == VkBotEventType.MESSAGE_NEW:
                    try:
                        handle_message(vk, event.message)
                    except Exception:
                        log.exception("Ошибка обработки сообщения")
                elif etype == "message_event":  # нажатие на кнопку под сообщением
                    try:
                        handle_event(vk, event.object)
                    except Exception:
                        log.exception("Ошибка обработки нажатия кнопки")
        except Exception:
            log.exception("Long Poll отвалился, переподключаюсь через 5 сек.")
            time.sleep(5)


# ---------------------- проверка форума ----------------------
def notify_chat(vk, chat_id: int, items: list, st: dict, now: float) -> None:
    total = len(items)
    items = items[:MAX_PER_RUN]
    header = (
        f"⚠ Просроченные жалобы в разделе обжалований (GROZNY) - {total} шт.\n"
        f"Срок рассмотрения: {fmt_duration(DEADLINE_HOURS * 3600)}"
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
    """Автоматическая проверка (AUTO_NOTIFY=1). Следит только за разделом обжалований."""
    chats = get_chats()
    if not chats:
        log.info("Нет включённых бесед (владелец беседы должен написать «старт»)")
        return

    sec = SECTIONS["appeal"]
    now = time.time()
    threads = fetch_threads(browser, sec["url"])
    log.info("Получено тем: %d", len(threads))

    from collections import Counter
    prefixes = Counter(t["prefix"] or "(без префикса)" for t in threads)
    log.info("Префиксы в разделе: %s", dict(prefixes.most_common(12)))

    pending_ids = set()
    overdue_items = []
    n_too_old = n_not_yet = 0
    for th in threads:
        if not is_pending(th, sec["prefixes"]):
            continue
        pending_ids.add(th["id"])
        age = now - th["created"]
        if MAX_AGE_DAYS and age > MAX_AGE_DAYS * 86400:
            n_too_old += 1
            continue
        overdue = age - DEADLINE_HOURS * 3600
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
                notify_chat(vk, chat_id, fresh, st, now)
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


# ---------------------- отчёт по команде /af ----------------------
def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def overdue_rows(threads: list, now: float, prefixes: list, hours: float) -> list:
    rows = []
    for th in threads:
        if not is_pending(th, prefixes):
            continue
        age = now - th["created"]
        if age <= hours * 3600:
            continue
        if MAX_AGE_DAYS and age > MAX_AGE_DAYS * 86400:
            continue
        rows.append((age, th))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def build_messages(rows: list, section: dict, hours: float,
                   with_links: bool = True, per_message: int = 40) -> list:
    head = f"{section['icon']} {section['title']} (>{hours:g}ч)\n\n{SERVER_LABEL}\n"
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
            label = th["prefix"] or th["title"][:30] or "Тема"
            if with_links:
                items.append({
                    "type": "url",
                    "offset": utf16_len(text),
                    "length": utf16_len(label),
                    "url": th["url"],
                })
                text += label + "\n"
            else:
                text += f"{label}\n{th['url']}\n"
        fd = None
        if with_links and items:
            fd = json.dumps({"version": "1", "items": items}, ensure_ascii=False)
        out.append((text.rstrip("\n"), fd))
    return out


def send_report(vk, peer_id: int, rows: list, section: dict, hours: float) -> None:
    try:
        for text, fd in build_messages(rows, section, hours, with_links=True):
            send_vk(vk, peer_id, text, fd)
            time.sleep(0.5)
    except ApiError as e:
        if e.code == 917:
            raise
        log.warning("Не сработало форматирование ссылок (%s), шлю обычным текстом", e)
        for text, _ in build_messages(rows, section, hours, with_links=False):
            send_vk(vk, peer_id, text)
            time.sleep(0.5)


def run_af(browser, vk, peer_id: int, section_key: str, hours: float) -> None:
    sec = SECTIONS[section_key]
    c = cache.setdefault(section_key, {"time": 0.0, "threads": []})
    if time.time() - c["time"] > CACHE_SECONDS:
        threads = fetch_threads(browser, sec["url"])
        if not threads:
            # Пустой результат не запоминаем и честно говорим об этом,
            # иначе неверная ссылка выглядела бы как «просрочек нет»
            send_vk(vk, peer_id,
                    f"⚠ В разделе «{sec['button']}» не найдено ни одной темы.\n"
                    "Проверьте ссылку раздела в bot.py и доступ cookies к этому разделу.")
            return
        c["threads"] = threads
        c["time"] = time.time()
    rows = overdue_rows(c["threads"], time.time(), sec["prefixes"], hours)
    log.info("/af [%s] в беседе %s: просроченных %d", section_key, peer_id - 2000000000, len(rows))
    send_report(vk, peer_id, rows, sec, hours)


def worker_loop(vk) -> None:
    browser = None
    notified = load_json(NOTIFIED_FILE, {})
    next_auto = 0.0
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
            if browser is None and (job["type"] == "af" or get_chats()):
                browser = Browser()
            if job["type"] == "af":
                run_af(browser, vk, peer, job["section"], job["hours"])
            elif get_chats():
                check(browser, vk, notified)
                save_json(NOTIFIED_FILE, notified)
        except Exception as e:
            log.exception("Ошибка: %s", e)
            if browser is not None:
                browser.close()
                browser = None
            stale = "Cookies устарели" in str(e)
            text = ("❗ Бот: cookies форума устарели, обновите cookies.txt." if stale
                    else "⚠ Не удалось получить данные с форума, попробуйте позже.")
            if peer or stale:
                for target in ([peer] if peer else get_chats()):
                    try:
                        send_vk(vk, target, text)
                    except Exception:
                        pass


def main() -> None:
    if not VK_TOKEN:
        raise SystemExit(
            "Не найден токен VK. Задайте переменную окружения VK_TOKEN "
            "или положите токен в файл token.txt рядом с bot.py."
        )
    vk_session = vk_api.VkApi(token=VK_TOKEN, api_version=API_VERSION)
    vk = vk_session.get_api()
    vk_worker = vk_api.VkApi(token=VK_TOKEN, api_version=API_VERSION).get_api()

    ready = [s["button"] for k, s in SECTIONS.items() if section_ready(k)]
    log.info("Бот запущен. Владелец: id%s. Авто-уведомления: %s. Разделы со ссылкой: %s",
             BOT_OWNER_ID, "вкл" if AUTO_NOTIFY else "выкл", ", ".join(ready) or "нет")
    threading.Thread(target=worker_loop, args=(vk_worker,), daemon=True).start()
    listen(vk_session, vk)


if __name__ == "__main__":
    main()
