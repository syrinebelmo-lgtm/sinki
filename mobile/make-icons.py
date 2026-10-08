"""Génère icônes et écrans de démarrage iOS/Android depuis resources-icon.png (logo biche)."""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "web", ".pypkgs"))
from PIL import Image  # noqa: E402

src = Image.open(os.path.join(HERE, "resources-icon.png")).convert("RGBA")
bg = src.getpixel((8, 8))[:3]


def flat(img, size):
    canvas = Image.new("RGB", img.size, bg)
    canvas.paste(img, mask=img.split()[3])
    return canvas.resize((size, size), Image.LANCZOS)


# iOS: une icône 1024 sans transparence (refusée sinon).
flat(src, 1024).save(os.path.join(HERE, "ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png"))

# Android : icônes classiques + premier plan adaptatif (zone sûre 66/108).
legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
res = os.path.join(HERE, "android/app/src/main/res")
for dpi, px in legacy.items():
    icon = flat(src, px)
    icon.save(os.path.join(res, "mipmap-" + dpi, "ic_launcher.png"))
    mask = Image.new("L", (px, px), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).ellipse((0, 0, px - 1, px - 1), fill=255)
    rnd = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    rnd.paste(icon, mask=mask)
    rnd.save(os.path.join(res, "mipmap-" + dpi, "ic_launcher_round.png"))
    fg_px = px * 108 // 48
    inner = int(fg_px * 66 / 108)
    fg = Image.new("RGBA", (fg_px, fg_px), (0, 0, 0, 0))
    fg.paste(flat(src, inner), ((fg_px - inner) // 2, (fg_px - inner) // 2))
    fg.save(os.path.join(res, "mipmap-" + dpi, "ic_launcher_foreground.png"))
with open(os.path.join(res, "values/ic_launcher_background.xml"), "w") as fh:
    fh.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#%02X%02X%02X</color>\n</resources>\n' % bg)

# Écrans de démarrage : la biche au centre, même fond que l'icône.
splashes = glob.glob(os.path.join(res, "drawable*/splash.png")) + glob.glob(os.path.join(HERE, "ios/App/App/Assets.xcassets/Splash.imageset/*.png"))
for path in splashes:
    w, h = Image.open(path).size
    canvas = Image.new("RGB", (w, h), bg)
    side = int(min(w, h) * 0.45)
    canvas.paste(flat(src, side), ((w - side) // 2, (h - side) // 2))
    canvas.save(path)
print("icônes OK, fond #%02X%02X%02X, %d écrans de démarrage" % (bg + (len(splashes),)))
