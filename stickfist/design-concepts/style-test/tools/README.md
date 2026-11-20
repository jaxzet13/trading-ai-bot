# Style test tools

Each style: a cheap low-res reference (Higgsfield 1k low = 0.5 credit, or a frame from the films) -> prep script that rebuilds print-ready plates/maps at 1500x2100 -> a Blender (Cycles) scene that prints/builds the card. Layout text is four.html (render_four.js).

1 screenprint: plates.py -> print_blender.py
2 papercut: prep_paper.py -> papercut_blender.py
3 black chrome: prep_chrome.py -> chrome_blender.py
4 ink wash: prep_wash.py -> wash_blender.py
