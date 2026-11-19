# Blender card tools

Render: pip install bpy==5.3.0 (Python 3.13), then from dark-cards/tools (needs art.py, noir_light.py and the film frames in full/):

    python blender_card.py out.png 1.0 128
    python blender_card.py out_mask.png 1.0 16 mask
    python blender_post.py out.png out_mask.png out/BL_bg.png out/BL_fg.png
    node blender_finish.js <head_top_css_px>
