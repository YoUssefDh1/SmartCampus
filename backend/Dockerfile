# Backend FastAPI - SmartCampus AI
FROM python:3.11-slim

WORKDIR /app

# Dependances systeme : compilation de quelques roues + client PostgreSQL (pg_isready)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        postgresql-client \
        curl \
        iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Dependances Python (couche mise en cache separement du code)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Code de l'application
COPY . .
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=development \
    CORS_ORIGINS='["http://localhost:3000"]' \
    DATABASE_URL=postgresql+psycopg://smartcampus:smartcampus@db:5432/smartcampus \
    JWT_SECRET=change-me-in-production \
    ACCESS_TOKEN_MINUTES=30 \
    AUTH_DEV_MODE=true \
    REFRESH_TOKEN_DAYS=7 \
    PASSWORD_MIN_LENGTH=8 \
    GUEST_SESSION_TTL_HOURS=24 \
    GUEST_MAX_MESSAGES=100 \
    GUEST_RATE_LIMIT_PER_MINUTE=10 \
    GUEST_PURGE_INTERVAL_MINUTES=60 \
    MEMORY_WINDOW_SIZE=10 \
    MAX_MESSAGE_LENGTH=2000 \
    LLM_BASE_URL=http://host.docker.internal:11434 \
    LLM_MODEL=mistral:latest \
    LLM_TIMEOUT_SECONDS=120 \
    LLM_MAX_TOKENS=600 \
    LLM_TEMPERATURE=0.2 \
    RAG_ENABLED=true \
    RAG_EMBEDDING_MODEL=nomic-embed-text \
    RAG_DOCUMENTS_DIR=/app/data/knowledge_base \
    RAG_TOP_K=4 \
    RAG_MIN_SIMILARITY=0.25

EXPOSE 8000

# Au demarrage : attendre PostgreSQL, appliquer les migrations, charger le seed,
# initialiser l'index RAG si necessaire, puis lancer l'API.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
