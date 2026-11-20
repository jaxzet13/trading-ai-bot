# Base style ("cut print") for Common to Signature

    python pick_frames.py ../../../films frames        # best frame from each film
    python base_style.py frames/daggers.png H out.png   # tier: C U R H RR
    node base_cards.js OUTDIR list.json                 # name, copy ID, rarity cuts (needs the app test copy)
