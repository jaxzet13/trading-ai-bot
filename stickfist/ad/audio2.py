#!/usr/bin/env python3
"""Scores the landscape film (ad2.html) from the cues in timeline.json, so every sound lands on its picture.
   python3 audio2.py <timeline.json> <out.wav>
   Everything is synthesised, in D minor: a pad that follows the picture's mood, a pulse and a kick that arrive with the pulls, a rising arpeggio under the
   market, and the sound effects the film asks for: heartbeats, risers, booms, whooshes, the tear, card flips, notes, a choir swell, a click and a cascade
   of bells for the sell, slams for the title. A breath of near-silence just before the tear and just before the click is deliberate: the ear leans in.
   One reverb (a synthetic hall, a different one per ear) carries the big moments. Needs numpy and scipy."""
import sys, json, wave, numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
tl = json.load(open(sys.argv[1])); DUR = tl["dur"]; T = tl["T"]; B = tl["B"]; EV = tl["EV"]
N = int((DUR + .4) * SR); rng = np.random.default_rng(23)
t = np.arange(N) / SR

def bp(x, lo, hi, order=2): return sosfilt(butter(order, [lo, min(hi, SR / 2 - 100)], btype="band", fs=SR, output="sos"), x)
def lp(x, f, order=2): return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)
def hp(x, f, order=2): return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)
def noise(n): return rng.standard_normal(n)
def sm(a, b, x): x = np.clip((x - a) / (b - a), 0, 1); return x * x * (3 - 2 * x)
def kf(tab, x): tab = np.array(tab, float); return np.interp(x, tab[:, 0], tab[:, 1])
def dt(n): return np.arange(n) / SR

ML = np.zeros(N); MR = np.zeros(N)          # the music bus
SL = np.zeros(N); SR_ = np.zeros(N)         # sound effects
RV = np.zeros(N)                            # what is sent to the reverb
def put(bus_l, bus_r, at, sig, pan=0.0, gain=1.0):
    i = int(at * SR)
    if i >= N or i + len(sig) <= 0: return
    a = max(0, -i); j = min(N, i + len(sig)); seg = sig[a:j - i] * gain
    bus_l[max(i, 0):j] += seg * (1 - max(0, pan)); bus_r[max(i, 0):j] += seg * (1 + min(0, pan))
def fx(at, sig, pan=0.0, gain=1.0, send=0.0):
    put(SL, SR_, at, sig, pan, gain)
    if send:
        i = max(0, int(at * SR)); j = min(N, int(at * SR) + len(sig)); k0 = i - int(at * SR)
        if j > i: RV[i:j] += sig[k0:k0 + j - i] * gain * send

# ------------------------------------------------------------------ sounds
def thump(amp, f0=95, f1=42, dec=.11):
    d = dt(int(.55 * SR)); ph = 2 * np.pi * (f1 * d + (f0 - f1) * dec * (1 - np.exp(-d / dec))); e = np.exp(-d / (dec * 1.3)) * np.minimum(1, d * 700)
    mid = np.sin(2.5 * ph + 1) * np.exp(-d / (dec * .55)) * np.minimum(1, d * 900) * .55            # the part a small speaker can actually play
    knock = bp(noise(len(d)), 350, 2600) * np.exp(-d / .012) * .6
    return (np.sin(ph) * e * .8 + mid + knock + lp(noise(len(d)), 220) * np.exp(-d / .02) * .4) * amp
def boom(amp):
    n = int(2.6 * SR); d = dt(n); f = 27 + 70 * np.exp(-d / .16); ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-d / 1.0) * np.minimum(1, d * 300); mid = np.sin(2.2 * ph + 1) * np.exp(-d / .22) * .5 + np.sin(4.1 * ph) * np.exp(-d / .09) * .25
    crack = bp(noise(n), 150, 4500) * np.exp(-d / .05) * 1.0; air = lp(noise(n), 700) * np.exp(-d / .55) * .55
    return (body + mid + crack + air) * amp * .75
def swoosh(secs=.4, lo=500, hi=8000, amp=.4, peak=.5):
    n = int(secs * SR); d = dt(n); x = d / secs; out = np.zeros(n)
    for k in range(7):
        c = lo * (hi / lo) ** (k / 6); out += bp(noise(n), c * .75, c * 1.35) * sm(k / 7 - .25, k / 7 + .25, x) * (1 - sm(k / 7 + .25, k / 7 + .75, x))
    return out * (sm(0, peak, x) * (1 - sm(peak, 1, x))) * amp * 2.4
