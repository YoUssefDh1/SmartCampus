#!/bin/sh
set -e

echo ">>> SmartCampus backend - attente de PostgreSQL sur db:5432 ..."
until pg_isready -h db -U "${POSTGRES_USER:-smartcampus}" -d "${POSTGRES_DB:-smartcampus}"; do
  sleep 2
done
echo ">>> PostgreSQL pret."

echo ">>> Application des migrations..."
python -m app.db.migrate

echo ">>> Chargement des donnees de demonstration (seed)..."
python -m app.db.seed

# --- Detection automatique de l'hote Ollama (aucune IP a configurer manuellement) ---
# Docker Desktop fait pointer host.docker.internal vers la passerelle (l'hote Windows).
# Si Ollama n'ecoute que sur 127.0.0.1, on essaie l'IP de la passerelle detectee dynamiquement.
if [ -z "$LLM_BASE_URL" ] || [ "$LLM_BASE_URL" = "http://host.docker.internal:11434" ]; then
  if curl -sf http://host.docker.internal:11434/api/tags >/dev/null 2>&1; then
    echo ">>> Ollama joignable via host.docker.internal"
  else
    HOST_IP=$(ip route | awk '/default/ {print $3}' | head -n1)
    if [ -n "$HOST_IP" ] && curl -sf "http://${HOST_IP}:11434/api/tags" >/dev/null 2>&1; then
      export LLM_BASE_URL="http://${HOST_IP}:11434"
      echo ">>> Ollama joignable via la passerelle Docker : $LLM_BASE_URL"
    else
      echo ">>> ATTENTION: Ollama non joignable depuis le conteneur."
      echo ">>> Lancez Ollama accessible sur le reseau (ex: OLLAMA_HOST=0.0.0.0 ollama serve)."
      echo ">>> Le chat sera indisponible tant qu'Ollama n'est pas accessible."
    fi
  fi
fi

if [ "${RAG_ENABLED:-false}" = "true" ]; then
  RAG_TABLE_EXISTS=$(PGPASSWORD="${POSTGRES_PASSWORD:-smartcampus}" \
    psql -h db -U "${POSTGRES_USER:-smartcampus}" -d "${POSTGRES_DB:-smartcampus}" \
    -tAc "SELECT to_regclass('public.rag_chunks') IS NOT NULL")
  if [ "$RAG_TABLE_EXISTS" = "t" ]; then
    RAG_CHUNK_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD:-smartcampus}" \
      psql -h db -U "${POSTGRES_USER:-smartcampus}" -d "${POSTGRES_DB:-smartcampus}" \
      -tAc "SELECT count(*) FROM public.rag_chunks")
  else
    RAG_CHUNK_COUNT=0
  fi

  if [ "$RAG_CHUNK_COUNT" -eq 0 ]; then
    echo ">>> Initialisation de l'index RAG..."
    python -m scripts.ingest_knowledge
  else
    echo ">>> Index RAG deja initialise ($RAG_CHUNK_COUNT passages)."
  fi
fi

echo ">>> Demarrage de l'API FastAPI sur le port 8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
