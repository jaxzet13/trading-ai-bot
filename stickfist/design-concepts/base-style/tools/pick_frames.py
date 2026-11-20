"""Pick the most dramatic usable frame from each film: a grey-background frame with a big readable figure,
red in it, and nothing cut off at the edges. Saves frame PNGs and a contact sheet.
usage: python pick_frames.py FILMS_DIR OUTDIR"""
import sys, os, glob, subprocess, cv2, numpy as np
films, outd = sys.argv[1:3]; os.makedirs(outd, exist_ok=True)
FPS = 8
res = {}
for f in sorted(glob.glob(os.path.join(films, '*.mp4'))):
    name = os.path.basename(f)[:-4]
    tmp = os.path.join(outd, '_t_' + name); os.makedirs(tmp, exist_ok=True)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', f, '-vf', f'fps={FPS}', os.path.join(tmp, '%03d.png')], check=True)
    best, bs = None, -1
    for p in sorted(glob.glob(os.path.join(tmp, '*.png'))):
        im = cv2.imread(p); lum = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        bg = float(np.median(np.concatenate([lum[:20].ravel(), lum[-20:].ravel(), lum[:, :20].ravel(), lum[:, -20:].ravel()])))
        if bg < 0.62 or bg > 0.9: continue                                          # skip black / white impact frames
        mask = (np.abs(lum - bg) > 0.14)
        frac = mask.mean()
        if frac < 0.02 or frac > 0.45: continue
        b = np.concatenate([mask[:12].ravel(), mask[-12:].ravel(), mask[:, :12].ravel(), mask[:, -12:].ravel()]).mean()
        if b > 0.02: continue                                                      # figure cut off by the frame
        red = ((im[..., 2].astype(int) - im[..., 1]) > 70).mean()
        ys, xs = np.where(mask); h = ys.max() - ys.min(); w = xs.max() - xs.min()
        size = min(1.0, max(h / 720, w / 1280) / 0.55)                             # a big figure beats a tiny one
        score = size * 1.0 + min(red * 25, 1.0) * 0.8 + min(frac * 6, 1.0) * 0.4
        if score > bs: bs, best = score, p
    if best is None:
        print(name, 'no frame'); continue
    dst = os.path.join(outd, name + '.png'); cv2.imwrite(dst, cv2.imread(best)); res[name] = round(bs, 2)
    for p in glob.glob(os.path.join(tmp, '*.png')): os.remove(p)
    os.rmdir(tmp)
print(res)
# contact sheet
names = sorted(res); cols = 4; tw, th = 480, 270
rows = (len(names) + cols - 1) // cols
S = np.full((rows * (th + 24), cols * tw, 3), 30, np.uint8)
for i, n in enumerate(names):
    im = cv2.resize(cv2.imread(os.path.join(outd, n + '.png')), (tw, th)); r, c = divmod(i, cols)
    S[r * (th + 24) + 24:(r + 1) * (th + 24), c * tw:(c + 1) * tw] = im
    cv2.putText(S, n, (c * tw + 6, r * (th + 24) + 17), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
cv2.imwrite(os.path.join(outd, '_sheet.jpg'), S)
