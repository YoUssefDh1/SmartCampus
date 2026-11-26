import hashlib

from app.db.migrate import _matches_migration_checksum, _migration_checksum


def test_migration_checksum_is_stable_across_line_endings():
    unix_sql = b"CREATE TABLE example (\n  id integer\n);\n"
    windows_sql = unix_sql.replace(b"\n", b"\r\n")

    assert _migration_checksum(unix_sql) == _migration_checksum(windows_sql)


def test_migration_checksum_accepts_legacy_raw_windows_checksum():
    windows_sql = b"CREATE TABLE example (\r\n  id integer\r\n);\r\n"
    legacy_checksum = hashlib.sha256(windows_sql).hexdigest()

    assert _matches_migration_checksum(windows_sql, legacy_checksum)
    assert _matches_migration_checksum(windows_sql, _migration_checksum(windows_sql))


def test_migration_checksum_still_rejects_changed_sql():
    original = b"CREATE TABLE example (id integer);\n"
    changed = b"CREATE TABLE example (id text);\n"

    assert not _matches_migration_checksum(changed, _migration_checksum(original))
