# Drawn card tools

Blender 5.x Grease Pencil (2D drawing), run headless with a software GL driver:

    apt-get install libegl1 libegl-mesa0 libgl1-mesa-dri
    pip install bpy==5.3.0
    EGL_PLATFORM=surfaceless python gp_card.py out.png 1.0

Then gp_finish.js (Playwright) sets the name and the copy ID on the art.
