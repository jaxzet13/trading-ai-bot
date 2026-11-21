#!/usr/bin/env python3
"""Builds the teaser's soundtrack from timeline.json (written by render.js), so every hit lines up with the picture.
   python3 audio.py <timeline.json> <out.wav>
   Everything is synthesised: sub drone, heartbeat, static, typing clicks, glitch bursts, a rising bed under the chart, a riser, the rip, the cut to silence."""
import sys, json, numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
tl = json.load(open(sys.argv[1])); DUR = tl["dur"]; N = int(DUR * SR) + SR // 2; T = tl["T"]; K = tl["KEYS"]
rng = np.random.default_rng(7)
t = np.arange(N) / SR

def bp(x, lo, hi, order=2): return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)
def lp(x, f, order=2): return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)
def hp(x, f, order=2): return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)
def noise(n): return rng.standard_normal(n)
def sm(a, b, x): x = np.clip((x - a) / (b - a), 0, 1); return x * x * (3 - 2 * x)
def kf(tab, x): tab = np.array(tab, float); return np.interp(x, tab[:, 0], tab[:, 1])
def add(L, R, at, sig, pan=0.0, gain=1.0):
    i = int(at * SR); 
    if i >= N or i + len(sig) <= 0: return
    j = min(N, i + len(sig)); seg = sig[:j - i] * gain
    l, r = (1 - max(0, pan)), (1 + min(0, pan)); L[i:j] += seg * l; R[i:j] += seg * r
L = np.zeros(N); R = np.zeros(N)
def mono(x, pan=0.0, gain=1.0): add(L, R, 0, x, pan, gain)

# ---- sub drone: three low tones that drift, and a dissonant fifth-less pair that opens up as the film goes on
lfo = np.sin(2 * np.pi * .11 * t)
drone = (np.sin(2 * np.pi * (41.2 + .25 * lfo) * t) * .55 + np.sin(2 * np.pi * (55 + .3 * np.sin(2 * np.pi * .07 * t)) * t) * .35 + np.sin(2 * np.pi * 82.4 * t + 1.7 * np.sin(2 * np.pi * .21 * t)) * .22)
# phone speakers cannot play below about 150 Hz, so the drone also carries the same notes two octaves up and a saturated edge that makes harmonics
drone += np.sin(2 * np.pi * 164.8 * t + .8 * lfo) * .16 + np.sin(2 * np.pi * 110 * t) * .2 + np.sin(2 * np.pi * 247 * t + 1.1 * np.sin(2 * np.pi * .13 * t)) * .07
drone = drone + .5 * np.tanh(3 * drone)
drone *= kf([[0, .12], [3, .22], [8, .3], [18, .38], [23.8, .55], [28, .6]], t) * .8
bed = lp(noise(N), 160) * 3 * kf([[0, .1], [8, .15], [23.8, .45], [28, .5]], t)
tension = np.sin(2 * np.pi * (233 * np.exp(.12 * sm(8, 28, t)) + 1.2 * lfo) * t) * .08 + np.sin(2 * np.pi * (246.9 * np.exp(.12 * sm(8, 28, t))) * t) * .08
tension *= sm(16, 22, t) * (1 - sm(23.62, 23.78, t)) + sm(24.6, 26.5, t) * .6
mono(drone + bed)
mono(tension, gain=.8)

# ---- heartbeat: lub and dub, each a short falling sine and a thud of filtered noise
def thump(amp, f0=95, f1=42, dec=.11):
    d = np.arange(int(.55 * SR)) / SR; ph = 2 * np.pi * (f1 * d + (f0 - f1) * dec * (1 - np.exp(-d / dec))); e = np.exp(-d / (dec * 1.3)) * np.minimum(1, d * 700)
    mid = np.sin(2.5 * ph + 1) * np.exp(-d / (dec * .55)) * np.minimum(1, d * 900) * .55            # the part a small speaker can actually play
    knock = bp(noise(len(d)), 350, 2600) * np.exp(-d / .012) * .6
    return (np.sin(ph) * e * .8 + mid + knock + lp(noise(len(d)), 220) * np.exp(-d / .02) * .4) * amp
for h in tl["HEART"]:
    if h["t"] >= K["cutBlack"]: continue
    k = sm(0, 24, h["t"]); add(L, R, h["t"], thump(.75 * h["a"] * (.7 + .5 * k), f0=95 - 8 * (h["a"] < 1), f1=44), gain=1)

