"""Mémoire temporaire des conversations visiteur (SA-26).

Deux niveaux de mémoire, tous deux portés par les tables du schéma réel :
- fenêtre glissante : les N derniers `message` de la `conversation` (N = memory_window_size),
  réinjectés dans le prompt pour borner les tokens ;
- état structuré : `conversation.profile_draft` (jsonb), fusionné de façon incrémentale
  sans écraser les clés déjà consolidées.
"""
from typing import Any

import psycopg

from app.agents.profile import extract_profile_signals, to_chat_language
from app.core.config import get_settings

_CONVERSATION_COLUMNS = """
    id, guest_session_id, candidate_id, language, status,
    started_at, last_message_at, profile_draft
"""


def get_or_create_conversation(connection: psycopg.Connection, guest_session_id: str,
                               conversation_id: str | None = None) -> dict:
    """Conversation active du visiteur.

    `conversation_id` n'est honoré que s'il appartient bien à cette session visiteur :
    l'ownership est filtré dans la requête, jamais déduit de la valeur fournie.
    """
    if conversation_id:
        row = connection.execute(
            f"""
            SELECT {_CONVERSATION_COLUMNS} FROM conversation
            WHERE id = %s AND guest_session_id = %s
            """,
            (conversation_id, guest_session_id),
        ).fetchone()
        if row:
            return row

    row = connection.execute(
        f"""
        SELECT {_CONVERSATION_COLUMNS} FROM conversation
        WHERE guest_session_id = %s AND status = 'active'
        ORDER BY started_at DESC LIMIT 1
        """,
        (guest_session_id,),
    ).fetchone()
    if row:
        return row

    return connection.execute(
        f"""
        INSERT INTO conversation (guest_session_id, status)
        VALUES (%s, 'active')
        RETURNING {_CONVERSATION_COLUMNS}
        """,
        (guest_session_id,),
    ).fetchone()


def get_conversation(connection: psycopg.Connection, conversation_id: str) -> dict | None:
    return connection.execute(
        f"SELECT {_CONVERSATION_COLUMNS} FROM conversation WHERE id = %s",
        (conversation_id,),
    ).fetchone()


def list_guest_conversations(connection: psycopg.Connection, guest_session_id: str) -> list[dict]:
    return connection.execute(
        f"""
        SELECT {_CONVERSATION_COLUMNS} FROM conversation
        WHERE guest_session_id = %s
        ORDER BY started_at DESC
        """,
        (guest_session_id,),
    ).fetchall()


def save_message(connection: psycopg.Connection, conversation_id: str, role: str, content: str,
                 *, language: str | None = None, sources: Any = None,
                 next_action: str | None = None, profile_updates: Any = None) -> dict:
    """Persiste un message (tronqué à max_message_length) et maj la conversation."""
    settings = get_settings()
    row = connection.execute(
        """
        INSERT INTO message (conversation_id, role, content, language, sources, next_action, profile_updates)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, conversation_id, role, content, language, sources, next_action,
                  profile_updates, created_at
        """,
        (conversation_id, role, content[:settings.max_message_length], language,
         psycopg.types.json.Jsonb(sources) if sources is not None else None,
         next_action,
         psycopg.types.json.Jsonb(profile_updates) if profile_updates is not None else None),
    ).fetchone()
    connection.execute(
        """
        UPDATE conversation
        SET last_message_at = now(),
            language = COALESCE(language, %s)
        WHERE id = %s
        """,
        (language, conversation_id),
    )
    return row


def get_recent_context(connection: psycopg.Connection, conversation_id: str) -> tuple[list[dict], dict]:
    """Les N derniers messages en ordre chronologique + le profile_draft courant."""
    settings = get_settings()
    rows = connection.execute(
        """
        SELECT id, role, content, language, sources, next_action, profile_updates, created_at
        FROM (
            SELECT * FROM message
            WHERE conversation_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        ) recent
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_id, settings.memory_window_size),
    ).fetchall()

    conversation = get_conversation(connection, conversation_id)
    profile_draft = (conversation or {}).get("profile_draft") or {}
    return rows, profile_draft


def merge_profile_draft(current: dict, incoming: dict) -> dict:
    """Fusion incrémentale : les scalaires vides n'écrasent rien, les listes sont unies sans doublon."""
    merged = dict(current or {})
    for key, value in (incoming or {}).items():
        if isinstance(value, list):
            existing = [item for item in (merged.get(key) or []) if item not in value]
            merged[key] = existing + value
        elif value not in (None, ""):
            merged[key] = value
    return merged


def update_profile_draft(connection: psycopg.Connection, conversation_id: str,
                         extracted: dict) -> dict:
    conversation = get_conversation(connection, conversation_id)
    if conversation is None:
        raise ValueError("Conversation introuvable.")

    merged = merge_profile_draft(conversation.get("profile_draft") or {}, extracted)
    connection.execute(
        "UPDATE conversation SET profile_draft = %s WHERE id = %s",
        (psycopg.types.json.Jsonb(merged), conversation_id),
    )
    return merged


def collect_profile_signals(text: str, detected_language: str) -> dict:
    """Signaux de profil d'un message visiteur : langue SQL + niveau + intérêts + institutions."""
    signals = extract_profile_signals(text)
    chat_language = to_chat_language(detected_language)
    if chat_language:
        signals["detected_language"] = chat_language
    return signals


def history_to_llm_messages(messages: list[dict]) -> list[dict[str, str]]:
    """Convertit la fenêtre glissante au format attendu par llm_service.generate_reply."""
    return [{"role": row["role"], "content": row["content"]} for row in messages
            if row["role"] in ("user", "assistant")]


def list_messages(connection: psycopg.Connection, conversation_id: str) -> list[dict]:
    """Historique complet d'une conversation, en ordre chronologique."""
    return connection.execute(
        """
        SELECT id, role, content, language, sources, next_action, profile_updates, created_at
        FROM message WHERE conversation_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_id,),
    ).fetchall()
