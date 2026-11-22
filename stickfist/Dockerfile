# STIXX on any host that runs a container (Fly.io, Render, Railway, a VPS...).
#   docker build --build-arg PUBLIC_URL=https://your-domain.example -t stixx .
#   docker run -p 8080:8080 -v stixx-data:/data -e ADMIN_TOKEN=... stixx
# The game and the server are one program on one address: the page talks to the server it was served from.
# Put the volume on /data: invites, fair-play seeds and paid orders live in the one file there (DATA_FILE).
# Secrets (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, ADMIN_TOKEN) are never baked in: set them in the host's secret settings. See STRIPE.md.

FROM python:3.12-slim AS build
ARG PUBLIC_URL=""
WORKDIR /app
COPY . .
RUN python3 build.py --release --url "$PUBLIC_URL"

FROM node:20-slim
WORKDIR /app
COPY --from=build /app/dist ./
ENV PORT=8080 DATA_FILE=/data/stixx.json TRUST_PROXY=1 NODE_ENV=production
RUN mkdir -p /data
EXPOSE 8080
CMD ["node", "server.js"]
