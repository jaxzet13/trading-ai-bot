"""The soundtrack for ad5.html ("made of code"): a low pad, a rising shimmer while each card draws itself, key clicks while the code scrolls, a whoosh and a thud on every cut,
and a soft chord on the end card. Everything is synthesised; nothing is sampled.   python3 audio5.py out.wav"""
import sys
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 44100; DUR = 22.0; N = int(SR * DUR); t = np.arange(N) / SR
rng = np.random.default_rng(5)
CUTS = [3.6, 7.6, 11.4, 15.4, 18.8]
PICS = [(0.0, 3.6), (7.6, 11.4), (15.4, 18.8)]
CODE = [(3.6, 7.6), (11.4, 15.4)]
def bp(x, lo, hi, o=3): return sosfilt(butter(o, [lo, hi], 'band', fs=SR, output='sos'), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x)
def lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x)
def env(a, b, c, d):  # a trapezoid in seconds: rise a..b, hold, fall c..d
    e = np.zeros(N); e += np.clip((t - a) / max(1e-6, b - a), 0, 1) * np.clip((d - t) / max(1e-6, d - c), 0, 1); return np.clip(e, 0, 1)

out = np.zeros(N)
# the pad: A1 and its fifth, slowly breathing
for f, g in ((55, .5), (82.4, .3), (110, .22), (164.8, .12)):
    out += g * np.sin(2 * np.pi * f * t + .4 * np.sin(2 * np.pi * .13 * t)) * (.75 + .25 * np.sin(2 * np.pi * .07 * t + f))
out *= .16 * np.clip(t / 1.5, 0, 1) * np.clip((DUR - t) / 1.2, 0, 1)
# the draw: a shimmer that climbs while the letters appear, and a bright tick for every row
for a, b in PICS:
    e = env(a, b - .5, b - .5, b); noise = bp(rng.standard_normal(N), 1400, 7000)
    f0 = 300 + 900 * np.clip((t - a) / (b - a), 0, 1) ** 1.5; ph = np.cumsum(2 * np.pi * f0 / SR); tone = np.sin(ph) * .5 + np.sin(ph * 1.5) * .25
    out += (noise * .09 + tone * .07) * e
    for k in range(int((b - a) * 14)):
        tt = a + .25 + k / 14 * (1 - .06); i = int(tt * SR)
        if i + 1200 < N: out[i:i + 1200] += (np.sin(2 * np.pi * (1200 + 40 * k) * np.arange(1200) / SR) * np.exp(-np.arange(1200) / 140) * .05)
# the code: key clicks at a human pace, a little faster in bursts
for a, b in CODE:
    tt = a + .15
    while tt < b - .1:
        i = int(tt * SR); L = 900
        if i + L < N:
            click = hp(rng.standard_normal(L), 2500) * np.exp(-np.arange(L) / 90) * (.07 + .05 * rng.random())
            out[i:i + L] += click + np.sin(2 * np.pi * (180 + 60 * rng.random()) * np.arange(L) / SR) * np.exp(-np.arange(L) / 160) * .03
        tt += (.045 + .07 * rng.random()) * (.5 if rng.random() < .25 else 1)
# every cut: a whoosh in, a low thud, and a glitch flick
for c in CUTS:
    w = bp(rng.standard_normal(N), 400, 6000) * env(c - .35, c - .02, c, c + .25) * .22; out += w
    i = int(c * SR); L = int(.5 * SR)
    if i + L < N: out[i:i + L] += np.sin(2 * np.pi * (70 - 30 * np.arange(L) / L) * np.arange(L) / SR) * np.exp(-np.arange(L) / (.12 * SR)) * .5
# the end card: a soft major chord and one chime
for f, g in ((220, .5), (277.2, .4), (329.6, .4), (440, .3), (659.3, .15)):
    e = np.clip((t - 18.8) / .08, 0, 1) * np.exp(-(t - 18.8) / 2.6) * (t >= 18.8)
    out += np.sin(2 * np.pi * f * t) * e * g * .12
i = int(19.4 * SR); L = int(1.6 * SR)
if i + L < N: out[i:i + L] += np.sin(2 * np.pi * 1318.5 * np.arange(L) / SR) * np.exp(-np.arange(L) / (.5 * SR)) * .05
out = lp(out, 15000)
out = np.tanh(out * 1.6) / 1.6 * np.clip(t / .05, 0, 1) * np.clip((DUR - t) / .6, 0, 1)
out = out / max(1e-6, np.abs(out).max()) * .9
wavfile.write(sys.argv[1] if len(sys.argv) > 1 else 'audio5.wav', SR, (out * 32767).astype(np.int16))
print('wrote audio, peak', round(float(np.abs(out).max()), 2))
