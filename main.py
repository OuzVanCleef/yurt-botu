import datetime
import os
import random
import time
import zoneinfo
import requests
from bs4 import BeautifulSoup

URL = "https://www.stwdo.de/wohnen/aktuelle-wohnangebote"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
KEYWORD = "einzelapartment"


def notify(msg):
    print(f"📢 Telegram'a gönderiliyor: {msg}")
    if not TOKEN or not CHAT_ID:
        print("❌ HATA: TELEGRAM_TOKEN veya TELEGRAM_CHAT_ID eksik!")
        return
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=15,
        )
        print("Telegram Yanıtı:", res.json())
    except Exception as e:
        print("Telegram hatası:", e)


def is_in_active_window():
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    now = datetime.datetime.now(tz)
    weekday = now.weekday()  # 0: Pzt, 1: Salı, 2: Çar, 3: Per
    hour = now.hour

    # Pazartesi 10:00 -> Salı 12:00
    if weekday == 0 and hour >= 10:
        return True
    if weekday == 1 and hour < 12:
        return True

    # Çarşamba 10:00 -> Perşembe 12:00
    if weekday == 2 and hour >= 10:
        return True
    if weekday == 3 and hour < 12:
        return True

    return False


def check_offers():
    print(
        f"🕒 Şu anki Almanya Saati: {datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Berlin')).strftime('%Y-%m-%d %H:%M:%S')}"
    )

    if not is_in_active_window():
        print("⏰ Aktif izleme saatleri dışındayız!")
        # Test için bildirimi yine de gönderelim
        notify("⚠️ TEST: Bot çalıştı ama zaman penceresi dışında.")
        return

    # Test amacıyla bekleme süresini 5 saniyeye düşürdük
    print("🎲 5 saniye bekleniyor...")
    time.sleep(5)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8",
    }

    try:
        print("🔎 Sayfa taranıyor...")
        response = requests.get(URL, headers=headers, timeout=30)
        print(f"HTTP Durum Kodu: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        body_text = soup.get_text()

        print(f"Sayfadaki toplam karakter sayısı: {len(body_text)}")

        # Aradığımız kelime var mı?
        if KEYWORD in body_text.lower():
            print(f"✅ '{KEYWORD}' kelimesi sayfada bulundu!")

            # Kelimenin geçtiği satırları yakala
            found_lines = []
            for line in body_text.splitlines():
                if KEYWORD in line.lower() and line.strip():
                    found_lines.append(line.strip())

            msg = f"🏠 YENİ İLAN BULUNDU!\n\n"
            msg += "\n".join(found_lines[:5])
            msg += f"\n\n🔗 {URL}"
            notify(msg)
        else:
            print(
                f"❌ '{KEYWORD}' kelimesi sayfa metninde bulunamadı. (Sayfa engellenmiş veya JS ile yükleniyor olabilir)"
            )
            # Test mesajı atalım
            notify(
                f"ℹ️ Bot sayfayı taradı ama '{KEYWORD}' kelimesini bulamadı."
            )

    except Exception as e:
        print("Hata oluştu:", e)
        notify(f"❌ Bot çalıştırma hatası: {e}")


if __name__ == "__main__":
    check_offers()
