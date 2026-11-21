#!/usr/bin/env python3
"""Builds the teaser's soundtrack from timeline.json (written by render.js), so every hit lands on its picture.
   python3 audio.py <timeline.json> <out.wav>
   Everything is synthesised: a pulse that drives the six steps, clicks and chimes for each thing you do, coins, a heartbeat and a riser for the
   cliffhanger, the rip, and the cut to silence. Needs numpy and scipy."""
import sys, json, wave, numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
tl = json.load(open(sys.argv[1])); DUR = tl["dur"]; N = int(DUR * SR) + SR // 2; T = tl["T"]; K = tl["KEYS"]; EV = tl["EV"]
rng = np.random.default_rng(11)
t = np.arange(N) / SR

def bp(x, lo, hi, order=2): return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)
def lp(x, f, order=2): return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)
def hp(x, f, order=2): return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)
def noise(n): return rng.standard_normal(n)
def sm(a, b, x): x = np.clip((x - a) / (b - a), 0, 1); return x * x * (3 - 2 * x)
def kf(tab, x): tab = np.array(tab, float); return np.interp(x, tab[:, 0], tab[:, 1])
def dt(n): return np.arange(n) / SR
L = np.zeros(N); R = np.zeros(N)
def add(at, sig, pan=0.0, gain=1.0):
    i = int(at * SR)
    if i >= N or i + len(sig) <= 0: return
    j = min(N, i + len(sig)); seg = sig[:j - i] * gain; L[i:j] += seg * (1 - max(0, pan)); R[i:j] += seg * (1 + min(0, pan))
def mono(x, pan=0.0, gain=1.0): add(0, x, pan, gain)
def bell(f, secs=.6, dec=.12, amp=.15):
    d = dt(int(secs * SR)); return (np.sin(2 * np.pi * f * d) + .45 * np.sin(2 * np.pi * f * 2.76 * d) + .2 * np.sin(2 * np.pi * f * 5.4 * d)) * np.exp(-d / dec) * np.minimum(1, d * 800) * amp
def pluck(f, secs=.5, dec=.14, amp=.2):
    d = dt(int(secs * SR)); ph = 2 * np.pi * f * d; return (np.sin(ph) + .5 * np.sin(2 * ph) + .25 * np.sin(3 * ph)) * np.exp(-d / dec) * np.minimum(1, d * 600) * amp
def click(amp=.4, f=1400):
    d = dt(int(.05 * SR)); return (np.sin(2 * np.pi * f * d) * np.exp(-d / .012) * .5 + hp(noise(len(d)), 2500) * np.exp(-d / .006) * .35) * amp
def thump(amp, f0=95, f1=42, dec=.11):
    d = dt(int(.55 * SR)); ph = 2 * np.pi * (f1 * d + (f0 - f1) * dec * (1 - np.exp(-d / dec))); e = np.exp(-d / (dec * 1.3)) * np.minimum(1, d * 700)
    mid = np.sin(2.5 * ph + 1) * np.exp(-d / (dec * .55)) * np.minimum(1, d * 900) * .55            # the part a small speaker can actually play
    knock = bp(noise(len(d)), 350, 2600) * np.exp(-d / .012) * .6
    return (np.sin(ph) * e * .8 + mid + knock + lp(noise(len(d)), 220) * np.exp(-d / .02) * .4) * amp
def swoosh(secs=.25, lo=600, hi=7000, amp=.4):
    n = int(secs * SR); d = dt(n); x = d / secs; out = np.zeros(n)
    for k in range(6):
        c = lo * (hi / lo) ** (k / 5); out += bp(noise(n), c * .8, min(c * 1.3, 20000)) * sm(k / 6 - .2, k / 6 + .3, x) * (1 - sm(k / 6 + .3, k / 6 + .8, x))
    return out * np.sin(np.pi * np.clip(x, 0, 1)) * amp * 2.2
def reverb(x, secs=2.2, decay=3.2):
    n = int(secs * SR); d = dt(n); ir = lp(noise(n) * np.exp(-d * decay), 5000); return fftconvolve(x, ir / np.sqrt(np.sum(ir ** 2)), mode="full")[:len(x) + n]

