FROM python:3.12-slim

# HF Spaces requires the container to run as a non-root user.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY --chown=user src ./src

# HF routes traffic to port 7860 by default.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:${PORT} src.picks.web:app"]
