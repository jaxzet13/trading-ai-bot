import os, sys, cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from noir_light import layers, render, save
from art import frame
OUT = os.path.join(os.path.dirname(__file__), 'out'); os.makedirs(OUT, exist_ok=True)
W, H = 1500, 2100          # 2.5 x 3.5 in at 600 dpi


def scene(n, crop, s, x0, y0, foot, name, fg_cut=1490, **kw):
    """crop=(y0,y1,x0,x1) in film px; foot=(x,y) in film px."""
    fy0, fy1, fx0, fx1 = crop
    L = layers(frame(n)[fy0:fy1, fx0:fx1], s)
    feet = (x0 + int((foot[0] - fx0) * s), y0 + int((foot[1] - fy0) * s))
    args = dict(wall_c=(feet[0] - 120, feet[1] - 760), wall_r=(700, 640), floor_r=(1000, 230),
                shadow_scale=1.42, shadow_off=(210, -30), rim_dir=(-1, 1), rim_px=6,
                rim_src=(W + 200, -200), rim_reach=2300, wall_i=.62, floor_i=.32, seed=19)
    args.update(kw)
    img, fg = render(L, W, H, x0, y0, feet[1] - 8, feet, **args)
    save(f'{OUT}/{name}.png', img)
    a = fg.copy(); a[fg_cut:] = 0                                  # nothing in front of the move text
    rgba = np.dstack([img, a])
    cv2.imwrite(f'{OUT}/{name}_fg.png', cv2.cvtColor((rgba * 255 + .5).astype(np.uint8), cv2.COLOR_RGBA2BGRA))
    print(name, 'feet', feet)


def _main():
    base = dict(n=246, crop=(188, 722, 400, 1090), s=2.38, x0=-100, y0=336, foot=(965, 618))
    scene(name='D_phantom', **base)
    scene(name='D_phantom_rain', rain=3200, red_rim=True, wall_i=.44, **base)


def lenticular():
    rare = dict(rain=3200, red_rim=True, wall_i=.44)
    # 1. the stab: sword knocked out of his hand
    scene(name='L1', n=146, crop=(188, 722, 250, 1000), s=2.0, x0=0, y0=501, foot=(600, 617), **rare)
    # 2. the dive: dropping onto the guard from above (film top edge sits on the card's bleed)
    scene(name='L2', n=191, crop=(0, 722, 420, 1102), s=2.2, x0=0, y0=0, foot=(650, 610),
          shadow_off=(160, -60), **rare)
    # 3. the aftermath
    scene(name='L3', n=246, crop=(188, 722, 400, 1090), s=2.38, x0=-100, y0=336, foot=(965, 618), **rare)


if __name__ == '__main__':
    import sys as _s
    lenticular() if 'len' in _s.argv else _main()
