import datetime
import hashlib
import os
import random
import re
import time
import zoneinfo
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.stwdo.de/wohnen/aktuelle-wohnangebote"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Tekli, ikili/üçlü WG ve genel daire anahtar kelimeleri
KEYWORDS = [
    "einzelapartment",
    "einzelapartments",
    "wg",
    "wg-zimmer",
    "wohngemeinschaft",
    "dublette",
    "apartments",
    "zimmer",
]

CACHE_FILE = "seen_offers.txt"


def notify(msg):
    if not TOKEN or not CHAT_ID:
        print("❌ Telegram konfigürasyonu eksik!")
        return
    try:
        clean_msg = msg[:3500]
        res = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": clean_msg},
            timeout=15,
        )
        print(f"Telegram Gönderim Yanıtı: {res.status_code}")
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

    if weekday == 0 and hour >= 10:
        return True
    if weekday == 1 and hour < 12:
        return True
    if weekday == 2 and hour >= 10:
        return True
    if weekday == 3 and hour < 12:
        return True

    return False


def load_seen_hashes():
    """Daha önce bildirilen ilanların hash değerlerini okur."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_seen_hashes(hashes):
    """Görülen ilanların hash değerlerini dosyaya kaydeder."""
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        for h in hashes:
            f.write(f"{h}\n")


def normalize_line_for_hash(line):
    """Rakamları ve değişen kontenjan sayılarını temizleyip ilanın sabit

    kimliğini çıkartır.
    """
    # Tüm sayıları temizle (örneğin '8 verfügbare' ile '7 verfügbare' aynı kabul edilir)
    clean = re.sub(r"\d+", "", line.lower())
    # Fazla boşlukları ve özel karakterleri temizle
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


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

    print("🚀 Playwright tarayıcısı stealth modunda başlatılıyor...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="de-DE",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Webdriver izini gizle
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            print("🔎 Sayfaya gidiliyor...")
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # Çerez (Cookie) Onay Kutusu
            cookie_selectors = [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Ich stimme zu')",
                ".cookie-consent-accept",
                "#uc-btn-accept-banner",
            ]
            for selector in cookie_selectors:
                try:
                    if page.is_visible(selector, timeout=2000):
                        page.click(selector)
                        print(f"🍪 Çerez onayına tıklandı: {selector}")
                        time.sleep(2)
                        break
                except Exception:
                    pass

            # Sayfayı aşağı kaydır
            page.mouse.wheel(0, 1000)
            time.sleep(3)

            body_text = page.inner_text("body")
            print(f"📄 Sayfa metni çekildi. Karakter sayısı: {len(body_text)}")

            seen_hashes = load_seen_hashes()
            new_offers = []
            new_hashes = set()

            for line in body_text.splitlines():
                clean_line = line.strip()
                # Kelimelerden herhangi biri geçiyor mu ve satır anlamlı bir uzunlukta mı?
                if (
                    any(kw in clean_line.lower() for kw in KEYWORDS)
                    and len(clean_line) > 8
                ):
                    # Rakamları temizleyip sadece mekan/ilan kimliğini hash'le
                    normalized = normalize_line_for_hash(clean_line)
                    offer_hash = hashlib.md5(
                        normalized.encode("utf-8")
                    ).hexdigest()

                    if offer_hash not in seen_hashes:
                        new_offers.append(clean_line)
                        new_hashes.add(offer_hash)

            if new_offers:
                print(
                    f"🔥 {len(new_offers)} Adet YENİ İlan (Einzel/WG) Bulundu!"
                )

                msg = f"🏠 YENİ İLAN BULUNDU!\n\n"
                msg += "\n• ".join(new_offers[:8])
                msg += f"\n\n🔗 Link: {URL}"

                notify(msg)
                save_seen_hashes(new_hashes)
            else:
                print(
                    "ℹ️ Yeni lokasyon/ilan yok. Sitedeki mevcut ilanlar (kontenjan değişmiş olsa bile) önceden bildirildi."
                )

        except Exception as e:
            print("Tarama hatası oluştu:", e)
        finally:
            browser.close()


if __name__ == "__main__":
    check_offers()
