"""UMBRA: the super-rare card. 1,500 columns x 1,052 rows = 1,578,000 characters: one character per pixel at print size."""
import cv2, numpy as np
import ascii2 as A

SRC = '../umbra/eclipse.png'
OUT = '../umbra/umbra_card.jpg'
n = A.render(SRC, OUT, 'Umbra', 'IS020-000001-6TQ2', '///', 'duo', 1500, 1, pal='amber', crop=(0.07, 0.05, 0.93, 0.985),
             black=0.05, white=0.9, gamma=0.72, glow=0.8, typo='line', caption='the sun blinked first.')
print('chars', f'{n:,}')
im = cv2.imread(OUT)[:1820]
im = cv2.resize(im, (900, 1092), interpolation=cv2.INTER_AREA)
cv2.imwrite('../umbra/umbra_pic.jpg', im, [cv2.IMWRITE_JPEG_QUALITY, 84])
print('done')