# ---- static under everything: loud at the very start, quiet in the middle, a storm for the last act
def hiss_env(x): return kf([[0, .36], [.5, .18], [1.3, .012], [3.0, .012], [3.1, .06], [3.3, .012], [8, .012], [15, .02], [17, .05], [18.2, .09], [20.2, .02], [23.8, .2], [24.6, .16], [27.9, .3], [28.0, 0], [29.0, 0], [29.2, .012], [33.2, .015], [33.5, .2]], x)
hs = hp(noise(N), 1200) * hiss_env(t)
hs[(t >= T["black"][0]) & (t < T["black"][1])] = 0
mono(hs * .9)

# ---- glitch hits: a burst of crushed noise and a falling zap
def glitch(a):
    n = int((.09 + .09 * a) * SR); d = np.arange(n) / SR; x = noise(n); step = rng.integers(3, 24); x = np.repeat(x[::step], step)[:n]; x = hp(x, 600) * np.exp(-d * 22)
    zap = np.sin(2 * np.pi * np.cumsum(np.linspace(5200, 260, n)) / SR) * np.exp(-d * 30) * .5
    return (x + zap) * .55 * min(1.6, a)
for h in tl["HITS"]:
    if K["cutBlack"] <= h["t"] < T["end"][0] + .3: continue
    pan = rng.uniform(-.6, .6); add(L, R, h["t"], glitch(h["a"]), pan)
    if h["a"] >= .8: add(L, R, h["t"], thump(.5 * min(1.2, h["a"]), 70, 38, .09))

# ---- typing: a tiny click for every letter
def tick():
    n = int(.014 * SR); d = np.arange(n) / SR; return bp(noise(n), 1800, 5200) * np.exp(-d / .0025) * 1.5 + np.sin(2 * np.pi * rng.uniform(900, 1500) * d) * np.exp(-d / .004) * .25
for ln in tl["LINES"]:
    last = min(ln["t1"] - .3, DUR)
    for i, ch in enumerate(ln["s"]):
        at = ln["t0"] + (i + 1) / ln["cps"] - 1 / ln["cps"]
        if ch != " " and at < last: add(L, R, at, tick(), rng.uniform(-.2, .2), .34)

# ---- pack: a soft rising shimmer as it floats in, a glint on the foil
sh = np.sin(2 * np.pi * np.cumsum(np.linspace(500, 2400, int(.7 * SR))) / SR) * np.hanning(int(.7 * SR)) * .14
add(L, R, T["pack"][0] + .05, sh, .2)
for at in (T["pack"][0] + .85, T["pack"][0] + 1.2, T["pack"][0] + 1.6):
    d = np.arange(int(.5 * SR)) / SR; add(L, R, at, (np.sin(2 * np.pi * 3136 * d) + .4 * np.sin(2 * np.pi * 4700 * d)) * np.exp(-d / .12) * .08, rng.uniform(-.5, .5))

# ---- cards: a slap and a falling pitch for each one, and a stuttering error for the redacted one
for i, at in enumerate((10.0, 10.5, 11.0, 11.5, 12.0)):
    n = int(.12 * SR); d = np.arange(n) / SR; slap = hp(noise(n), 1500) * np.exp(-d / .02) * .5 + np.sin(2 * np.pi * np.cumsum(np.linspace(520, 110, n)) / SR) * np.exp(-d / .05) * .4
    add(L, R, at, slap, -.3 + .15 * i, .8)
for k in range(5):
    d = np.arange(int(.06 * SR)) / SR; add(L, R, 12.12 + k * .075, np.sin(2 * np.pi * 880 * d) * np.exp(-d / .02) * .25 * (k % 2 + .5), 0)

# ---- chart: a tone that follows the price, a little portamento, a sparkle when it jumps
cv = np.array(tl["chartV"]); u0 = T["chart"][0]; tt = np.arange(0, 3.0, 1 / SR); price = np.interp(tt, np.arange(len(cv)) / 100, cv)
price = lp(price, 14, 1); fr = 180 * (price / 10) ** .42; ph = 2 * np.pi * np.cumsum(fr) / SR
tone = (np.sin(ph) * .5 + np.sin(2 * ph + .5) * .25 + np.sin(3 * ph) * .12) * sm(0, .5, tt) * (1 - sm(2.7, 3.0, tt)) * .11
add(L, R, u0, tone, 0)
for at in (13.35, 14.35, 14.85, 15.05, 15.2):
    d = np.arange(int(.4 * SR)) / SR; add(L, R, at, np.sin(2 * np.pi * np.cumsum(np.linspace(1200, 3200, len(d))) / SR) * np.exp(-d / .09) * .12, rng.uniform(-.4, .4))

