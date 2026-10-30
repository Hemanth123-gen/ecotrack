# Single service: builds the React app, then serves it and the API from FastAPI (used by Render).
# Cloud Run deploys use backend/Dockerfile (API only) with Firebase Hosting in front instead.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# frontend/.env.production holds the public Firebase web config read at build time
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    STATIC_DIR=/srv/static

WORKDIR /srv
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY backend/data ./data
COPY backend/scripts ./scripts
COPY --from=web /web/dist ./static

RUN useradd --uid 10001 --no-create-home app
USER app

CMD exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips="*"
