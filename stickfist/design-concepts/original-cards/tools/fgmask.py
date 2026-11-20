import sys, cv2, numpy as np
art, mask, out = sys.argv[1:4]
a = cv2.imread(art); m = cv2.imread(mask, 0)
m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))); m = cv2.GaussianBlur(m, (0, 0), 1.2)
cv2.imwrite(out, np.dstack([a, m]))
