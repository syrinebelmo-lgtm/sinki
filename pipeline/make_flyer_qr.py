# -*- coding: utf-8 -*-
"""QR flyer → page de téléchargement Sinki."""

import os
import sys

URL = "https://sinki.onrender.com/download"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")


def main():
    try:
        import segno
    except ImportError:
        raise SystemExit("pip3 install segno")
    out_svg = os.path.abspath(os.path.join(ROOT, "flyer-qr.svg"))
    out_png = os.path.abspath(os.path.join(ROOT, "flyer-qr.png"))
    qr = segno.make(URL, error="h")
    qr.save(out_svg, scale=20, dark="#1c2a22", light="#ffffff", border=4)
    try:
        qr.save(out_png, scale=40, dark="#1c2a22", light="#ffffff", border=4)
    except Exception as exc:
        raise SystemExit("png failed (%s). pip3 install pypng" % exc)
    print("qr", URL, "→", out_svg, out_png, flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
