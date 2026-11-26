#!/bin/bash
# usage: dl.sh id uuid  (saves sources/<id>.png)
cd "$(dirname "$0")/sources" && curl -sf -L -o "$1.png" "https://www.figma.com/api/mcp/asset/$2.png" && echo "$1 ok $(stat -c %s $1.png)"
