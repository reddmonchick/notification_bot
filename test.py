import time
import csv
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from bs4 import BeautifulSoup
import re
from curl_cffi import requests as curl_requests
import itertools

# -----------------------
# Настройки
# -----------------------
INPUT_XLSX = "inn.xlsx"
OUTPUT_CSV = "phones.csv"
OUTPUT_SQLITE = "phones.db"

THREADS = 1
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

# Если прокси не нужен — оставь None


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    # 'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Referer': 'https://orginfo.uz/',
    'Connection': 'keep-alive',
    # 'Cookie': 'csrftoken=QDD5UPVxuap2mut6QoBbKbvW61zhPuCm; _ga_VT2HDZFHXZ=GS2.1.s1767091223$o5$g1$t1767091318$j53$l0$h0; _ga=GA1.1.1856424547.1766748294; _gcl_au=1.1.341960008.1766748294; _ym_uid=1766748294101940749; _ym_d=1766748294; sessionid=yh6rgiheyp77c0cnna00ixoheo72yp1h; _ym_isad=1; _ym_visorc=w',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Priority': 'u=0, i',
    # Requests doesn't support trailers
    # 'TE': 'trailers',
}


SEARCH_URL = "https://orginfo.uz/search/organizations/?q={inn}"

# -----------------------
# База данных
# -----------------------
def init_sqlite(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS phones (
            inn TEXT NOT NULL,
            phone TEXT,
            status TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_phones_inn ON phones(inn)")
    conn.commit()
    return conn

def write_sqlite(conn, rows):
    cur = conn.cursor()
    cur.executemany("INSERT INTO phones (inn, phone, status) VALUES (?, ?, ?)", rows)
    conn.commit()


# -----------------------
# CSV
# -----------------------
def write_csv_init(csv_path):
    if not Path(csv_path).exists():
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["inn", "phone", "status"])

def write_csv_append(csv_path, rows):
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        for r in rows:
            w.writerow([r[0], r[1] if r[1] else "", r[2] if r[2] else ""])






# -----------------------
# HTTP с ретраями через curl_cffi
# ----------------------

# Список HTTP(S) прокси
import requests
import itertools
import time

# Список HTTP(S) прокси
HTTP_PROXIES = [
    "http://iparchitect_44807_01_01_26:8QTdHHk9294i9EnBbz@188.143.169.27:30014",
    "http://iparchitect_44807_01_01_26:s8s7tDn7ezB3836FBT@188.143.169.27:30151",
    "http://iparchitect_44807_01_01_26:s8s7tDn7ezB3836FBT@188.143.169.27:30020",
    "http://iparchitect_44807_01_01_26:s8s7tDn7ezB3836FBT@188.143.169.27:30021",
]

# Список SOCKS5 прокси (если нужен)
SOCKS_PROXIES = [
    "socks5://iparchitect_44807_01_01_26:8QTdHHk9294i9EnBbz@188.143.169.27:40014",
    "socks5://iparchitect_44807_01_01_26:s8s7tDn7ezB3836FBT@188.143.169.27:40151",
    "socks5://iparchitect_44807_01_01_26:s8s7tDn7ezB3836FBT@188.143.169.27:40020",
    "socks5://iparchitect_44807_01_01_26:s8s7tDn7ezB3836FBT@188.143.169.27:40021",
]

http_cycle = itertools.cycle(HTTP_PROXIES)
socks_cycle = itertools.cycle(SOCKS_PROXIES)

def get_next_proxy(use_socks=False):
    return next(socks_cycle) if use_socks else next(http_cycle)

def request_with_retries(url, max_retries=3, use_socks=False):
    # Таймаут зависит от типа URL
    timeout = 15 if "/search/organizations/" in url else 60

    for attempt in range(1, max_retries + 1):
        proxy = get_next_proxy(use_socks)
        proxies = {"http": proxy, "https": proxy}
        try:
            resp = requests.get(
                url,
                headers=HEADERS,
                proxies=proxies,
                timeout=timeout,
            )
            print(f"[{proxy}] {resp.status_code} {url} (timeout={timeout})")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"[WARN] attempt {attempt} failed via {proxy} and url {url}: {e}")
            time.sleep(attempt * 0.5)
    return None






