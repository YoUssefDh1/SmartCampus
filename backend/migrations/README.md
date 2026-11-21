# SQL migrations

The initial migration is the repository-root `schema.sql` file and is recorded as
`001_initial_schema`. Add subsequent changes as sequentially numbered SQL files here,
for example `002_add_example_column.sql`.

Applied migration files are checksum-verified. Do not edit an applied migration; add a
new migration instead. Migration scripts are run in a transaction and must not include
their own `BEGIN` or `COMMIT` statements.
