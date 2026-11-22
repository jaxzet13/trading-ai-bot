#!/usr/bin/env python3
"""Scores the collection film (ad3.html) from the cues in timeline.json, so every sound lands on its picture.
   python3 audio3.py <timeline.json> <out.wav>
   Everything is synthesised, in D minor. Each market step in the picture plays a note that climbs with the profit (a price you can hear going up), a quiet
   click is the screen ticking, milestones ($50, $100, $250, $500 and the final one) get a cascade of bells, and when the numbers lock a breath of silence
   comes first so the boom lands. A pad, a pulse and a kick build under it; one synthetic hall carries the big moments. Needs numpy and scipy."""
import sys, json, wave, numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
tl = json.load(open(sys.argv[1])); DUR = tl["dur"]; EV = tl["EV"]; LOCK = tl["LOCK"]; END0 = tl["END0"]
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
def smoothk(tab): return kf(tab, t)
duck = np.ones(N)
for a0, a1 in [(LOCK - .32, LOCK - .005)]:
    duck *= 1 - .97 * (sm(a0, a0 + .08, t) * (1 - sm(a1 - .02, a1 + .02, t)))
CH = {"Dm": [73.42, 110.0, 174.6, 293.7], "Bb": [58.27, 116.5, 174.6, 233.1], "F": [87.31, 130.8, 174.6, 261.6], "Dm2": [73.42, 146.8, 220.0, 349.2]}
PLAN = [("Dm", 0, 6.5), ("Bb", 6.0, 12.8), ("F", 12.3, LOCK + .1), ("Dm2", LOCK - .1, END0 + .3), ("Dm", END0 - .2, DUR + .4)]
padL = np.zeros(N); padR = np.zeros(N)
for name, a, b in PLAN:
    p = pad(CH[name], DUR + .4); env = sm(a, a + .6, t) * (1 - sm(b - .6, b, t)); padL += p * env; padR += np.roll(p, 37) * env
mpad = smoothk([[0, .2], [4, .35], [10, .55], [LOCK - .4, .8], [LOCK + .1, .95], [END0 - .5, .5], [END0, .25], [DUR, .0]])
ML += padL * mpad * duck; MR += padR * mpad * duck
sub = (np.sin(2 * np.pi * 36.71 * t) * .5 + np.sin(2 * np.pi * 73.42 * t) * .26) * smoothk([[0, .2], [5, .35], [LOCK, .8], [END0 - .3, .5], [END0, .2], [DUR, 0]]) * duck
ML += sub * .8; MR += sub * .8
# a pulse and a kick that arrive after the first few seconds and grow with the profit
beat = .5
for k in range(int((END0 - 2.4) / beat)):
    tb = 2.4 + k * beat
    if tb > LOCK - .3 and tb < LOCK + .3: continue
    prog = sm(2.4, LOCK, tb); amp = .35 + .6 * prog; di = duck[min(N - 1, int(tb * SR))]
    put(ML, MR, tb, thump(.6 * amp, 90, 46, .1), 0, di)
    if tb > 6:
        root = 58.27 if tb < 12.3 else 87.31
        for j in range(2): put(ML, MR, tb + j * beat / 2, saw(root * 2, .3, .5 * amp * (1 if j == 0 else .6), .13, 700), 0, di)
    hh = hp(noise(int(.06 * SR)), 7000) * np.exp(-dt(int(.06 * SR)) / .012) * (.12 + .1 * prog); put(ML, MR, tb + beat / 2, hh, .35, di)
    if tb > 9: put(ML, MR, tb + beat / 4, hh * .6, -.3, di); put(ML, MR, tb + beat * .75, hh * .6, .3, di)

# ------------------------------------------------------------------ the cues
PENT = [293.66, 349.23, 392.0, 440.0, 523.25]          # D minor pentatonic; the note a tick plays climbs with the profit
for e in EV:
    k, at, a, p = e["k"], e["t"], e["a"], e["p"]
    if k == "tick":
        fx(at, click(.12 + .1 * abs(a), 2200), 0, 1, .05)
        if a > 0:
            idx = int(p * 13.99); f = PENT[idx % 5] * 2 ** (idx // 5); vol = .08 + .16 * a
            fx(at, bell(f, .8, .22 + .15 * p, vol), ((idx % 3) - 1) * .3, 1, .35); fx(at, pluck(f / 2, .35, .12, vol * .8), 0, 1, .15)
        else: fx(at, pluck(196.0, .4, .16, .1 * abs(a)), -.2, 1, .25)
    elif k == "mile":
        base = [783.99, 987.77, 1174.66, 1318.5, 1567.98, 1975.5, 2349.3, 2637.0]
        for i in range(4 + int(p) * 2): fx(at + i * .05, bell(base[i % 8] * (2 if i > 7 else 1), 1.0, .3, .09 + .03 * p), (-1) ** i * .4, 1, .4)
        fx(at, thump(.4 + .12 * p, 120, 55, .08), 0, 1, .1); fx(at, swoosh(.4, 2000, 11000, .15 + .05 * p, .4), 0, 1, .3)
    elif k == "swap": fx(at - .05, swoosh(.22, 900, 6000, .16 * a, .5), (-1) ** int(at * 7) * .3, 1, .15)
    elif k == "riser": fx(at, riser(p, a), 0, 1, .25)
    elif k == "lock":
        for i, f in enumerate([783.99, 987.77, 1174.66, 1318.5, 1567.98, 1975.5, 2349.3, 2637, 3135.9, 3951]): fx(at + .04 + i * .06, bell(f, 1.4, .45, .13), (-1) ** i * .45, 1, .5)
        fx(at - .1, choir(3.4, .9), 0, 1, .55)
    elif k == "boom": fx(at, boom(a), 0, 1, .55)
    elif k == "whoosh": fx(at - .12, swoosh(.55, 400, 9000, .38 * a, .6), 0, 1, .25)
    elif k == "heart": fx(at, thump(.8 * a, 92, 42, .1), 0, 1, .12); fx(at + .3, thump(.6 * a, 88, 42, .1), 0, 1, .12)

# ------------------------------------------------------------------ the mix
rvL = reverb(RV, seed=1) * .85; rvR = reverb(RV, seed=2) * .85
L = ML * .9 + SL + rvL; R = MR * .9 + SR_ + rvR
out = np.stack([L, R], 1); out = hp(out, 24, 1)
fade = np.minimum(1, (DUR + .4 - t) * 3) * np.minimum(1, t * 400)
out *= fade[:, None]; out = np.tanh(out * 1.25) / np.tanh(1.25); out *= .92 / max(1e-6, np.abs(out).max())
pcm = (out * 32767).astype(np.int16)
with wave.open(sys.argv[2], "wb") as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
rms = [float(np.sqrt(np.mean(out[int(s * SR):int((s + 1) * SR)] ** 2))) for s in range(int(DUR))]
print(f"wrote {sys.argv[2]} {DUR:.1f} s, peak {np.abs(out).max():.3f}; rms by second:", " ".join(f"{x:.2f}" for x in rms))
