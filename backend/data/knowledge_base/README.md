# Official RAG source documents

Put approved, current IIT/ISB materials in this folder before ingesting:

- program descriptions and curricula
- admission requirements and procedures
- current fees and application dates
- official FAQs, brochures, and contact information

Only ingest documents the team has verified as official and is permitted to use.
Do not put candidate records or personal data here. Supported inputs are PDF,
Markdown, and UTF-8 text. PDF extraction works only when the PDF contains
selectable text; scanned PDFs need OCR before ingestion.

Run ingestion from the `backend` folder after starting PostgreSQL and Ollama:

    ollama pull nomic-embed-text
    python -m scripts.ingest_knowledge

The embedding model is configured separately from the chat model using
`RAG_EMBEDDING_MODEL`. If you change the embedding model, re-run ingestion so
retrieval compares vectors created by the same model.
