# Official RAG source documents

Put approved, current IIT/ISB materials in this folder before ingesting:

- program descriptions and curricula
- admission requirements and procedures
- current fees and application dates
- official FAQs, brochures, and contact information

Only ingest documents the team has verified as official and is permitted to use.
Do not put candidate records or personal data here. Supported inputs are PDF,
DOCX, Markdown, and UTF-8 text. DOCX heading styles and tables are retained
when extractable. PDF pages must contain selectable text; if a page has none,
ingestion reports its page number and stops so the file can be verified or
processed with OCR.

Run ingestion from the `backend` folder after starting PostgreSQL and Ollama:

    ollama pull nomic-embed-text-v2-moe
    python -m scripts.ingest_knowledge

The embedding model is configured separately from the chat model using
`RAG_EMBEDDING_MODEL`. The default `nomic-embed-text-v2-moe` is multilingual
and supports French. Chunks prefer sentence and paragraph boundaries, retain
Markdown headings with their following text, and are limited to 600
characters with up to 90 characters of overlap. If you change the embedding
model, re-run ingestion so retrieval compares vectors created by the same
model.
