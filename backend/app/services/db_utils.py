"""Outils SQL partagés par les services : erreurs PostgreSQL -> erreurs API, filtres, pagination, audit.

Les fragments SQL passés à Where / update_row viennent TOUJOURS du code (jamais de l'utilisateur) ;
les valeurs passent par des paramètres %s.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors as pg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.security import Actor

# Contrainte -> message compréhensible par un responsable.
CONSTRAINT_MESSAGES = {
    "program_institution_id_code_key": "Ce code de formation existe déjà dans cette école.",
    "specialty_program_id_name_key": "Cette spécialité existe déjà pour cette formation.",
    "subject_code_key": "Ce code de matière existe déjà.",
    "curriculum_version_key": "Cette version existe déjà pour cette formation, cette spécialité et cette année.",
    "curriculum_one_active_key": "Un seul programme pédagogique actif par formation, spécialité et année.",
    "curriculum_subject_curriculum_id_subject_id_semester_key":
        "Cette matière figure déjà dans ce programme pour ce semestre.",
    "tuition_fee_key": "Un tarif de ce type existe déjà pour cette formation, cette année et ce niveau. "
                       "Modifiez-le, ou archivez-le avant d'en créer un nouveau.",
    "payment_plan_name_key": "Une modalité de paiement porte déjà ce nom pour cette formation et cette année.",
    "curriculum_specialty_id_program_id_fkey": "La spécialité choisie n'appartient pas à cette formation.",
    "admission_requirement_required_program_id_fkey": "La formation exigée n'existe pas.",
    "program_institution_id_fkey": "École introuvable.",
    "curriculum_subject_subject_id_fkey": "Matière introuvable.",
    "admission_requirement_check": "Une condition « moyenne minimale » exige la valeur min_average.",
    "tuition_fee_validity_check": "La date de fin de validité doit être postérieure à la date de début.",
    "admission_requirement_validity_check": "La date de fin de validité doit être postérieure à la date de début.",
    "payment_plan_validity_check": "La date de fin de validité doit être postérieure à la date de début.",
}

# Table qui référence encore l'élément qu'on veut supprimer.
REFERENCING_LABELS = {
    "preregistration": "des préinscriptions",
    "recommendation": "des recommandations d'orientation",
    "equivalence_request": "des demandes d'équivalence",
    "curriculum": "des programmes pédagogiques",
    "curriculum_subject": "des programmes pédagogiques",
    "admission_requirement": "des conditions d'admission d'autres formations",
}


@contextmanager
def translate_db_errors(deleting: bool = False) -> Iterator[None]:
    """À placer AUTOUR de `conn.transaction()` : la transaction est annulée, puis l'erreur traduite."""
    try:
        yield
    except pg.UniqueViolation as exc:
        name = exc.diag.constraint_name
        raise ConflictError(CONSTRAINT_MESSAGES.get(name, "Un élément identique existe déjà."),
                            [{"constraint": name}]) from exc
    except (pg.ForeignKeyViolation, pg.RestrictViolation) as exc:  # RESTRICT lève RestrictViolation
        name = exc.diag.constraint_name
        if deleting or isinstance(exc, pg.RestrictViolation):
            used_by = REFERENCING_LABELS.get(exc.diag.table_name or "", "d'autres données")
            raise ConflictError(f"Suppression impossible : cet élément est utilisé par {used_by}. "
                                "Désactivez-le ou archivez-le plutôt.", [{"constraint": name}]) from exc
        raise UnprocessableError(CONSTRAINT_MESSAGES.get(name, "Un élément référencé est introuvable."),
                                 [{"constraint": name}]) from exc
    except (pg.CheckViolation, pg.NotNullViolation) as exc:
        name = exc.diag.constraint_name or exc.diag.column_name
        raise UnprocessableError(CONSTRAINT_MESSAGES.get(name or "", "Valeur refusée par les règles de la base."),
                                 [{"constraint": name}]) from exc
    except pg.RaiseException as exc:  # règles écrites en triggers
        raise UnprocessableError(exc.diag.message_primary or "Opération refusée.") from exc


