FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Hugging Face Spaces routes traffic to port 7860 by default.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:${PORT} src.picks.web:app"]
