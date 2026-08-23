# Build the frontend, then serve it + the API from the Python backend as one image.

# --- stage 1: build the SPA ---
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- stage 2: backend serving /api and the built SPA ---
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RAIDLINES_STATIC_DIR=/app/webroot
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/tools ./tools
COPY --from=frontend /fe/dist ./webroot
EXPOSE 8600
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8600"]