class Where:
    """Construit une clause WHERE : w.add("p.school = %s", value)."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.params: list[Any] = []

    def add(self, fragment: str, *params: Any) -> "Where":
        self.parts.append(fragment)
        self.params.extend(params)
        return self

    def add_if(self, value: Any, fragment: str, repeat: int = 1) -> "Where":
        if value is not None and value != "":
            self.add(fragment, *([value] * repeat))
        return self

    def search(self, q: str | None, *columns: str) -> "Where":
        """Recherche insensible à la casse et aux accents sur plusieurs colonnes."""
        if q and q.strip():
            like = f"%{q.strip()}%"
            cond = " OR ".join(f"catalog_search_text({c}) LIKE catalog_search_text(%s)" for c in columns)
            self.add(f"({cond})", *([like] * len(columns)))
        return self

    def sql(self) -> str:
        return (" WHERE " + " AND ".join(self.parts)) if self.parts else ""


def fetch_page(conn: psycopg.Connection, select: str, from_: str, where: Where, order_by: str,
               page: int, size: int) -> tuple[list[dict], int]:
    total = conn.execute(f"SELECT count(*) AS n {from_}{where.sql()}", where.params).fetchone()["n"]
    rows = conn.execute(f"{select} {from_}{where.sql()} ORDER BY {order_by} LIMIT %s OFFSET %s",
                        [*where.params, size, (page - 1) * size]).fetchall()
    return rows, total


def insert_row(conn: psycopg.Connection, table: str, values: dict[str, Any]) -> UUID:
    cols = list(values)
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, cols)),
        sql.SQL(", ").join(sql.Placeholder() * len(cols)))
    return conn.execute(query, [_adapt(values[c]) for c in cols]).fetchone()["id"]


def update_row(conn: psycopg.Connection, table: str, row_id: UUID, values: dict[str, Any]) -> None:
    if not values:
        return
    sets = sql.SQL(", ").join(sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder()) for k in values)
    query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(sql.Identifier(table), sets)
    conn.execute(query, [*(_adapt(v) for v in values.values()), row_id])


def delete_row(conn: psycopg.Connection, table: str, row_id: UUID, not_found: str) -> None:
    deleted = conn.execute(sql.SQL("DELETE FROM {} WHERE id = %s RETURNING id").format(sql.Identifier(table)),
                           [row_id]).fetchone()
    if not deleted:
        raise NotFoundError(not_found)


def _adapt(value: Any) -> Any:
    return Jsonb(value) if isinstance(value, dict) else value


def audit(conn: psycopg.Connection, actor: Actor, action: str, entity_type: str, entity_id: UUID,
          details: dict | None = None) -> None:
    """Journal append-only (table audit_log du schéma) : qui a modifié quoi dans le catalogue."""
    conn.execute(
        """INSERT INTO audit_log (actor_type, actor_user_id, actor_label, action, entity_type, entity_id,
                                  details, request_id)
           VALUES ('user', %s, %s, %s, %s, %s, %s, %s)""",
        (actor.user_id, actor.role.value, action, entity_type, entity_id,
         Jsonb(_jsonable(details or {})), actor.request_id))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)  # UUID, Decimal, date


def visibility_sql(alias: str) -> str:
    """Statut réellement vu par le candidat (cf. catalog_is_official, migration 002)."""
    return (f"CASE WHEN {alias}.status = 'draft' THEN 'draft' "
            f"WHEN {alias}.status = 'archived' THEN 'archived' "
            f"WHEN {alias}.valid_from IS NOT NULL AND {alias}.valid_from > current_date THEN 'scheduled' "
            f"WHEN {alias}.valid_until IS NOT NULL AND {alias}.valid_until < current_date THEN 'expired' "
            f"ELSE 'visible' END")
