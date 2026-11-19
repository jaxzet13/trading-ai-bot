"""Minimal cards: the art is the card. Four rarity tiers of the same Phantom shot."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from dark_phantom import scene

# bigger, full-bleed: Phantom over the bodies, head rising into the name
base = dict(n=246, crop=(188, 722, 560, 1077), s=2.9, x0=0, y0=392, foot=(965, 618), fg_cut=1960,
            wall_c=None)
feet = ((965 - 560) * 2.9, 392 + (618 - 188) * 2.9)
light = dict(wall_c=(feet[0] - 160, feet[1] - 930), wall_r=(760, 720), floor_r=(1100, 260),
             shadow_scale=1.33, shadow_off=(230, -40))
base.pop('wall_c')

TIERS = {
    'T0': dict(),                                                                  # common: clean light
    'T1': dict(red_rim=True),                                                      # rare: red rim
    'T2': dict(red_rim=True, rain=3600, wall_i=.48),                               # top: rain, red rim
    'T3': dict(rain=3600, light_tint=(214, 38, 40), wall_i=.70, floor_i=.42),      # 1 of 1: lit in blood
}
if __name__ == '__main__':
    for k, v in TIERS.items():
        scene(name=f'M_{k}', **base, **{**light, **v})
