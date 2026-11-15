import hashlib
import os
import random
import re
import time
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.stwdo.de/wohnen/aktuelle-wohnangebote"
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CACHE_FILE = "seen_offers.txt"

# Yakalanacak ilan tipleri (Tekli daireler ve 2'li, 3'lü, 5'li vb. WG odaları)
KEYWORDS = [
    "einzelapartment",
    "einzelapartments",
    "er-wg",          # 2er-WG, 3er-WG, 5er-WG gibi tüm varyasyonları yakalar
    "wg-zimmer",
    "wohngemeinschaft",
    "dublette"
]


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
        print(f"Telegram Yanıtı: {res.status_code}")
    except Exception as e:
        print("Telegram hatası:", e)


def load_seen_hashes():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_seen_hashes(hashes):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        for h in hashes:
            f.write(f"{h}\n")


def normalize_for_hash(text):
    """
    Rakamları ve boş oda sayılarını temizler.
    Örn: '8 verfügbare Einzelapartments' -> 'verfügbare einzelapartments'
    Örn: 'Zimmer in 3er-WG' -> 'zimmer in er-wg'
    Böylece kontenjan 8'den 7'ye düşse bile aynı yurt/tip için tekrar bildirim atmaz.
    """
    clean = re.sub(r"\d+", "", text.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def check_offers():
    # 1. İlk başlatma / Önbellek silinmişse bildirim gönder
    is_first_run = not os.path.exists(CACHE_FILE)
    if is_first_run:
        print("🚀 İlk çalıştırma veya önbellek temizlendi. Başlangıç mesajı atılıyor...")
        notify("🤖 Bot başlatıldı ve hafıza sıfırlandı! İlan takibi aktif.")
        # Dosyayı hemen oluştur ki bir sonraki çalışmada tekrar başlatıldı mesajı atmasın
        open(CACHE_FILE, "w", encoding="utf-8").close()

    # 2. Bot tespitini önlemek için 0 - 180 saniye arası rastgele bekleme
    wait_seconds = random.randint(0, 180)
    print(f"🎲 Tarama öncesi {wait_seconds} saniye rastgele bekleniyor...")
    time.sleep(wait_seconds)

    print("🌐 Tarayıcı başlatılıyor...")
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
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            print("🔎 Sayfa yükleniyor...")
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # Çerez onay penceresini geç
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
                        time.sleep(2)
                        break
                except Exception:
                    pass

            page.mouse.wheel(0, 1200)
            time.sleep(3)

            body_text = page.inner_text("body")
            lines = [line.strip() for line in body_text.splitlines() if line.strip()]
            
            seen_hashes = load_seen_hashes()
            new_offers = []
            new_hashes = set()

            for i, line in enumerate(lines):
                lower_line = line.lower()
                if any(kw in lower_line for kw in KEYWORDS) and len(line) > 5:
                    # İlan başlığının hemen üstündeki adres satırını da (varsa) yakala
                    # Görseldeki yapı: Üstte "Iserlohn, Steubenstraße, 14-18", altta başlık var.
                    address_line = lines[i - 1] if i > 0 and len(lines[i - 1]) < 60 else ""
                    
                    # Tekrar kontrolü için adres + başlık birleşimini kullan
                    full_offer_id = f"{address_line} | {line}" if address_line else line
                    offer_hash = hashlib.md5(normalize_for_hash(full_offer_id).encode("utf-8")).hexdigest()

                    if offer_hash not in seen_hashes and offer_hash not in new_hashes:
                        display_text = f"📍 {address_line}\n🏠 {line}" if address_line else f"🏠 {line}"
                        new_offers.append(display_text)
                        new_hashes.add(offer_hash)

            if new_offers:
                print(f"🔥 {len(new_offers)} adet yeni ilan tespit edildi!")
                msg = "🚨 YENİ YURT İLANI BULUNDU!\n\n"
                msg += "\n\n".join(new_offers[:6])
                msg += f"\n\n🔗 Başvuru Linki: {URL}"
                
                notify(msg)
                save_seen_hashes(new_hashes)
            else:
                print("ℹ️ Yeni ilan bulunamadı, mevcut ilanlar zaten önbellekte kayıtlı.")

        except Exception as e:
            print("❌ Tarama hatası:", e)
        finally:
            browser.close()


if __name__ == "__main__":
    check_offers()
