import csv, datetime as dt, os, re, time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; rental-tracker/1.0; +you@example.com)"
}

# Muokkaa nämä vastaamaan hakusivuja
TARGET_URL_OIKOTIE = "https://asunnot.oikotie.fi/vuokra-asunnot"
TARGET_URL_LUMO    = "https://lumo.fi/vuokra-asunnot"

# Säännöt lukujen kaappamiseen
EXTRACTOR = re.compile(r"(\d{2,3}(?:[ \u00A0]\d{3})+|\d{3,})")

def fetch_count(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    nums = [int(re.sub(r"[^\d]", "", m.group(1))) for m in EXTRACTOR.finditer(text)]
    if not nums:
        raise RuntimeError(f"Ei löytynyt lukua: {url}")
    return max(nums)

def main():
    today = dt.date.today().isoformat()
    os.makedirs("data", exist_ok=True)
    csv_path = os.path.join("data", "listings.csv")

    oikotie = fetch_count(TARGET_URL_OIKOTIE)
    time.sleep(2)
    lumo    = fetch_count(TARGET_URL_LUMO)

    new_file = not os.path.exists(csv_path)
    if new_file:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "oikotie", "lumo"])

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([today, oikotie, lumo])

    print(f"{today}: Oikotie={oikotie}, Lumo={lumo}")

if __name__ == "__main__":
    main()
