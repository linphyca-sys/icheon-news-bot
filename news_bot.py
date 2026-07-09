# -*- coding: utf-8 -*-
"""
이천 뉴스봇
- 설정한 키워드로 이천시 관련 뉴스를 주기적으로 검색해서 새 기사만 텔레그램으로 전송
- 뉴스 소스: 네이버 뉴스 검색 API
"""

import csv
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

try:
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
except AttributeError:
    pass

BOT_NAME = os.getenv("BOT_NAME", "이천 뉴스봇").strip()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def parse_keyword_line(line: str) -> dict:
    """'검색어 | 제외: a, b | 포함: x, y | 보호: p, q' 형식 파싱."""
    parts = [p.strip() for p in line.split("|")]
    kw = {"query": parts[0], "include": [], "exclude": [], "protect": []}
    for part in parts[1:]:
        if ":" not in part:
            continue
        label, words = part.split(":", 1)
        words = [w.strip() for w in words.split(",") if w.strip()]
        if label.strip() in ("제외", "exclude"):
            kw["exclude"] = words
        elif label.strip() in ("포함", "include"):
            kw["include"] = words
        elif label.strip() in ("보호", "protect"):
            kw["protect"] = words
    return kw


KEYWORDS = [
    parse_keyword_line(k.strip())
    for k in os.getenv("KEYWORDS", "").split(",")
    if k.strip()
]
if not KEYWORDS:
    kw_file = BASE_DIR / "keywords.txt"
    if kw_file.exists():
        KEYWORDS = [
            parse_keyword_line(line.strip())
            for line in kw_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]


def passes_filter(article: dict, kw: dict) -> bool:
    """제외 단어가 있으면 탈락, 보호 단어가 함께 있으면 통과. 포함 단어가 지정됐으면 하나는 있어야 통과."""
    text = f"{article['title']} {article['description']}"
    if any(w in text for w in kw["exclude"]) and not any(w in text for w in kw["protect"]):
        return False
    if kw["include"] and not any(w in text for w in kw["include"]):
        return False
    return True


INTERVAL_MINUTES = float(os.getenv("INTERVAL_MINUTES", "10"))
MAX_PER_KEYWORD = int(os.getenv("MAX_PER_KEYWORD", "0"))
FIRST_RUN_SEND = int(os.getenv("FIRST_RUN_SEND", "0"))
MAX_AGE_HOURS = float(os.getenv("MAX_AGE_HOURS", "36"))
NAVER_DISPLAY = 100
NAVER_MAX_START = int(os.getenv("NAVER_MAX_START", "1000"))

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "").strip()
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "").strip()

SEEN_FILE = BASE_DIR / "seen_links.json"
CSV_FILE = BASE_DIR / "articles.csv"
KST = timezone(timedelta(hours=9))


