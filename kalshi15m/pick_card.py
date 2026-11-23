"""Bet-slip images for the Discord feed: one custom-designed PNG per pick, redrawn when it settles.

render(coin, side, price, stake, payout, settles_ts, status="live"|"won"|"lost", pnl=None) -> PNG bytes.
"""
from __future__ import annotations

import io
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2                                    # draw at 2x for crisp text on phones
W, H = 900, 372
FONT_DIR = "/usr/share/fonts/opentype/inter/"
BG, CARD, LINE = (9, 11, 17), (17, 21, 31), (34, 40, 56)
TEXT, MUTED = (240, 243, 248), (130, 139, 160)
STATUS = {"live": ((96, 165, 250), "LIVE"), "won": ((52, 211, 153), "WON"), "lost": ((248, 113, 113), "LOST")}
COIN = {"NEAR": ((0, 236, 151), (20, 20, 20)), "SOL": ((153, 69, 255), (20, 241, 149)),
        "ZEC": ((244, 183, 40), (236, 148, 0)), "BTC": ((247, 147, 26), (255, 190, 90)),
        "ETH": ((98, 126, 234), (160, 175, 255)), "XRP": ((35, 41, 47), (120, 130, 140)),
        "DOGE": ((194, 166, 51), (230, 205, 100)), "HYPE": ((80, 210, 190), (30, 120, 110))}


def _font(weight, size):
    name = {"bold": "Inter-Bold.otf", "semi": "Inter-SemiBold.otf", "med": "Inter-Medium.otf",
            "reg": "Inter-Regular.otf", "black": "InterDisplay-Black.otf"}[weight]
    try:
        return ImageFont.truetype(FONT_DIR + name, size * S)
    except OSError:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size * S)


def _xy(*v):
    return tuple(int(x * S) for x in v)


def render(coin, side, price, stake, payout, settles_ts=None, status="live", pnl=None, today=None, alltime=None):
    accent, word = STATUS[status]
    img = Image.new("RGB", _xy(W, H), BG)
    # soft glow in the status colour behind the card
    glow = Image.new("RGB", img.size, BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse(_xy(-120, -160, 420, 300), fill=tuple(int(c * 0.35) for c in accent))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(90 * S)), 0.9)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(_xy(16, 16, W - 16, H - 16), radius=28 * S, fill=CARD,
                        outline=tuple(int(LINE[k] * 0.6 + accent[k] * 0.4) for k in range(3)), width=2 * S)

    # coin badge
    c1, c2 = COIN.get(coin, ((90, 100, 120), (60, 70, 90)))
    n = 84 * S                                                                     # smooth diagonal blend
    g = Image.new("L", (n, n))
    g.putdata([int(255 * (x + y) / (2 * n - 2)) for y in range(n) for x in range(n)])
    badge = Image.composite(Image.new("RGB", g.size, c2), Image.new("RGB", g.size, c1), g)
    mask = Image.new("L", badge.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, *badge.size), fill=255)
    img.paste(badge, _xy(52, 56), mask)
    d.text(_xy(94, 98), coin[:4], font=_font("black", 22 if len(coin) <= 3 else 18), fill=(255, 255, 255), anchor="mm")

    # header: market + status pill
    d.text(_xy(156, 62), "KALSHI  ·  15-MIN CRYPTO", font=_font("semi", 15), fill=MUTED)
    pill_w = 22 + d.textlength(word, font=_font("bold", 15)) / S + 26
    px = W - 52 - pill_w
    d.rounded_rectangle(_xy(px, 52, W - 52, 86), radius=17 * S, fill=tuple(int(c * 0.18) for c in accent),
                        outline=accent, width=2 * S)
    d.ellipse(_xy(px + 14, 64, px + 24, 74), fill=accent)
    d.text(_xy(px + 32, 69), word, font=_font("bold", 15), fill=accent, anchor="lm")

    # headline: coin + side, price
    d.text(_xy(156, 84), f"{coin}", font=_font("black", 46), fill=TEXT)
    cw = d.textlength(f"{coin}", font=_font("black", 46)) / S
    side_col = (52, 211, 153) if side.upper() == "YES" else (248, 113, 113)
    d.text(_xy(156 + cw + 18, 84), side.upper(), font=_font("black", 46), fill=side_col)
    sw = d.textlength(side.upper(), font=_font("black", 46)) / S
    d.text(_xy(156 + cw + sw + 36, 104), f"@ {price * 100:.0f}¢", font=_font("semi", 26), fill=MUTED)

    # divider + stats
    d.line(_xy(52, 168, W - 52, 168), fill=LINE, width=2 * S)
    if status == "live":
        stats = [("STAKE", f"${stake:.2f}"), ("TO WIN", f"${payout:.2f}"),
                 ("SETTLES", time.strftime("%H:%M UTC", time.gmtime(settles_ts)) if settles_ts else "—")]
    else:
        stats = [("STAKE", f"${stake:.2f}"), ("RETURN", f"${max(stake + (pnl or 0), 0):.2f}"),
                 ("PROFIT", f"{'+' if (pnl or 0) >= 0 else '−'}${abs(pnl or 0):.2f}")]
    colw = (W - 104) / 3
    for i, (k, v) in enumerate(stats):
        x = 52 + i * colw
        d.text(_xy(x, 190), k, font=_font("semi", 14), fill=MUTED)
        col = accent if (status != "live" and k == "PROFIT") else TEXT
        d.text(_xy(x, 214), v, font=_font("bold", 34), fill=col)
        if i:
            d.line(_xy(x - 18, 190, x - 18, 258), fill=LINE, width=2 * S)

    # footer: today's and all-time P&L
    if today is not None or alltime is not None:
        d.rounded_rectangle(_xy(36, 290, W - 36, H - 36), radius=16 * S, fill=(12, 15, 23))
        pos, neg = (52, 211, 153), (248, 113, 113)
        items = [("TODAY", today), ("ALL-TIME", alltime)]
        x = 60
        for label, v in items:
            if v is None:
                continue
            d.text(_xy(x, 318), label, font=_font("semi", 14), fill=MUTED, anchor="lm")
            x += d.textlength(label, font=_font("semi", 14)) / S + 12
            txt = f"{'+' if v >= 0 else '−'}${abs(v):.2f}"
            d.text(_xy(x, 318), txt, font=_font("bold", 20), fill=pos if v >= 0 else neg, anchor="lm")
            x += d.textlength(txt, font=_font("bold", 20)) / S + 40
        d.text(_xy(W - 60, 318), "KALSHI BOT", font=_font("semi", 13), fill=(70, 78, 98), anchor="rm")

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    open(f"{base}/card_live.png", "wb").write(render("NEAR", "no", 0.29, 0.86, 3.00, time.time() + 600, today=4.12, alltime=29.75))
    open(f"{base}/card_won.png", "wb").write(render("SOL", "yes", 0.18, 0.38, 2.00, status="won", pnl=1.62, today=5.74, alltime=31.37))
    open(f"{base}/card_lost.png", "wb").write(render("ZEC", "no", 0.52, 0.54, 1.00, status="lost", pnl=-0.54, today=-1.20, alltime=28.55))
