# Ollama model test checklist

This checklist is for the teammate testing Gemma and Qwen on the PC with Ollama.
The goal is to return comparable results so the SmartCampus code and prompts can
be improved. Ollama is the model runner; Gemma and Qwen are the models.

## 1. Get the code

- [ ] Ask the project owner to share/push branch `feature/SA-30-llm-integration`.
      It must be shared before it can be checked out.
- [ ] Check out that branch and do not edit the prompt set or benchmark settings
      during the comparison.

## 2. Prepare Ollama and the backend

- [ ] Install and start Ollama.
- [ ] In PowerShell, download the candidate models:

      ollama pull gemma3:4b
      ollama pull qwen3:4b
      ollama list

- [ ] Open a PowerShell terminal in `backend`.
- [ ] Create `backend/.env` from `.env.example` if it does not already exist:

      if (-not (Test-Path .env)) { Copy-Item .env.example .env }

- [ ] Confirm `LLM_BASE_URL=http://localhost:11434` and set `LLM_MODEL` to one
      installed model, such as `gemma3:4b`. The benchmark itself tests both
      models regardless of this setting.
- [ ] Install backend dependencies if needed:

      python -m pip install -r requirements.txt

## 3. Run the same benchmark on both models

- [ ] From the `backend` directory, run:

      python -m scripts.benchmark_llm

- [ ] Wait for the run to finish. It warms up each model and tests all 35
      prompts with identical settings.
- [ ] Find the generated report under
      `backend/data/llm_eval/results/benchmark-*.json`.
- [ ] Open `backend/data/llm_eval/README.md` and complete each run's
      `human_review` fields. Score helpfulness, language match, grounding, and
      context use from 1–5; mark context use as N/A for single-turn prompts.
- [ ] Set `hallucination` to `true` for any unsupported official admission
      rule, fee, date, program fact, or guaranteed outcome. Add a short note
      with the prompt ID and what was wrong.
- [ ] Fill in `environment_notes` in the report: PC model, RAM, OS, Ollama
      version (`ollama --version`), and whether Ollama used GPU acceleration.
- [ ] Do not edit the source prompt dataset or generation settings for this
      comparison. If a prompt is confusing or inaccurate, note its ID
      separately instead.

## 4. Run the live chat check for each model

- [ ] Set `LLM_MODEL` in `backend/.env` to the model being tested.
- [ ] Start the backend from `backend`:

      python -m uvicorn app.main:app --reload

- [ ] In a second PowerShell terminal, go to `backend` and run:

      $env:RUN_LLM_INTEGRATION="1"
      python -m pytest -q tests/integration/test_live_ollama.py

- [ ] Repeat with the other model by changing `LLM_MODEL` and rerunning the
      test. Save any failing response or unexpected language behavior with the
      model name and prompt.

## 5. RAG smoke test (after official documents are provided)

- [ ] Ask the project owner for the approved, current IIT/ISB source documents.
      Do not use project specifications or candidate records as admissions
      sources.
- [ ] Put approved, text-searchable PDF, Markdown, or UTF-8 text files in
      `backend/data/knowledge_base/`.
- [ ] From the repository root, start PostgreSQL:

      docker compose up -d

- [ ] In another terminal, pull the embedding model and ingest the documents
      from `backend/`:

      ollama pull nomic-embed-text
      python -m scripts.ingest_knowledge

- [ ] Set `RAG_ENABLED=true` in `backend/.env`, restart the backend, and ask a
      question answerable from one of the source documents.
- [ ] Confirm the response includes a citation and the API response includes
      the document title, filename, and page. Also test an unsupported official
      question and confirm the assistant does not invent an answer.
- [ ] Report any failed ingestion, missing citation, or unsupported claim with
      the question and source document.

## 6. Send the results back

- [ ] Send the completed benchmark JSON file to the project owner. The results
      folder is intentionally Git-ignored, so attach or share the file directly
      rather than committing it.
- [ ] Include a short summary for each model: mean latency, quality/language/
      grounding scores, number of critical hallucinations, and any failed live
      tests.
- [ ] Do not send `.env` files, API keys, or other secrets.

## Done when

- Both models have been tested against the same prompt set and generation
  settings.
- Human review is complete and critical hallucinations are clearly identified.
- Live integration results and the machine/Ollama details are included.
- If approved RAG documents were supplied, ingestion and citation checks are
  included.
- The raw benchmark JSON and a brief comparison summary have been returned to
  the project owner.