def riser(secs, amp):
    n = int(secs * SR); d = dt(n); x = d / secs
    lo = bp(noise(n), 180, 900) * x ** 1.6 * .6; mi = bp(noise(n), 900, 3500) * x ** 2.2 * .8; hi = bp(noise(n), 3500, 12000) * x ** 3.0 * 1.0
    f = 110 * 8 ** x; ph = 2 * np.pi * np.cumsum(f) / SR; tone = (np.sin(ph) + .4 * np.sin(2 * ph)) * x ** 2.4 * .25
    out = (lo + mi + hi + tone) * np.minimum(1, (secs - d) * 60)
    return out * amp * .9
def bell(f, secs=.9, dec=.25, amp=.15):
    d = dt(int(secs * SR)); return (np.sin(2 * np.pi * f * d) + .45 * np.sin(2 * np.pi * f * 2.76 * d) + .2 * np.sin(2 * np.pi * f * 5.4 * d)) * np.exp(-d / dec) * np.minimum(1, d * 800) * amp
def pluck(f, secs=.5, dec=.14, amp=.2):
    d = dt(int(secs * SR)); ph = 2 * np.pi * f * d; return (np.sin(ph) + .5 * np.sin(2 * ph) + .25 * np.sin(3 * ph)) * np.exp(-d / dec) * np.minimum(1, d * 600) * amp
def saw(f, secs, amp=.2, dec=.18, cut=2600):
    d = dt(int(secs * SR)); x = np.zeros(len(d))
    for h in range(1, 9): x += np.sin(2 * np.pi * f * h * d) / h
    return lp(x, cut) * np.exp(-d / dec) * np.minimum(1, d * 400) * amp
def click(amp=.4, f=1500):
    d = dt(int(.06 * SR)); return (np.sin(2 * np.pi * f * d) * np.exp(-d / .012) * .5 + hp(noise(len(d)), 2500) * np.exp(-d / .006) * .4) * amp
def rip_sound(amp):
    n = int(.7 * SR); d = dt(n); x = d / .7; steps = rng.random(int(.7 / .004)) > .45; am = np.interp(d, np.arange(len(steps)) * .004, steps.astype(float)) ** 1.0
    body = hp(noise(n), 1400) * (.35 + .65 * am) * (1 - sm(.5, 1, x)) * sm(0, .04, x); grit = bp(noise(n), 300, 1200) * am * (1 - sm(.3, .9, x)) * .5
    thud = lp(noise(n), 260) * np.exp(-(d - .3).clip(0) / .08) * sm(.25, .32, d) * .9 + np.sin(2 * np.pi * 52 * d) * np.exp(-(d - .3).clip(0) / .2) * sm(.28, .31, d) * .8
    return (body * .9 + grit + thud) * amp
def sparkle(secs, amp):
    out = np.zeros(int(secs * SR)); k = 0
    for i in range(int(secs * 36)):
        at = rng.random() ** 1.6 * secs; f = rng.choice([2093, 2637, 3136, 3520, 4186, 5274]) * rng.choice([1, 1, 2]); s = bell(f, .5, .09 + .1 * rng.random(), amp * .06 * (1 - at / secs))
        i0 = int(at * SR); out[i0:i0 + len(s)] += s[:len(out) - i0]
    return out
def choir(secs, amp):
    n = int(secs * SR); d = dt(n); x = np.zeros(n); vib = .004 * np.sin(2 * np.pi * 5.2 * d)
    for f, g in [(146.8, 1.0), (220, .8), (293.7, .9), (349.2, .6), (440, .5), (587.3, .3)]:
        for dd in (-1, 0, 1):
            for h in range(1, 6): x += np.sin(2 * np.pi * f * (1 + dd * .0035) * h * d + vib * h * 8) / h * g
    return lp(x, 3200) * (sm(0, .9, d) * (1 - sm(secs - 1.6, secs, d))) * amp * .09
def pad(freqs, dur, bright=.5):
    n = int(dur * SR); d = dt(n); x = np.zeros(n)
    for f in freqs:
        for dd in (-1, 0, 1):
            for h in range(1, 7): x += np.sin(2 * np.pi * f * (1 + dd * .004) * h * d + h * 1.3 * dd) / (h ** 1.15)
    return x * .1
def reverb(x, secs=3.0, decay=2.1, seed=0):
    r = np.random.default_rng(100 + seed); n = int(secs * SR); d = dt(n)
    ir = lp(r.standard_normal(n) * np.exp(-d * decay), 7000) * np.minimum(1, d * 90); ir = np.concatenate([np.zeros(int(.02 * SR)), ir]); return fftconvolve(x, ir / np.sqrt(np.sum(ir ** 2)), mode="full")[:len(x)]

