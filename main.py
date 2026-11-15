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

KEYWORDS = [
    "einzelapartment",
    "einzelapartments",
    "er-wg",
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
    clean = re.sub(r"\d+", "", text.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def accept_cookies(page):
    button_names = [
        re.compile(r"alle akzeptieren", re.I),
        re.compile(r"akzeptieren", re.I),
        re.compile(r"zustimmen", re.I),
    ]
    for name in button_names:
        try:
            btn = page.get_by_role("button", name=name).first
            if btn.is_visible(timeout=2000):
                btn.click()
                print(f"🍪 Çerez butonu tıklandı: {name.pattern}")
                time.sleep(2)
                return
        except Exception:
            pass

    try:
        clicked = page.evaluate("""() => {
            const uc = document.querySelector('#usercentrics-root');
            if (uc && uc.shadowRoot) {
                const btn = uc.shadowRoot.querySelector('[data-testid="uc-accept-all-button"]');
                if (btn) { btn.click(); return true; }
            }
            return false;
        }""")
        if clicked:
            print("🍪 Shadow DOM çerez onayı geçildi.")
            time.sleep(2)
    except Exception:
        pass


def pass_mosparo_spam_protection(page):
    """Mosparo spam koruma kutusunu işaretler ve asıl sayfa yüklenene kadar bekler."""
    body_text = page.inner_text("body")
    if "spamschutz" in body_text.lower() or "ich akzeptiere" in body_text.lower():
        print("🛡️ Mosparo spam koruması tespit edildi, onay veriliyor...")
        try:
            checkbox_label = page.locator("text=/Ich akzeptiere/i").first
            if checkbox_label.is_visible(timeout=3000):
                checkbox_label.click(force=True)
                print("✅ 'Ich akzeptiere' kutusuna tıklandı.")
            else:
                cb = page.locator("input[type='checkbox']").first
                cb.click(force=True)
                print("✅ Checkbox işaretlendi.")

            print("⏳ Spam doğrulaması ve yönlendirme bekleniyor...")
            for _ in range(20):
                time.sleep(1)
                current_text = page.inner_text("body").lower()
                # Artık 'spamschutz' metni kalktıysa ve asıl sayfa başlığı geldiyse geçilmiş demektir
                if "spamschutz" not in current_text and "freie zimmer" in current_text:
                    print("🔓 Spam koruması başarıyla geçildi, ilan sayfası yüklendi!")
                    time.sleep(2)
                    return True
            print("⚠️ Yönlendirme kontrol süresi tamamlandı, sayfa taranıyor...")
        except Exception as e:
            print(f"❌ Spam koruması tıklama hatası: {e}")
    return False


def check_offers():
    is_first_run = not os.path.exists(CACHE_FILE)
    if is_first_run:
        print("🚀 İlk çalıştırma veya önbellek temizlendi. Başlangıç mesajı atılıyor...")
        notify("🤖 Bot başlatıldı ve hafıza sıfırlandı! İlan takibi aktif.")
        open(CACHE_FILE, "w", encoding="utf-8").close()

    wait_seconds = random.randint(0, 180)
    print(f"🎲 Tarama öncesi {wait_seconds} saniye rastgele bekleniyor...")
    time.sleep(wait_seconds)

    print("🌐 Tarayıcı başlatılıyor...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="de-DE",
            timezone_id="Europe/Berlin",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            print("🔎 Sayfa yükleniyor...")
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            accept_cookies(page)
            pass_mosparo_spam_protection(page)

            page.mouse.wheel(0, 1500)
            time.sleep(3)

            body_text = page.inner_text("body")
            print(f"📄 Çekilen toplam karakter sayısı: {len(body_text)}")

            # Hala spam ekranındaysak dur, ama asıl sayfadaysak karakter sayısına bakmadan devam et
            if "spamschutz" in body_text.lower() or "ich akzeptiere" in body_text.lower():
                print("⚠️ Hala spam ekranında takılı kaldı, çıkılıyor.")
                return

            seen_hashes = load_seen_hashes()
            new_offers = []
            new_hashes = set()

            headings = page.locator("h2, h3, h4").all()
            for heading in headings:
                title = " ".join(heading.inner_text().split())
                if any(kw in title.lower() for kw in KEYWORDS) and len(title) > 5:
                    card_text = heading.locator("xpath=..").inner_text()
                    card_lines = [l.strip() for l in card_text.splitlines() if l.strip()]
                    
                    address = ""
                    for l in card_lines:
                        if l != title and "mehr informationen" not in l.lower() and "€" not in l and "m²" not in l:
                            address = l
                            break

                    full_offer_id = f"{address} | {title}" if address else title
                    offer_hash = hashlib.md5(normalize_for_hash(full_offer_id).encode("utf-8")).hexdigest()

                    if offer_hash not in seen_hashes and offer_hash not in new_hashes:
                        display_text = f"📍 {address}\n🏠 {title}" if address else f"🏠 {title}"
                        new_offers.append(display_text)
                        new_hashes.add(offer_hash)

            if not new_offers and not new_hashes:
                lines = [l.strip() for l in body_text.splitlines() if l.strip()]
                for i, line in enumerate(lines):
                    combined = f"{line} {lines[i+1]}" if i + 1 < len(lines) else line
                    if any(kw in combined.lower() for kw in KEYWORDS):
                        target = line if any(kw in line.lower() for kw in KEYWORDS) else combined
                        offer_hash = hashlib.md5(normalize_for_hash(target).encode("utf-8")).hexdigest()
                        if offer_hash not in seen_hashes and offer_hash not in new_hashes:
                            new_offers.append(f"🏠 {target}")
                            new_hashes.add(offer_hash)

            if new_offers:
                print(f"🔥 {len(new_offers)} adet yeni ilan tespit edildi!")
                msg = "🚨 YENİ YURT İLANI BULUNDU!\n\n"
                msg += "\n\n".join(new_offers[:6])
                msg += f"\n\n🔗 Başvuru Linki: {URL}"
                
                notify(msg)
                save_seen_hashes(new_hashes)
            else:
                print("ℹ️ Yeni ilan bulunamadı veya mevcut ilanlar zaten önbellekte kayıtlı.")

        except Exception as e:
            print("❌ Tarama hatası:", e)
        finally:
            browser.close()


if __name__ == "__main__":
    check_offers()
