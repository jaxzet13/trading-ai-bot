# Standing cards: the Blender toon style (flat cel tones, ink outlines, red the only colour)

One character, standing, nothing else happening. Each is built from primitives in Blender (toonlib.py), rendered emission-only in Cycles, then laid out with the name and copy ID (base_cards.js, needs the app test copy).

    pip install bpy==5.3.0
    python stand3d_reaper.py out.png 1.0 40
