# scrape_listings.py
# Kerää Oikotie- ja Lumo-vuokra-asuntojen listausmäärät ja tallentaa data/listings.csv

import csv
import datetime as dt
import os
import re
import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; rental-tracker/1.0; +you@example.com)"
}

TARGET_URL_OIKOTIE = "https://asunnot.oikotie.fi/vuokra-asunnot"
TARGET_URL_LUMO = "https://lumo.fi/vuokra-asunnot"

CSV_DIR = "data"
CSV_PATH = os.path.join(CSV_DIR, "listings.csv")

RE_GROUPED_INT = r"\d{1,3}(?:[ \u00A0]?\d{3})+"
RE_PLAIN_INT = r"\d{3,}"

def fetch_soup(url: str, tries: int = 3, delay: float = 2.0) -> BeautifulSoup:
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(delay)
    raise RuntimeError(f"Sivun haku epäonnistui: {url} ({last})")

def _clean_to_int(s: str) -> Optional[int]:
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else None

def find_numbers(text: str) -> List[int]:
    rx_all = re.compile(rf"({RE_GROUPED_INT}|{RE_PLAIN_INT})")
    out: List[int] = []
    for m in rx_all.finditer(text):
        v = _clean_to_int(m.group(1))
        if v is not None:
            out.append(v)
    return out

def choose_reasonable(cands: List[int], lo: int, hi: int) -> Optional[int]:
    xs = [x for x in cands if lo <= x <= hi]
    return max(xs) if xs else None

# ---------- OIKOTIE ----------
def fetch_oikotie_count() -> int:
    soup = fetch_soup(TARGET_URL_OIKOTIE)
    text = soup.get_text(" ", strip=True)
    cands = find_numbers(text)
    val = choose_reasonable(cands, 500, 300_000)
    if val is None:
        raise RuntimeError("Oikotie: ei löytynyt järkevää lukua")
    print(f"[DEBUG] Oikotie candidate max in range -> {val}")
    return val

# ---------- LUMO (täsmäregex otsikosta) ----------
def fetch_lumo_count() -> int:
    soup = fetch_soup(TARGET_URL_LUMO)

    # 1) Yritä suoraan h1/h2: “Hakuehdoillasi löytyi 1 246 asuntoa”
    heading = soup.find(["h1", "h2"], string=re.compile(r"Hakuehdoill?asi löytyi", re.I))
    if heading:
        htext = heading.get_text(" ", strip=True)
        m = re.search(r"Hakuehdoill?asi löytyi\s+([0-9 \u00A0]+)\s+asuntoa", htext, re.I)
        if m:
            val = _clean_to_int(m.group(1))
            if val is not None:
                print(f"[DEBUG] Lumo exact heading match -> '{htext}' -> {val}")
                return val

    # 2) Jos ei löytynyt, etsi koko sivulta sama fraasi
    page_text = soup.get_text(" ", strip=True)
    m2 = re.search(r"Hakuehdoill?asi löytyi\s+([0-9 \u00A0]+)\s+asuntoa", page_text, re.I)
    if m2:
        val = _clean_to_int(m2.group(1))
        if val is not None:
            print(f"[DEBUG] Lumo exact page match -> {val}")
            return val

    # 3) Viimeinen fallback: kohtuullinen numeroalue (mutta EI etsi mitään 'max' temppua)
    cands = find_numbers(page_text)
    val = choose_reasonable(cands, 50, 20_000)
    if val is None:
        raise RuntimeError("Lumo: ei löytynyt järkevää lukua (tai fraasia)")
    print(f"[DEBUG] Lumo fallback candidate -> {val}")
    return val

# ---------- CSV-apurit ----------
def init_csv(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["date", "oikotie", "lumo"])

def read_rows(path: str) -> List[List[str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))

def write_rows(path: str, rows: List[List[str]]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

def main():
    today = dt.date.today().isoformat()
    init_csv(CSV_PATH)

    oikotie = fetch_oikotie_count()
    time.sleep(2)
    lumo = fetch_lumo_count()

    rows = read_rows(CSV_PATH)
    if not rows:
        rows = [["date", "oikotie", "lumo"]]

    # jos viimeinen rivi on tälle päivälle, korvaa se
    if len(rows) >= 2 and rows[-1][0] == today:
        rows[-1] = [today, str(oikotie), str(lumo)]
        write_rows(CSV_PATH, rows)
    else:
        with open(CSV_PATH, "a", newl_
