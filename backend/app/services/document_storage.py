"""Private filesystem storage for uploaded official documents."""

import codecs
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import UUID

from fastapi import UploadFile

from app.core.config import Settings, get_settings
from app.core.errors import FileTooLargeError, NotFoundError, UnprocessableError, UnsupportedMediaTypeError

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


@dataclass(frozen=True)
class StoredUpload:
    storage_path: str
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str


def _storage_root(settings: Settings | None = None) -> Path:
    config = settings or get_settings()
    root = Path(config.documents_storage_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    return root.resolve()


def _clean_filename(filename: str | None) -> tuple[str, str]:
    if not filename:
        raise UnprocessableError("Le nom du fichier est obligatoire.")

    basename = PureWindowsPath(filename.replace("/", "\\")).name
    basename = "".join(char for char in basename if ord(char) >= 32 and ord(char) != 127).strip(" .")
    suffix = PureWindowsPath(basename).suffix.lower()
    if suffix not in MIME_TYPES:
        raise UnsupportedMediaTypeError(
            "Formats acceptés : PDF, DOCX, Markdown (.md) et texte UTF-8 (.txt)."
        )
    if not basename:
        raise UnprocessableError("Le nom du fichier est invalide.")
    if len(basename) > 255:
        stem = basename[:-len(suffix)]
        basename = f"{stem[:255 - len(suffix)]}{suffix}"
    return basename, suffix


def store_upload(
    upload: UploadFile,
    document_id: UUID,
    version_id: UUID,
    *,
    settings: Settings | None = None,
) -> StoredUpload:
    config = settings or get_settings()
    original_filename, suffix = _clean_filename(upload.filename)
    root = _storage_root(config)
    relative_path = PurePosixPath(str(document_id), f"{version_id}{suffix}")
    destination = root.joinpath(*relative_path.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    checksum = hashlib.sha256()
    size_bytes = 0
    first_chunk = True
    decoder = codecs.getincrementaldecoder("utf-8")("strict") if suffix in {".md", ".txt"} else None

    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=root)
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stored:
            while chunk := upload.file.read(64 * 1024):
                size_bytes += len(chunk)
                if size_bytes > config.document_max_upload_bytes:
                    raise FileTooLargeError("Le fichier dépasse la taille maximale autorisée.")
                if first_chunk and suffix == ".pdf" and not chunk.startswith(b"%PDF-"):
                    raise UnsupportedMediaTypeError("Le contenu du fichier ne correspond pas à un PDF valide.")
                if decoder:
                    decoder.decode(chunk)
                checksum.update(chunk)
                stored.write(chunk)
                first_chunk = False

            if size_bytes == 0:
                raise UnprocessableError("Le fichier ne peut pas être vide.")
            if decoder:
                decoder.decode(b"", final=True)

        os.replace(temporary_path, destination)
    except UnicodeDecodeError as exc:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise UnsupportedMediaTypeError("Les fichiers texte doivent être encodés en UTF-8.") from exc
    except Exception:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise

    return StoredUpload(
        storage_path=relative_path.as_posix(),
        original_filename=original_filename,
        mime_type=MIME_TYPES[suffix],
        size_bytes=size_bytes,
        checksum_sha256=checksum.hexdigest(),
    )


def remove_stored_file(storage_path: str, *, settings: Settings | None = None) -> None:
    path = resolve_stored_file(storage_path, settings=settings, must_exist=False)
    path.unlink(missing_ok=True)


def resolve_stored_file(
    storage_path: str,
    *,
    settings: Settings | None = None,
    must_exist: bool = True,
) -> Path:
    root = _storage_root(settings)
    relative_path = PurePosixPath(storage_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise NotFoundError("Fichier introuvable.")

    path = (root / Path(*relative_path.parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise NotFoundError("Fichier introuvable.") from exc
    if must_exist and not path.is_file():
        raise NotFoundError("Le fichier associé au document est introuvable.")
    return path
