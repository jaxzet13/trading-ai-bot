# Original cards: no films, no AI images

Every figure is drawn in code with tapered ink shapes (kit.py), composed with a camera (rotate + scale), then printed through the halftone pipeline.

    python art_phantom.py frame.png                       # draw the frame (also writes *_fgmask.png and *_focus.txt)
    python base_style.py frame.png H out.png full FX,FY   # tiers: C U R H RR; full = use the whole composed frame
    python fgmask.py out.png frame_fgmask.png out_fg.png  # the layer that goes over the name
    node base_cards.js OUTDIR list.json                   # name, copy ID, rarity cuts, frame-break overlay
