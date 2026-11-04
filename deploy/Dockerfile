FROM node:22-bookworm-slim AS nodejs
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=nodejs /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libstdc++6 ffmpeg fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt yt-dlp && useradd --uid 10001 --create-home atlas
COPY *.py *.js *.css *.html *.svg ./
COPY data/library.example.json ./data/library.example.json
COPY tools ./tools
RUN mkdir /state && chown atlas:atlas /state
USER atlas
VOLUME /state
CMD ["python", "private_server.py", "--bind", "0.0.0.0", "--state", "/state"]
