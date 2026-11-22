#!/bin/sh
# Starts the server. If PUBLIC_URL is set, the link-preview image address in the page is made absolute (social sites need that).
if [ -n "$PUBLIC_URL" ]; then
  sed -i "s#content=\"og.png\"#content=\"${PUBLIC_URL%/}/og.png\"#" index.html
fi
exec node server.js
