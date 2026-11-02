import datetime
import hashlib
import os
import random
import time
import zoneinfo
import requests
from bs4 import BeautifulSoup

URL = "https://www.stwdo.de/wohnen/aktuelle-wohnangebote"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
KEYWORD = "Einzelapartment"


def notify(msg):
    if not TOKEN or not CHAT_ID:
        print("Telegram konfigürasyonu eksik!")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=15,
        )
    except Exception as e:
        print("Telegram hatası:", e)


def is_in_active_window():
    """Almanya (Berlin) saat dilimine göre izin verilen zaman pencerelerini kontrol eder:

    - Pazartesi 10:00 -> Salı 12:00
    - Çarşamba 10:00 -> Perşembe 12:00
    """
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    now = datetime.datetime.now(tz)

    weekday = now.weekday()  # 0: Pazartesi, 1: Salı, 2: Çarşamba, 3: Perşembe
    hour = now.hour

    # Pazartesi 10:00 - Salı 12:00
    if weekday == 0 and hour >= 10:
        return True
    if weekday == 1 and hour < 12:
        return True

    # Çarşamba 10:00 - Perşembe 12:00
    if weekday == 2 and hour >= 10:
        return True
    if weekday == 3 and hour < 12:
        return True

    return False


def check_offers():
    if not is_in_active_window():
        print("⏰ Şu an aktif izleme saatleri dışında. İşlem atlanıyor.")
        return

    # 120 ile 300 saniye (2 - 5 dakika) arasında rastgele bekle
    wait_seconds = random.randint(120, 300)
    print(
        f"🎲 Aktif zaman penceresindeyiz. Sayfa kontrolünden önce {wait_seconds} saniye ({round(wait_seconds/60, 1)} dk) bekleniyor..."
    )
    time.sleep(wait_seconds)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8",
    }

    try:
        print("🔎 Sayfa taranıyor...")
        response = requests.get(URL, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"Siteye erişilemedi, Durum Kodu: {response.status_code}")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        body_text = soup.get_text()

        offers = [
            line.strip()
            for line in body_text.splitlines()
            if KEYWORD.lower() in line.lower() and line.strip()
        ]

        print(f"Bulunan {KEYWORD} sayısı: {len(offers)}")

        if offers:
            details = "\n• ".join(offers[:3])
            notify(
                f"🏠 YENİ İLAN BULUNDU!\n\nBulunan İlanlar:\n• {details}\n\nLink: {URL}"
            )

    except Exception as e:
        print("Hata oluştu:", e)


if __name__ == "__main__":
    check_offers()