# ---- bots: ticks that quicken as the log scrolls
u = np.arange(0, 2.6, .0005); sp = np.interp(u / 2.4, [0, 1], [4, 22]); e = np.clip(u / 2.4, 0, 1); sp = 4 + 18 * np.where(e < .5, 2 * e * e, 1 - (-2 * e + 2) ** 2 / 2); top = u * sp; idx = np.floor(top)
for j in np.where(np.diff(idx) > 0)[0]:
    at = T["bots"][0] + u[j]; n = int(.012 * SR); d = np.arange(n) / SR
    add(L, R, at, bp(noise(n), 2500, 7000) * np.exp(-d / .003) * .9 + np.sin(2 * np.pi * 1700 * d) * np.exp(-d / .004) * .15, rng.uniform(-.7, .7), .26)

# ---- sell: a click, then coins
d = np.arange(int(.05 * SR)) / SR; add(L, R, 19.15, np.sin(2 * np.pi * 1400 * d) * np.exp(-d / .012) * .4 + hp(noise(len(d)), 3000) * np.exp(-d / .006) * .3)
for k in range(26):
    at = 19.25 + k * .035 + rng.uniform(0, .05) + (k ** 1.4) * .012; f = rng.choice([2093, 2637, 3136, 3520, 4186]); d = np.arange(int(.35 * SR)) / SR
    add(L, R, at, (np.sin(2 * np.pi * f * d) + .5 * np.sin(2 * np.pi * f * 2.76 * d)) * np.exp(-d / .06) * .1, rng.uniform(-.8, .8))

# ---- build: a riser made of noise that sweeps up, a pitch that climbs, then nothing for a moment before the rip
a0, a1 = T["build"][0], T["rip"][0]; n = int((a1 - a0) * SR); d = np.arange(n) / SR; x = d / (a1 - a0)
sweep = np.zeros(n); parts = 14
for k in range(parts):
    c = 250 * (7000 / 250) ** (k / (parts - 1)); band = bp(noise(n), c * .8, min(c * 1.25, 20000), 2) * sm(k / parts - .1, k / parts + .5, x) * (1 - sm(k / parts + .5, k / parts + 1.05, x))
    sweep += band
sweep *= x ** 1.6 * 5.5
tone2 = np.sin(2 * np.pi * np.cumsum(110 * (7 ** x)) / SR) * x ** 2 * .22 + np.sin(2 * np.pi * np.cumsum(113 * (7 ** x)) / SR) * x ** 2 * .22
trem = .55 + .45 * np.sin(2 * np.pi * np.cumsum(2 + 14 * x ** 2) / SR)
riser = (sweep + tone2) * trem * (1 - sm(.965, .995, x))
add(L, R, a0, riser, 0, .85)

# ---- rip: paper tearing, then a hit with a long tail
def reverb(x, secs=2.2, decay=3.2, wet=1.0):
    n = int(secs * SR); d = np.arange(n) / SR; ir = noise(n) * np.exp(-d * decay); ir = lp(ir, 5000); return fftconvolve(x, ir / np.sqrt(np.sum(ir ** 2)), mode="full")[:len(x) + n] * wet
rn = int(.8 * SR); d = np.arange(rn) / SR; env = (np.exp(-d / .22) * np.minimum(1, d * 120)); crackle = (rng.random(rn) > .5) * 2 - 1
rip = hp(noise(rn) * (.4 + .6 * np.abs(np.sin(2 * np.pi * 85 * d + rng.uniform(0, 6)))) + crackle * .3 * (rng.random(rn) > .985), 1800) * env * 1.4
boom_n = int(2.6 * SR); d = np.arange(boom_n) / SR
boom = np.sin(2 * np.pi * (34 + 80 * np.exp(-d / .09)) * d) * np.exp(-d / .75) * .8 + lp(noise(boom_n), 900) * np.exp(-d / .28) * .9 + np.sin(2 * np.pi * (60 + 140 * np.exp(-d / .05)) * d) * np.exp(-d / .3) * .5 + bp(noise(boom_n), 200, 3000) * np.exp(-d / .4) * .8
hit = np.concatenate([boom + np.pad(rip, (0, boom_n - rn))[:boom_n] * .7, np.zeros(int(2.3 * SR))])
wet = reverb(hit, 2.4, 2.4, .5); add(L, R, T["rip"][0], hit[:int(3.6 * SR)], 0, 1.0); add(L, R, T["rip"][0], wet, 0, .35)