# ---- a drone that never quite resolves, with its notes also two octaves up so a phone speaker can play them
lfo = np.sin(2 * np.pi * .11 * t)
drone = (np.sin(2 * np.pi * (41.2 + .25 * lfo) * t) * .55 + np.sin(2 * np.pi * (55 + .3 * np.sin(2 * np.pi * .07 * t)) * t) * .35 + np.sin(2 * np.pi * 82.4 * t + 1.7 * np.sin(2 * np.pi * .21 * t)) * .22)
drone += np.sin(2 * np.pi * 164.8 * t + .8 * lfo) * .16 + np.sin(2 * np.pi * 110 * t) * .2 + np.sin(2 * np.pi * 247 * t + 1.1 * np.sin(2 * np.pi * .13 * t)) * .07
drone = drone + .5 * np.tanh(3 * drone)
drone *= kf([[0, .12], [3, .2], [3.3, .1], [22.7, .1], [23.5, .4], [25, .55], [28.3, .6]], t) * .8
bed = lp(noise(N), 160) * 3 * kf([[0, .1], [3, .12], [22.8, .1], [25, .45], [28.3, .5]], t)
tension = (np.sin(2 * np.pi * (233 * np.exp(.12 * sm(22.8, 28.3, t)) + 1.2 * lfo) * t) * .08 + np.sin(2 * np.pi * (246.9 * np.exp(.12 * sm(22.8, 28.3, t))) * t) * .08)
tension *= sm(22.8, 24.4, t) * (1 - sm(T["rip"][0] - .18, T["rip"][0] - .02, t)) + sm(T["reveal"][0], T["reveal"][0] + 1.8, t) * .6
mono(drone + bed); mono(tension, gain=.8)

# ---- heartbeat (the cold open, and again from the build to the cut)
for h in tl["HEART"]:
    if h["t"] >= K["cutBlack"]: continue
    add(h["t"], thump(.75 * h["a"] * (.7 + .5 * sm(22, 28, h["t"])), f0=95 - 8 * (h["a"] < 1), f1=44))