# ------------------------------------------------------------------ the music
# the dips: just before the tear, and just before the click, the music falls away
duck = np.ones(N)
for a0, a1 in [(B["drop"] - .04, B["tear"] - .015), (B["peak"] - .05, B["click"] + .02)]:
    duck *= 1 - .97 * (sm(a0, a0 + .09, t) * (1 - sm(a1 - .02, a1 + .02, t)))
CH = {"Dm": [73.42, 110.0, 174.6, 293.7], "Bb": [58.27, 116.5, 174.6, 233.1], "F": [87.31, 130.8, 174.6, 261.6], "Dm2": [73.42, 146.8, 220.0, 349.2]}
PLAN = [("Dm", 0, B["cut"] + .3), ("Bb", B["card"][0] - .1, B["card"][4] + .1), ("Dm2", B["card"][4] - .1, T["market"][0] + .15), ("F", T["market"][0] - .1, B["sold"] + .2), ("Dm", B["sold"] - .1, T["cta"][1] + .4)]
gain_by_chord = {}
padL = np.zeros(N); padR = np.zeros(N)
for name, a, b in PLAN:
    p = pad(CH[name], DUR + .4); env = sm(a, a + .5, t) * (1 - sm(b - .5, b, t)); padL += p * env; padR += np.roll(p, 37) * env
mpad = kf([[0, .25], [B["land"] - .3, .5], [B["land"], .85], [B["land"] + 1.5, .55], [T["rip"][0] + .1, .5], [B["drop"], .55], [B["tear"], .9], [B["cut"], .5], [B["card"][0], .35], [B["card"][4], .85], [T["market"][0], .5], [B["peak"], .75], [B["sold"], .85], [B["sold"] + 1.5, .3], [T["cta"][0] + 1.2, .8], [T["cta"][1] - 1.6, .9], [T["cta"][1], 0.2]], t)
ML += padL * mpad * duck; MR += padR * mpad * duck
sub = (np.sin(2 * np.pi * 36.71 * t) * .5 + np.sin(2 * np.pi * 73.42 * t + .6 * np.sin(2 * np.pi * .11 * t)) * .28) * kf([[0, .25], [B["land"] - .2, .45], [B["land"], .9], [T["rip"][0], .5], [B["drop"], .5], [B["tear"], 1.0], [B["cut"], .6], [B["card"][0], .55], [B["sold"] + 1.4, .55], [T["cta"][0] + 1, .7], [DUR, .3]], t) * duck
ML += sub * .8; MR += sub * .8
# a pulse and a kick from the first pull, a hat on the off-beat; they thin out when the market peaks
beat = .5
for k in range(int((T["market"][1] - T["pulls"][0]) / beat)):
    tb = T["pulls"][0] + k * beat
    if tb > B["peak"] - .1: break
    if B["drop"] - 1 < tb < B["tear"]: continue
    amp = .55 + .4 * sm(T["pulls"][0], B["card"][4], tb)
    kk = thump(.62 * amp, 90, 46, .1) * np.interp(tb, [0, 1e3], [1, 1]); put(ML, MR, tb, kk, 0, duck[min(N - 1, int(tb * SR))])
    root = {"Bb": 58.27, "Dm2": 73.42, "F": 87.31}["Bb" if tb < B["card"][4] else ("Dm2" if tb < T["market"][0] else "F")]
    for j in range(2):
        tt = tb + j * beat / 2; put(ML, MR, tt, saw(root * 2, .3, .5 * amp * (1 if j == 0 else .6), .13, 700), 0, duck[min(N - 1, int(tt * SR))])
    hh = hp(noise(int(.06 * SR)), 7000) * np.exp(-dt(int(.06 * SR)) / .012) * .16 * amp; put(ML, MR, tb + beat / 2, hh, .35, duck[min(N - 1, int(tb * SR))])
    if tb > T["market"][0]:
        put(ML, MR, tb + beat / 4, hh * .6, -.3, 1); put(ML, MR, tb + beat * .75, hh * .6, .3, 1)