# ---- reveal: a pad that opens like a sunrise, bells, the heart going flat out, then the cut
r0 = T["reveal"][0]; r1 = T["reveal"][1]; n = int((r1 - r0) * SR); d = np.arange(n) / SR; x = d / (r1 - r0)
pad = np.zeros(n); base = 110 * (2 ** (2 / 12 * x))
for mult, a in ((1, .5), (1.5, .35), (2, .3), (3, .22), (4.02, .16), (5.04, .1)):
    vib = 1 + .004 * np.sin(2 * np.pi * (4.5 + mult) * d); pad += np.sin(2 * np.pi * np.cumsum(base * mult * vib) / SR + mult) * a
pad *= (sm(0, 2.2, d) * .3 + sm(1.5, 3.4, d) * .35) * .55
add(L, R, r0, pad, 0, 1)
for k in range(46):
    at = r0 + rng.uniform(.2, 3.3) ** 1.0; f = 880 * 2 ** rng.choice([0, 3 / 12, 7 / 12, 12 / 12, 15 / 12, 19 / 12]); d2 = np.arange(int(.8 * SR)) / SR
    add(L, R, at, (np.sin(2 * np.pi * f * d2) + .3 * np.sin(2 * np.pi * f * 2.01 * d2)) * np.exp(-d2 / .18) * .05 * (.5 + .5 * (at - r0) / 3.4), rng.uniform(-.8, .8))

# ---- the cut: nothing at all, then a thin high tone that you are not sure you hear
cut = int(K["cutBlack"] * SR); mask = np.ones(N); mask[cut:int(T["end"][0] * SR)] = 0; fadein = np.arange(N - int(T["end"][0] * SR)); L *= mask; R *= mask
d = np.arange(int(.9 * SR)) / SR; ring = np.sin(2 * np.pi * 5600 * d) * .03 * np.exp(-d / .45) * np.minimum(1, d * 60)
add(L, R, K["cutBlack"] + .05, ring, 0)

# ---- end card: the name lands with a deep thump, the line is typed over a low held note that never resolves
lg = K["logo"]; add(L, R, lg, thump(1.0, 80, 34, .16), 0, 1); add(L, R, lg, glitch(1.0), 0)
d = np.arange(int(1.4 * SR)) / SR; add(L, R, lg, lp(noise(len(d)), 800) * np.exp(-d / .5) * .5)
e0 = T["end"][0] + 1.2; n = int((DUR - e0) * SR); d = np.arange(n) / SR; ex = d / (DUR - e0)
held = (np.sin(2 * np.pi * 82.4 * d) * .5 + np.sin(2 * np.pi * 87.3 * d) * .32 + np.sin(2 * np.pi * (164.8 + 2 * ex) * d) * .12) * sm(0, 1.8, d) * (.35 + .4 * ex)
add(L, R, e0, held, 0)
for at in (31.75, 32.35):
    d = np.arange(int(.5 * SR)) / SR; add(L, R, at, thump(.5, 70, 38, .12), 0)

# ---- the last frame: it collapses
end = int(33.3 * SR); fall = np.ones(N); fall[end:] = np.clip(1 - np.arange(N - end) / (.18 * SR), 0, 1) ** 2
d = np.arange(int(.2 * SR)) / SR; add(L, R, 33.25, (hp(noise(len(d)), 500) * np.exp(-d / .05) + np.sin(2 * np.pi * np.cumsum(np.linspace(6000, 120, len(d))) / SR) * .6 * np.exp(-d / .06)) * .7, 0)
L *= fall; R *= fall; L[int(DUR * SR):] = 0; R[int(DUR * SR):] = 0

# ---- master: a little glue, a soft clip, peak at -1 dB
st = np.stack([L, R], 1); st = np.tanh(st * 1.15) / np.tanh(1.15); pk = np.abs(st).max(); st *= (10 ** (-1 / 20)) / pk
st = st[:int(DUR * SR)]
import wave
w = wave.open(sys.argv[2], "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype("<i2").tobytes()); w.close()
print("wrote", sys.argv[2], round(len(st) / SR, 2), "s, peak", round(float(np.abs(st).max()), 3))
