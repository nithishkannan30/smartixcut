FROM node:22-slim AS web-build

WORKDIR /app/web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
COPY --from=web-build /app/web/dist ./web/dist
RUN python get_fonts.py \
    && test -f fonts/NotoSansTamil-Bold.ttf \
    && test -f fonts/NotoSansDevanagari-Bold.ttf \
    && test -f fonts/NotoSans-Bold.ttf

EXPOSE 10000

CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-10000}