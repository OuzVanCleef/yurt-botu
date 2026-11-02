import datetime
import os
import random
import time
import zoneinfo
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.stwdo.de/wohnen/aktuelle-wohnangebote"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
KEYWORD = "einzelapartment"


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
    """Almanya (Berlin) saat dilimine göre izin verilen zaman pencereleri:

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

    # 120 - 300 saniye (2-5 dakika) rastgele bekleme
    wait_seconds = random.randint(120, 300)
    print(
        f"🎲 Aktif zaman penceresindeyiz. Sayfa kontrolünden önce {wait_seconds} saniye ({round(wait_seconds/60, 1)} dk) bekleniyor..."
    )
    time.sleep(wait_seconds)

    print("🚀 Playwright tarayıcısı başlatılıyor...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="de-DE",
        )
        page = context.new_page()

        try:
            print("🔎 Sayfaya gidiliyor...")
            page.goto(URL, wait_until="networkidle", timeout=60000)
            time.sleep(3)  # JS içeriklerinin tam oturması için ek bekleme

            body_text = page.inner_text("body")
            print(f"📄 Sayfa başarıyla yüklendi. (Metin uzunluğu: {len(body_text)})")

            if KEYWORD in body_text.lower():
                print(f"✅ '{KEYWORD}' kelimesi sayfada yakalandı!")

                found_lines = []
                for line in body_text.splitlines():
                    if KEYWORD in line.lower() and line.strip():
                        found_lines.append(line.strip())

                # İlan metinlerini derle
                msg = f"🏠 YENİ İLAN BULUNDU!\n\n"
                msg += "\n• ".join(found_lines[:5])
                msg += f"\n\n🔗 Link: {URL}"

                notify(msg)
            else:
                print(f"❌ İlan metninde '{KEYWORD}' bulunamadı.")

        except Exception as e:
            print("Tarama hatası oluştu:", e)
        finally:
            browser.close()


if __name__ == "__main__":
    check_offers()