# -----------------------
# Нормализация и парсинг телефонов
# -----------------------
uz_patterns = [
    # tel: ссылки -> достаём из href
    # Явные международные/локальные формы с кодом Узбекистана
    r"\+?998[\s\-\(\)]?\d{2}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{2}[\s\-\(\)]?\d{2}",
    # Иногда могут быть без +998, как 90-123-45-67 или 712345678
    r"\b\d{2}[\s\-\(\)]?\d{3}[\s\-\(\)]?\d{2}[\s\-\(\)]?\d{2}\b",
    r"\b\d{7,9}\b",
]

def normalize_phone(raw: str):
    s = raw.strip()
    plus = s.startswith("+")
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    # эвристика длины: 9–15 цифр
    if len(digits) < 9 or len(digits) > 15:
        return None
    # если начинается с 998 и длина соответствует, добавим плюс
    if digits.startswith("998") and not plus:
        return "+{}".format(digits)
    return ("+" + digits) if plus else digits

def parse_url(html):
    soup = BeautifulSoup(html, "html.parser")
    #url_org = soup.find("div", class_='d-flex flex-column h-100').find_all('div', class_="col-sm-12 col-md-12 col-lg-10 m-auto")[-1].find_all("div")[2].find("div", class_="py-3").find("a", class_="text-decoration-none og-card")["href"]
    url_org = f'https://orginfo.uz{soup.find("a", class_="text-decoration-none og-card")["href"]}'
    return url_org

def parse_phones(html):
    soup = BeautifulSoup(html, "html.parser")
    phone_tag = soup.find("a", attrs={"itemprop": "telephone"})
    if phone_tag:
        span = phone_tag.find("span")
        if span:
            return span.get_text(strip=True)
        else:
            return phone_tag.get_text(strip=True)
    return None

def parse_status(html):
    soup = BeautifulSoup(html, "html.parser")
    status = soup.find_all("div", class_="row border-bottom py-3")[3].find_all("div",class_="col-6")[-1].find("span").get_text(strip=True)
    print(status, "Статус")
    if status:
        return status
    return None


# -----------------------
# Обработка одного ИНН
# -----------------------
def process_inn(inn):
    url = SEARCH_URL.format(inn=inn)
    try:
        html = request_with_retries(url)
        if not html:
            return [(inn, None, None)]

        try:
            url = parse_url(html)
        except Exception as e:
            return [(inn, None, None)]
        
        try:
            html = request_with_retries(url)
        except Exception as e:
            return [(inn, None, None)]

        try:
            phones = parse_phones(html)
        except Exception as e:
            print(f"[ERROR] parse_phones failed for {inn}: {e}")
            phones = None

        try:
            status = parse_status(html)
        except Exception as e:
            print(f"[ERROR] parse_status failed for {inn}: {e}")
            status = None

        if phones:
            if isinstance(phones, str):
                return [(inn, phones, status)]
            return [(inn, p, status) for p in phones]
        else:
            return [(inn, None, status)]

    except Exception as e:
        print(f"[ERROR] process_inn failed for {inn}: {e}")
        return [(inn, None, None)]



# -----------------------
# Основной пайплайн
# -----------------------
def main():
    df = pd.read_excel(INPUT_XLSX, usecols=[0], dtype=str)
    inn_list = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
    total = len(inn_list)

    conn = init_sqlite(OUTPUT_SQLITE)
    write_csv_init(OUTPUT_CSV)

    processed = 0  # счётчик обработанных

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {executor.submit(process_inn, inn): inn for inn in inn_list}
        for fut in as_completed(futures):
            rows = fut.result()
            print("результат", rows)
            if rows:
                write_sqlite(conn, rows)
                write_csv_append(OUTPUT_CSV, rows)

            processed += 1
            remaining = total - processed
            print(f"[PROGRESS] Обработано: {processed}/{total}, осталось: {remaining}")

    conn.close()
    print("Готово! Результаты сохранены в phones.db и phones.csv")


if __name__ == "__main__":
    main()
