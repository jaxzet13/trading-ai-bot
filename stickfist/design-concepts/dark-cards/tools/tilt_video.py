"""Simulate a lenticular card being tilted on camera (4:5, for social).
Tilt picks which printed state you see, with the slight ghosting a real lens gives."""
import os, sys, subprocess, cv2, numpy as np
D = os.path.dirname(os.path.abspath(__file__)); O = os.path.join(D, 'out')
states = [cv2.imread(f'{O}/card_L{i}.png').astype(np.float32) / 255 for i in (1, 2, 3)]
Hc, Wc = states[0].shape[:2]
VW, VH, FPS, SEC = 1080, 1350, 30, 6
out = sys.argv[1]

# rounded corners like a real cut card (1/8 in radius)
r = int(Wc * .05)
mask = np.zeros((Hc, Wc), np.float32)
cv2.rectangle(mask, (r, 0), (Wc - r, Hc), 1, -1); cv2.rectangle(mask, (0, r), (Wc, Hc - r), 1, -1)
for cx, cy in ((r, r), (Wc - r, r), (r, Hc - r), (Wc - r, Hc - r)):
    cv2.circle(mask, (cx, cy), r, 1, -1, cv2.LINE_AA)
# lens ridges: fine vertical lines you can just see up close
ridge = (1 + .035 * np.sin(np.arange(Wc) * 2 * np.pi / 7.0))[None, :, None].astype(np.float32)

yy, xx = np.mgrid[0:VH, 0:VW].astype(np.float32)
table = np.exp(-(((xx - VW * .5) / (VW * .7)) ** 2 + ((yy - VH * .45) / (VH * .55)) ** 2)) * .10 + .025
table = np.dstack([table] * 3)
rng = np.random.default_rng(2)

def project(theta, phi, scale):
    w, h = Wc * scale / 2, Hc * scale / 2
    f = 2600.0
    pts = []
    for x, y in ((-w, -h), (w, -h), (w, h), (-w, h)):
        X = x * np.cos(theta); Z = x * np.sin(theta)
        Y = y * np.cos(phi); Z += y * np.sin(phi)
        pts.append((VW / 2 + X * f / (f + Z), VH * .48 + Y * f / (f + Z)))
    return np.float32(pts)

src = np.float32([(0, 0), (Wc, 0), (Wc, Hc), (0, Hc)])
p = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{VW}x{VH}', '-r', str(FPS), '-i', '-',
                      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '17', '-preset', 'slow', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
N = FPS * SEC
for i in range(N):
    t = i / N
    theta = np.deg2rad(16 * np.sin(2 * np.pi * t) + 1.5 * np.sin(6 * np.pi * t + .7))   # hand tilt, left and right
    phi = np.deg2rad(-6 + 2 * np.sin(2 * np.pi * t * 2 + 1.1))
    # which printed state the lens shows at this angle: -16..16 deg -> state 0..2, soft at the edges
    u = (np.rad2deg(theta) + 16) / 32 * 3 - .5
    wts = np.array([np.clip(1 - abs(u - k) * 1.6, 0, 1) for k in range(3)]) ** 1.5 + 1e-4
    face = sum(w * s for w, s in zip(wts, states)) / wts.sum()
    face = face * ridge
    # specular sweep across the lens as it turns
    band = np.exp(-((np.arange(Wc) / Wc - (.5 + np.rad2deg(theta) / 26)) / .07) ** 2)[None, :, None] * .055
    face = np.clip(face + band, 0, 1)
    dst = project(theta, phi, .52)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(face, M, (VW, VH), flags=cv2.INTER_LINEAR)
    a = cv2.warpPerspective(mask, M, (VW, VH), flags=cv2.INTER_LINEAR)[..., None]
    shadow = cv2.GaussianBlur(cv2.warpPerspective(mask, M, (VW, VH)), (0, 0), 28)[..., None]
    shadow = np.roll(shadow, (30, 14), (0, 1))
    frame = table * (1 - shadow * .85)
    frame = frame * (1 - a) + warped * a
    edge = np.clip(a - cv2.erode(a, np.ones((3, 3), np.uint8))[..., None], 0, 1)
    frame += edge * .28
    frame += rng.normal(0, .006, frame.shape[:2])[..., None]
    p.stdin.write((np.clip(frame, 0, 1) * 255).astype(np.uint8).tobytes())
p.stdin.close(); p.wait()
print('ok', out)