def log_to_csv(keyword: str, article: dict) -> None:
    new_file = not CSV_FILE.exists()
    with CSV_FILE.open("a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["전송시각", "검색어", "기사시각", "제목", "요약", "링크"])
        writer.writerow([
            datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            keyword,
            article["published"].strftime("%Y-%m-%d %H:%M"),
            article["title"],
            article["description"],
            article["link"],
        ])


def load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_seen(seen: dict) -> None:
    if len(seen) > 3000:
        items = sorted(seen.items(), key=lambda x: x[1])[-2000:]
        seen = dict(items)
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")


def clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    for _ in range(3):
        unescaped = html.unescape(s)
        if unescaped == s:
            break
        s = unescaped
    return s.strip()


def _og_meta(head: str, prop: str):
    for pattern in (
        re.compile(rf'<meta[^>]+property=["\']og:{prop}["\'][^>]+content=(["\'])(?P<v>.*?)\1', re.I),
        re.compile(rf'<meta[^>]+content=(["\'])(?P<v>.*?)\1[^>]+property=["\']og:{prop}["\']', re.I),
    ):
        m = pattern.search(head)
        if m:
            value = clean_text(m.group("v"))
            if value:
                return value
    return None


def strip_site_name(title: str, site_name) -> str:
    if not site_name:
        return title
    m = re.match(r"^(.*\S)\s*[|\-–—:]\s*(.+?)$", title)
    if m and m.group(2).strip().lower() == site_name.strip().lower():
        return m.group(1).strip(" |-–—:")
    return title


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _fetch_og_title(url: str):
    try:
        resp = requests.get(url, timeout=10, stream=True, headers=BROWSER_HEADERS)
        if not resp.ok:
            resp.close()
            return None
        chunk = next(resp.iter_content(65536), b"") or b""
        resp.close()
    except requests.RequestException:
        return None
    for enc in ("utf-8", "euc-kr"):
        head = chunk.decode(enc, errors="ignore")
        title = _og_meta(head, "title")
        if title:
            return strip_site_name(title, _og_meta(head, "site_name"))
    return None


def fetch_full_title(article: dict):
    title = _fetch_og_title(article["link"])
    if title:
        return title
    naver_link = article.get("naver_link")
    if naver_link and naver_link != article["link"]:
        title = _fetch_og_title(naver_link)
        if title:
            return title
    print(f"  [!] 제목 복원 실패: {article['link']}")
    return None


def search_naver(keyword: str, cutoff=None) -> list:
    articles = []
    for start in range(1, NAVER_MAX_START + 1, NAVER_DISPLAY):
        resp = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": keyword, "display": NAVER_DISPLAY, "sort": "date", "start": start},
            headers={
                "X-Naver-Client-Id": NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            timeout=15,
        )
        resp.raise_for_status()
        page_articles = []
        for item in resp.json().get("items", []):
            try:
                pub = parsedate_to_datetime(item["pubDate"]).astimezone(KST)
            except (KeyError, ValueError, TypeError):
                pub = datetime.now(KST)
            page_articles.append({
                "title": clean_text(item.get("title")),
                "description": clean_text(item.get("description")),
                "link": item.get("originallink") or item.get("link"),
                "naver_link": item.get("link"),
                "published": pub,
            })
        articles.extend(page_articles)
        if len(page_articles) < NAVER_DISPLAY:
            break
        if cutoff and page_articles and page_articles[-1]["published"] < cutoff:
            break
    return articles


def search_news(keyword: str, cutoff=None) -> list:
    return search_naver(keyword, cutoff)


def format_kst(dt: datetime) -> str:
    ampm = "오전" if dt.hour < 12 else "오후"
    hour12 = dt.hour % 12 or 12
    return f"{dt.year}.{dt.month:02d}.{dt.day:02d}. {ampm} {hour12}:{dt.minute:02d}"


def build_message(keyword: str, article: dict) -> str:
    title = html.escape(article["title"])
    desc = html.escape(article["description"])
    if len(desc) > 300:
        desc = desc[:300] + "..."
    return (
        f"<b>{title}</b>\n\n"
        f"{desc}\n\n"
        f"📅 {format_kst(article['published'])}\n"
        f"🔗 <a href=\"{article['link']}\">뉴스 전문 보기</a>"
    )


def send_telegram(text: str) -> bool:
    for attempt in range(3):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": CHAT_ID,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=30,
            )
            if resp.ok:
                return True
            if resp.status_code == 429:
                wait = resp.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                continue
            print(f"  [!] 텔레그램 전송 실패: {resp.status_code} {resp.text}")
            return False
        except requests.RequestException as e:
            print(f"  [!] 텔레그램 전송 오류 (시도 {attempt + 1}/3): {e}")
            time.sleep(3)
    return False


def check_once(seen: dict, first_run: bool) -> None:
    now = datetime.now(KST).strftime("%H:%M:%S")
    for kw in KEYWORDS:
        cutoff = datetime.now(KST) - timedelta(hours=MAX_AGE_HOURS)
        try:
            articles = search_news(kw["query"], cutoff)
        except Exception as e:
            print(f"[{now}] '{kw['query']}' 검색 실패: {e}")
            continue

        fresh = []
        fresh_links = set()
        for article in articles:
            link = article["link"]
            if link and link not in seen and link not in fresh_links:
                fresh.append(article)
                fresh_links.add(link)
        matched = [a for a in fresh if passes_filter(a, kw)]
        recent = [a for a in matched if a["published"] >= cutoff]
        if first_run:
            limit = FIRST_RUN_SEND if FIRST_RUN_SEND > 0 else None
        else:
            limit = MAX_PER_KEYWORD if MAX_PER_KEYWORD > 0 else None
        to_send = recent[:limit]

        stamp = time.time()
        for a in fresh:
            seen[a["link"]] = stamp

        filtered_out = len(fresh) - len(matched)
        too_old = len(matched) - len(recent)
        print(
            f"[{now}] '{kw['query']}': 새 기사 {len(fresh)}건"
            f" (필터 제외 {filtered_out}건, 오래된 기사 제외 {too_old}건), {len(to_send)}건 전송"
        )
        save_seen(seen)
        for a in reversed(to_send):
            if a["title"].endswith(("...", "…")):
                full_title = fetch_full_title(a)
                if full_title:
                    a["title"] = full_title
            if send_telegram(build_message(kw["query"], a)):
                log_to_csv(kw["query"], a)
            time.sleep(3)


def main() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        sys.exit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 .env에 설정하세요. README 참고")
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        sys.exit("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET을 .env 또는 GitHub Secrets에 설정하세요.")
    if not KEYWORDS:
        sys.exit("KEYWORDS를 .env 또는 keywords.txt에 설정하세요.")

    once = "--once" in sys.argv
    source = "네이버 뉴스 API"
    mode = "1회 실행" if once else f"{INTERVAL_MINUTES}분 주기"
    kw_names = [k["query"] for k in KEYWORDS]
    print(f"{BOT_NAME} 시작 - 소스: {source}, 키워드: {kw_names}, 모드: {mode}")

    seen = load_seen()
    first_run = not seen

    if once:
        check_once(seen, first_run)
        return

    while True:
        try:
            check_once(seen, first_run)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[!] 오류 발생, 다음 주기에 재시도: {e}")
        first_run = False
        time.sleep(INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n뉴스봇 종료")
