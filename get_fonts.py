"""
Downloads the fonts used for burned-in captions into ./fonts
Run once:  python get_fonts.py
"""
import os
import urllib.request

BASE = "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts"
FONTS = {
    "NotoSansTamil-Bold.ttf":      BASE + "/NotoSansTamil/full/ttf/NotoSansTamil-Bold.ttf",
    "NotoSansDevanagari-Bold.ttf": BASE + "/NotoSansDevanagari/full/ttf/NotoSansDevanagari-Bold.ttf",
    "NotoSans-Bold.ttf":           BASE + "/NotoSans/full/ttf/NotoSans-Bold.ttf",
}

os.makedirs("fonts", exist_ok=True)
for name, url in FONTS.items():
    dest = os.path.join("fonts", name)
    if os.path.exists(dest) and os.path.getsize(dest) > 10000:
        print("already have", name)
        continue
    print("downloading", name, "...")
    try:
        urllib.request.urlretrieve(url, dest)
        print("   ok:", os.path.getsize(dest), "bytes")
    except Exception as e:
        print("   FAILED:", e)
        print("   Download it by hand from https://fonts.google.com/noto and put it in the fonts folder.")

print("\nFonts folder now has:", os.listdir("fonts"))