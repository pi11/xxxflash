from tortoise import migrations
from tortoise.migrations import operations as ops

# Full-text search over name + description (Russian stemming) and trigram fallback on name.
# pg_trgm lives in the `ext` schema (see app/db.py: ensure_schemas); search_path includes it.


class Migration(migrations.Migration):
    dependencies = [('models', '0001_initial')]

    initial = False

    operations = [
        ops.RunSQL(
            sql=[
                "ALTER TABLE games ADD COLUMN search tsvector GENERATED ALWAYS AS "
                "(to_tsvector('russian'::regconfig, coalesce(name, '') || ' ' || "
                "coalesce(description, ''))) STORED",
                "CREATE INDEX games_search_idx ON games USING gin (search)",
                "CREATE INDEX games_name_trgm_idx ON games USING gin (name ext.gin_trgm_ops)",
            ],
            reverse_sql=[
                "DROP INDEX IF EXISTS games_name_trgm_idx",
                "DROP INDEX IF EXISTS games_search_idx",
                "ALTER TABLE games DROP COLUMN IF EXISTS search",
            ],
        ),
    ]