# ---- a pulse under the six steps: a soft kick, a hat on the off-beat, a bass note each bar, a minor pentatonic shimmer
s0, s1, beat = T["buy"][0], T["collect"][1], .5
for i, at in enumerate(np.arange(s0, s1 - .01, beat)):
    lvl = .3 + .25 * sm(s0, s1, at); add(at, thump(lvl, 85, 46, .09), 0)
    add(at + beat / 2, bp(noise(int(.03 * SR)), 6000, 12000) * np.exp(-dt(int(.03 * SR)) / .008) * .09, rng.uniform(-.3, .3))
    if i % 4 == 0: add(at, pluck([55, 55, 82.4, 73.4][(i // 4) % 4], .9, .3, .32), 0); add(at, pluck([110, 110, 164.8, 146.8][(i // 4) % 4], .5, .12, .08), .1)
    if i % 8 == 6: add(at, bell([523.25, 587.33, 659.25, 783.99][(i // 2) % 4], .8, .2, .05), rng.uniform(-.5, .5))

# ---- static under everything: loud at the start, thin through the steps, a storm for the last act, nothing at all in the black
hs = hp(noise(N), 1200) * kf([[0, .36], [.5, .18], [1.3, .012], [3.0, .012], [3.1, .06], [3.3, .012], [22.8, .012], [23.8, .18], [25.0, .2], [25.7, .16], [28.2, .3], [28.3, 0], [29.1, 0], [29.3, .012], [33.1, .015], [33.3, .2]], t)
hs[(t >= T["black"][0]) & (t < T["black"][1])] = 0
mono(hs * .9)

# ---- glitch hits
def glitch(a):
    n = int((.09 + .09 * a) * SR); d = dt(n); x = noise(n); step = rng.integers(3, 24); x = np.repeat(x[::step], step)[:n]; x = hp(x, 600) * np.exp(-d * 22)
    return (x + np.sin(2 * np.pi * np.cumsum(np.linspace(5200, 260, n)) / SR) * np.exp(-d * 30) * .5) * .55 * min(1.6, a)
for h in tl["HITS"]:
    if K["cutBlack"] <= h["t"] < T["end"][0] + .3: continue
    q = .45 if T["cards"][0] + .1 < h["t"] < T["collect"][1] else 1.0                # the clean acts get quieter glitches
    add(h["t"], glitch(h["a"]), rng.uniform(-.6, .6), q)
    if h["a"] >= .8 and q == 1.0: add(h["t"], thump(.5 * min(1.2, h["a"]), 70, 38, .09))

# ---- typing: a tiny click for every letter
def tick():
    n = int(.014 * SR); d = dt(n); return bp(noise(n), 1800, 5200) * np.exp(-d / .0025) * 1.5 + np.sin(2 * np.pi * rng.uniform(900, 1500) * d) * np.exp(-d / .004) * .25
for ln in tl["LINES"]:
    last = min(ln["t1"] - .3, DUR)
    for i, ch in enumerate(ln["s"]):
        at = ln["t0"] + i / ln["cps"]
        if ch != " " and at < last: add(at, tick(), rng.uniform(-.2, .2), .3)

# ---- 1. buy a pack: a shimmer as it lands, the click, the money leaving
sh = np.sin(2 * np.pi * np.cumsum(np.linspace(500, 2400, int(.7 * SR))) / SR) * np.hanning(int(.7 * SR)) * .14; add(T["buy"][0] + .05, sh, .2)
add(EV["buyClick"], click(.5)); add(EV["buyClick"] + .05, bell(880, .5, .1, .12)); add(EV["buyClick"] + .22, bell(587, .6, .14, .1))
rise = np.sin(2 * np.pi * np.cumsum(np.linspace(180, 900, int(1.1 * SR))) / SR) * sm(0, 1, dt(int(1.1 * SR))) * .09; add(EV["buyClick"] + .45, rise)

# ---- 2. get cards: the rip, then a chime for each card that gets better
def ripnoise(secs=.8):
    rn = int(secs * SR); d = dt(rn); env = np.exp(-d / .22) * np.minimum(1, d * 120); crackle = (rng.random(rn) > .5) * 2 - 1
    return hp(noise(rn) * (.4 + .6 * np.abs(np.sin(2 * np.pi * 85 * d + rng.uniform(0, 6)))) + crackle * .3 * (rng.random(rn) > .985), 1800) * env * 1.4
add(T["cards"][0], ripnoise(.8), 0, .9); add(T["cards"][0], thump(1.0, 80, 40, .12)); add(T["cards"][0] + .02, glitch(1.0))
notes = [659.25, 783.99, 880.0, 1046.5, 1318.5]
for i, at in enumerate(EV["cardPops"]):
    add(at - .04, swoosh(.2, 700, 6500, .4), -.3 + .15 * i); add(at, bell(notes[i], .9, .18 + .05 * i, .16 + .03 * i), 0); add(at, thump(.35 + .12 * i, 90, 44, .09))
    if i >= 2: add(at, bell(notes[i] / 2, 1.2, .3, .12)); 
    if i >= 3:
        for k in range(5 + 3 * i): add(at + .08 + k * .05, bell(notes[-1] * 2 ** rng.choice([0, 3 / 12, 7 / 12, 1]), .5, .1, .05), rng.uniform(-.8, .8))

# ---- 3. the value goes up: a tone that follows the price, a sparkle at each big milestone
pr = np.array(tl["price"]["v"]); tt = np.arange(0, len(pr) / 30, 1 / SR); price = np.interp(tt, np.arange(len(pr)) / 30, pr); price = lp(price, 14, 1)
fr = 190 * (price / pr[0]) ** .4; ph = 2 * np.pi * np.cumsum(fr) / SR
tone = (np.sin(ph) * .5 + np.sin(2 * ph + .5) * .25 + np.sin(3 * ph) * .12) * sm(0, .5, tt) * (1 - sm(tt[-1] - .1, tt[-1], tt)) * .13
add(tl["price"]["t0"], tone, 0)
for c in EV["cross"]:
    if c: add(c, np.sin(2 * np.pi * np.cumsum(np.linspace(1200, 3600, int(.4 * SR))) / SR) * np.exp(-dt(int(.4 * SR)) / .1) * .14, 0); add(c, bell(1568, .8, .2, .1))

# ---- 4. sell: a click, a register, coins, and a small falling tone for the price that carries on without you
add(EV["sellClick"], click(.55)); add(EV["sellClick"] + .02, thump(.6, 90, 46, .1))
add(EV["sellClick"] + .08, bell(2093, .9, .22, .2)); add(EV["sellClick"] + .2, bell(3136, 1.0, .3, .18))
for k in range(24):
    at = EV["sellClick"] + .15 + k * .035 + rng.uniform(0, .05) + (k ** 1.4) * .01; f = rng.choice([2093, 2637, 3136, 3520, 4186]); add(at, bell(f, .35, .06, .09), rng.uniform(-.8, .8))
fall = np.sin(2 * np.pi * np.cumsum(np.linspace(700, 180, int(.95 * SR))) / SR) * sm(0, .1, dt(int(.95 * SR))) * (1 - sm(.6, .95, dt(int(.95 * SR)))) * .07; add(EV["sellClick"] + .35, fall, .3)

# ---- 5. profit: a swell, a burst, a rain of coins that thins out, and a count that ticks up
p0 = EV["profit"]; add(p0 - .12, swoosh(.35, 400, 9000, .5)); add(p0, thump(.9, 90, 42, .13)); add(p0, bell(1046.5, 1.2, .35, .18)); add(p0 + .05, bell(1568, 1.4, .4, .14))
for k in range(70):
    at = p0 + .05 + (rng.random() ** 1.6) * 1.8; f = rng.choice([2093, 2637, 3136, 3520, 4186]); add(at, bell(f, .35, .06, .09), rng.uniform(-.9, .9))
for k in range(34): add(p0 + .05 + k * .03, np.sin(2 * np.pi * (800 + 1600 * k / 34) * dt(int(.02 * SR))) * np.exp(-dt(int(.02 * SR)) / .006) * .15, 0)

# ---- 6. collect: a soft note for each card, a double chime for the one you pick, and a rising run as it takes off
scale = [523.25, 587.33, 659.25, 783.99, 880.0, 1046.5, 1174.7, 1318.5, 1568.0]
for i, at in enumerate(EV["collectPops"]): add(at, pluck(scale[i], .6, .16, .18), rng.uniform(-.5, .5)); add(at, click(.15, 1800))
add(EV["favClick"], click(.5)); add(EV["favClick"] + .02, bell(1318.5, .9, .2, .18)); add(EV["favClick"] + .13, bell(1760, 1.1, .26, .18)); add(EV["favClick"] + .02, thump(.5))
sk = np.sin(2 * np.pi * np.cumsum(400 * (8 ** (dt(int(1.3 * SR)) / 1.3))) / SR) * sm(0, .5, dt(int(1.3 * SR))) * .12; add(EV["sky"], sk, 0); add(EV["sky"], swoosh(1.2, 500, 9000, .35))
for k in range(26): add(EV["sky"] + k * .045, bell(rng.choice(scale) * 2, .35, .08, .07), rng.uniform(-.8, .8))

# ---- build: a riser made of noise that sweeps up, a pitch that climbs, then nothing for a moment before the rip
a0, a1 = T["build"][0], T["rip"][0]; n = int((a1 - a0) * SR); d = dt(n); x = d / (a1 - a0); sweep = np.zeros(n); parts = 14
for k in range(parts):
    c = 250 * (7000 / 250) ** (k / (parts - 1)); sweep += bp(noise(n), c * .8, min(c * 1.25, 20000), 2) * sm(k / parts - .1, k / parts + .5, x) * (1 - sm(k / parts + .5, k / parts + 1.05, x))
sweep *= x ** 1.6 * 5.5
tone2 = np.sin(2 * np.pi * np.cumsum(110 * (7 ** x)) / SR) * x ** 2 * .22 + np.sin(2 * np.pi * np.cumsum(113 * (7 ** x)) / SR) * x ** 2 * .22
add(a0, (sweep + tone2) * (.55 + .45 * np.sin(2 * np.pi * np.cumsum(2 + 14 * x ** 2) / SR)) * (1 - sm(.965, .995, x)), 0, .85)

# ---- rip, with a long tail
bn = int(2.6 * SR); d = dt(bn)
boom = np.sin(2 * np.pi * (34 + 80 * np.exp(-d / .09)) * d) * np.exp(-d / .75) * .8 + lp(noise(bn), 900) * np.exp(-d / .28) * .9 + np.sin(2 * np.pi * (60 + 140 * np.exp(-d / .05)) * d) * np.exp(-d / .3) * .5 + bp(noise(bn), 200, 3000) * np.exp(-d / .4) * .8
rp = ripnoise(.8); hit = np.concatenate([boom + np.pad(rp, (0, bn - len(rp)))[:bn] * .7, np.zeros(int(2.3 * SR))])
wet = reverb(hit, 2.4, 2.4) * .5; add(T["rip"][0], hit[:int(3.6 * SR)], 0, 1.0); add(T["rip"][0], wet, 0, .35)

# ---- reveal: a pad that opens like a sunrise, bells, the heart going flat out
r0, r1 = T["reveal"][0], T["reveal"][1]; n = int((r1 - r0) * SR); d = dt(n); x = d / (r1 - r0); pad = np.zeros(n); base = 110 * (2 ** (2 / 12 * x))
for mult, a in ((1, .5), (1.5, .35), (2, .3), (3, .22), (4.02, .16), (5.04, .1)): pad += np.sin(2 * np.pi * np.cumsum(base * mult * (1 + .004 * np.sin(2 * np.pi * (4.5 + mult) * d))) / SR + mult) * a
pad *= (sm(0, 2.0, d) * .3 + sm(1.4, 2.8, d) * .35) * .55; add(r0, pad)
for k in range(40):
    at = r0 + rng.uniform(.2, 2.6); f = 880 * 2 ** rng.choice([0, 3 / 12, 7 / 12, 12 / 12, 15 / 12, 19 / 12]); d2 = dt(int(.8 * SR))
    add(at, (np.sin(2 * np.pi * f * d2) + .3 * np.sin(2 * np.pi * f * 2.01 * d2)) * np.exp(-d2 / .18) * .05 * (.5 + .5 * (at - r0) / 2.6), rng.uniform(-.8, .8))

# ---- the cut: nothing at all, then a thin high tone that you are not sure you hear
cut = int(K["cutBlack"] * SR); mask = np.ones(N); mask[cut:int(T["end"][0] * SR)] = 0; L *= mask; R *= mask
d = dt(int(.9 * SR)); add(K["cutBlack"] + .05, np.sin(2 * np.pi * 5600 * d) * .03 * np.exp(-d / .45) * np.minimum(1, d * 60), 0)

# ---- end card: the name lands with a deep thump, and the line is typed over a low held note that never resolves
lg = K["logo"]; add(lg, thump(1.0, 80, 34, .16)); add(lg, glitch(1.0)); d = dt(int(1.4 * SR)); add(lg, lp(noise(len(d)), 800) * np.exp(-d / .5) * .5)
e0 = T["end"][0] + 1.2; n = int((DUR - e0) * SR); d = dt(n); ex = d / (DUR - e0)
add(e0, (np.sin(2 * np.pi * 82.4 * d) * .5 + np.sin(2 * np.pi * 87.3 * d) * .32 + np.sin(2 * np.pi * (164.8 + 2 * ex) * d) * .12 + np.sin(2 * np.pi * 247 * d) * .06) * sm(0, 1.8, d) * (.35 + .4 * ex))
for at in EV["endThumps"]: add(at, thump(.5, 70, 38, .12))

# ---- the last frame collapses
end = int((DUR - .2) * SR); fall = np.ones(N); fall[end:] = np.clip(1 - np.arange(N - end) / (.18 * SR), 0, 1) ** 2
d = dt(int(.2 * SR)); add(DUR - .25, (hp(noise(len(d)), 500) * np.exp(-d / .05) + np.sin(2 * np.pi * np.cumsum(np.linspace(6000, 120, len(d))) / SR) * .6 * np.exp(-d / .06)) * .7, 0)
L *= fall; R *= fall; L[int(DUR * SR):] = 0; R[int(DUR * SR):] = 0

# ---- master: a little glue, a soft clip, peak at -1 dB
st = np.stack([L, R], 1); st = np.tanh(st * 1.15) / np.tanh(1.15); st *= (10 ** (-1 / 20)) / np.abs(st).max(); st = st[:int(DUR * SR)]
w = wave.open(sys.argv[2], "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype("<i2").tobytes()); w.close()
print("wrote", sys.argv[2], round(len(st) / SR, 2), "s, peak", round(float(np.abs(st).max()), 3))
