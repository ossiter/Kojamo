# scrape_listings.py
# Kerää Oikotie- ja Lumo-vuokra-asuntojen listausmäärät ja tallentaa data/listings.csv-tiedostoon

import csv
import datetime as dt
import os
import re
import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

# ---- ASETUKSET ---------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; rental-tracker/1.0; +you@example.com)"
}

# Hakusivut (voit rajata kaupunkiin tms. vaihtamalla näitä URL:eja)
TARGET_URL_OIKOTIE = "https://asunnot.oikotie.fi/vuokra-asunnot"
TARGET_URL_LUMO = "https://lumo.fi/vuokra-asunnot"

# CSV-polku
CSV_DIR = "data"
CSV_PATH = os.path.join(CSV_DIR, "listings.csv")

# -----------------------------------------------------------------------------

# Yleisiä numero-regexeja (välilyönti voi olla tavallinen tai sitova \u00A0)
RE_GROUPED_INT = r"\d{1,3}(?:[ \u00A0]?\d{3})+"  # esim. 29 123 tai 29123
RE_PLAIN_INT = r"\d{3,}"  # varmistetaan ettei aivan pieniä (kuten vuosilukuja) napata

# Fraasit, joiden yhteydestä yritetään poimia kokonaismäärä
COUNT_KEYWORDS = [
    "hakutulosta", "hakutulokset", "ilmoitusta", "ilmoitukset", "asuntoa", "asuntoja", "kohdetta", "kohteet",
    "yhteensä", "kaikkiaan"
]


def fetch_soup(url: str, tries: int = 3, delay: float = 2.0) -> BeautifulSoup:
    """Lataa sivun ja palauttaa BeautifulSoup-olion, tekee muutaman uudelleenyrityksen."""
    last_exc = None
    for i in range(tries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            last_exc = exc
            if i < tries - 1:
                time.sleep(delay)
    raise RuntimeError(f"Sivun haku epäonnistui: {url} ({last_exc})")


def _clean_to_int(s: str) -> Optional[int]:
    """Poista kaikki paitsi numerot ja muunna intiksi. Palauta None jos ei järkevä."""
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def find_candidate_counts(text: str) -> List[int]:
    """
    Etsi tekstistä lukumääräkandidaatteja:
    - fraasin (asuntoa/ilmoitusta/hakutulosta/...) läheltä
    - ' / 12 345 ' -tyyliset "Näytetään 1–24 / 12 345 asuntoa"
    - varalta myös irralliset iso(t) luvut
    """
    candidates: List[int] = []

    # 1) "jotain ... 12 345 asuntoa|ilmoitusta|hakutulosta"
    rx_keywords = re.compile(
        rf"({RE_GROUPED_INT}|{RE_PLAIN_INT})\s*(?:{'|'.join(COUNT_KEYWORDS)})",
        flags=re.IGNORECASE,
    )
    for m in rx_keywords.finditer(text):
        val = _clean_to_int(m.group(1))
        if val is not None:
            candidates.append(val)

    # 2) " / 12 345 " (esim. Näytetään 1–24 / 12 345 asuntoa)
    rx_slash_total = re.compile(
        rf"/\s*({RE_GROUPED_INT}|{RE_PLAIN_INT})\s*(?:{'|'.join(COUNT_KEYWORDS)})?",
        flags=re.IGNORECASE,
    )
    for m in rx_slash_total.finditer(text):
        val = _clean_to_int(m.group(1))
        if val is not None:
            candidates.append(val)

    # 3) Varavaralla: kaikki isohkot luvut
    rx_all = re.compile(rf"({RE_GROUPED_INT}|{RE_PLAIN_INT})")
    for m in rx_all.finditer(text):
        val = _clean_to_int(m.group(1))
        if val is not None:
            candidates.append(val)

    return candidates


def choose_reasonable(cands: List[int], min_ok: int, max_ok: int) -> Optional[int]:
    """Rajaa kandidaatit järkevään väliin ja palauta 'paras' (tässä maksimi)."""
    ok = [x for x in cands if min_ok <= x <= max_ok]
    if not ok:
        return None
    # Usein kokonaismäärä on tekstissä suurin järkevän rangen luku
    return max(ok)


def fetch_oikotie_count() -> int:
    soup = fetch_soup(TARGET_URL_OIKOTIE)
    text = soup.get_text(" ", strip=True)
    cands = find_candidate_counts(text)
    # Oikotien kokomarkkina on yleensä kymmeniä tuhansia (mutta pidetään raja laajana)
    val = choose_reasonable(cands, min_ok=500, max_ok=300_000)
    if val is None:
        raise RuntimeError("Oikotie: ei löytynyt järkevää listausmäärää")
    return val


def fetch_lumo_count() -> int:
    soup = fetch_soup(TARGET_URL_LUMO)
    text = soup.get_text(" ", strip=True)
    cands = find_candidate_counts(text)
    # Lumo-yhtiön omassa haussa tyypillisesti ~500–5000 (jätetään leveä liikkumavara)
    val = choose_reasonable(cands, min_ok=50, max_ok=20_000)
    if val is None:
        # Jos yleishaku ei toimi, yritä etsiä h1/h2:sta erikseen
        headings = " ".join(
            [
                *(tag.get_text(" ", strip=True) for tag in soup.find_all(["h1", "h2"])),
            ]
        )
        cands2 = find_candidate_counts(headings)
        val = choose_reasonable(cands2, min_ok=50, max_ok=20_000)
    if val is None:
        raise RuntimeError("Lumo: ei löytynyt järkevää listausmäärää")
    return val


def init_csv(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "oikotie", "lumo"])


def read_last_row(path: str) -> Optional[List[str]]:
    if not os.path.exists(path):
        return None
    last = None
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header_seen = False
        for row in r:
            if not header_seen:
                header_seen = True
                continue
            last = row
    return last


def main():
    today = dt.date.today().isoformat()
    init_csv(CSV_PATH)

    # Hae luvut
    oikotie = fetch_oikotie_count()
    time.sleep(2)  # pieni viive
    lumo = fetch_lumo_count()

    # Älä duplaa samaa päivää; jos sama päivä löytyy, korvaa viimeinen rivi
    last = read_last_row(CSV_PATH)
    if last and last[0] == today:
        # päivitä viimeisin rivi
        rows = []
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        # rows[0] on header
        rows[-1] = [today, str(oikotie), str(lumo)]
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerows(rows)
    else:
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([today, oikotie, lumo])

    print(f"{today}: Oikotie={oikotie}, Lumo={lumo}")


if __name__ == "__main__":
    main()