# ------------------------------------------------------------------ the cues
SCALE = [293.66, 349.23, 392.0, 440.0, 523.25]
for e in EV:
    k, at, a, p = e["k"], e["t"], e["a"], e["p"]
    if k == "heart": fx(at, thump(.85 * a, 92, 42, .1), 0, 1, .12)
    elif k == "riser": fx(at, riser(p, a), 0, 1, .25)
    elif k == "boom": fx(at, boom(a), 0, 1, .55); fx(at + .01, bell(1174.7, 1.4, .5, .05 * a), -.3, 1, .6)
    elif k == "whoosh": fx(at - .12, swoosh(.55, 400, 9000, .38 * a, .6), 0, 1, .25)
    elif k == "hit": fx(at, thump(.75 * a, 110, 50, .09), 0, 1, .18); fx(at, click(.25 * a, 1100), 0, 1, .1)
    elif k == "dust": n = int(p * SR); d = dt(n); x = bp(noise(n), 2500, 7000) * (.5 + .5 * np.sin(2 * np.pi * .4 * d)) * sm(0, .8, d) * (1 - sm(p - .5, p, d)) * .05 * a; fx(at, x, 0, 1, .4)
    elif k == "drop": n = int(p * SR); d = dt(n); f = 880 + 1500 * (d / p) ** 2; ph = 2 * np.pi * np.cumsum(f) / SR; x = np.sin(ph) * sm(0, p * .7, d) * .05 * a; fx(at, x, 0, 1, .5)
    elif k == "dropout": n = int(p * SR); d = dt(n); x = np.sin(2 * np.pi * 1760 * d) * sm(0, .15, d) * (1 - sm(p - .1, p, d)) * .04; fx(at, x, 0, 1, .4)
    elif k == "rip": fx(at, rip_sound(a), 0, 1, .3)
    elif k == "sparkle": fx(at, sparkle(p, a), 0, 1, .55)
    elif k == "flip": fx(at - .02, swoosh(.2, 900, 9000, .5 * a, .45), 0, 1, .2); fx(at, hp(noise(int(.05 * SR)), 2800) * np.exp(-dt(int(.05 * SR)) / .012) * .5 * a, 0, 1, 0); fx(at + .15, thump(.35 * a, 130, 70, .06), 0, 1, .1)
    elif k == "note": fx(at, bell(p, 1.1, .4, .2 * a), 0, 1, .5); fx(at, bell(p * 2, .8, .25, .09 * a), .25, 1, .5); fx(at, pluck(p / 2, .5, .16, .22 * a), 0, 1, .2)
    elif k == "choir": fx(at - .1, choir(p, a), 0, 1, .55)
    elif k == "arp":
        tt = at; i = 0
        while tt < at + p:
            prog = (tt - at) / p; step = .22 * (1 - .68 * prog); idx = i % 5 + 5 * (i // 5 // 1 % 3); f = SCALE[i % 5] * 2 ** (min(2, i // 5)) * (1 if prog < .6 else 1) * 2 ** (prog * .5)
            fx(tt, saw(f, .28, (.12 + .12 * prog) * a, .1, 3200), (-1) ** i * .35, 1, .3); fx(tt, hp(noise(int(.03 * SR)), 6000) * np.exp(-dt(int(.03 * SR)) / .006) * (.08 + .1 * prog), (-1) ** i * -.3, 1, 0)
            tt += step; i += 1
    elif k == "click": fx(at, click(.55 * a, 1700), 0, 1, .12)
    elif k == "cash":
        for i, f in enumerate([783.99, 987.77, 1174.66, 1318.5, 1567.98, 1975.5, 2349.3, 2637, 3135.9, 3951]): fx(at + .08 + i * .055, bell(f, 1.0, .3, .12 * a), (-1) ** i * .4, 1, .35)
        b1_ = bell(2093, 1.4, .5, .12 * a); b2_ = bell(3136, 1.0, .3, .08 * a); b1_[:len(b2_)] += b2_; fx(at, b1_, 0, 1, .4); fx(at + .02, swoosh(.5, 3000, 12000, .22 * a, .3), 0, 1, .3)
    elif k == "slam": fx(at, click(.5 * a, 900 + 120 * p), (p % 3 - 1) * .3, 1, .12); fx(at, thump(.4 * a, 150, 70, .05), 0, 1, .08)
    elif k == "sweep": fx(at, swoosh(1.1, 800, 12000, .3 * a, .35), 0, 1, .35)

# ------------------------------------------------------------------ the mix
rvL = reverb(RV, seed=1) * .85; rvR = reverb(RV, seed=2) * .85
L = ML * .9 + SL + rvL; R = MR * .9 + SR_ + rvR
out = np.stack([L, R], 1); out = hp(out, 24, 1)
fade = np.minimum(1, (DUR + .4 - t) * 6) * np.minimum(1, t * 400)               # the cut at the very end, and no click at the start
out *= fade[:, None]; out = np.tanh(out * 1.25) / np.tanh(1.25); out *= .92 / max(1e-6, np.abs(out).max())
pcm = (out * 32767).astype(np.int16)
with wave.open(sys.argv[2], "wb") as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
rms = [float(np.sqrt(np.mean(out[int(s * SR):int((s + 1) * SR)] ** 2))) for s in range(int(DUR))]
print(f"wrote {sys.argv[2]} {DUR:.1f} s, peak {np.abs(out).max():.3f}; rms by second:", " ".join(f"{x:.2f}" for x in rms))
