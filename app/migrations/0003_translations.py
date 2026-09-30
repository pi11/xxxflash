from tortoise import migrations
from tortoise.migrations import operations as ops
from app.models import TranslationStatus
from tortoise.fields.base import OnDelete
from tortoise import fields
from tortoise.indexes import Index

class Migration(migrations.Migration):
    dependencies = [('models', '0002_search')]

    initial = False

    operations = [
        ops.CreateModel(
            name='GameTranslation',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('game', fields.ForeignKeyField('models.Game', source_field='game_id', db_constraint=True, to_field='id', related_name='translations', on_delete=OnDelete.CASCADE)),
                ('language', fields.CharField(max_length=8)),
                ('name', fields.CharField(default='', max_length=300)),
                ('description', fields.TextField(default='', unique=False)),
                ('source_hash', fields.CharField(default='', max_length=64)),
                ('status', fields.CharEnumField(description='MACHINE: machine\nEDITED: edited\nFAILED: failed', enum_type=TranslationStatus, max_length=10)),
                ('error', fields.TextField(null=True, unique=False)),
                ('translated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={'table': 'game_translations', 'app': 'models', 'unique_together': (('game', 'language'),), 'indexes': [Index(fields=['language', 'status'])], 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='ThemeTranslation',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('theme', fields.ForeignKeyField('models.Theme', source_field='theme_id', db_constraint=True, to_field='id', related_name='translations', on_delete=OnDelete.CASCADE)),
                ('language', fields.CharField(max_length=8)),
                ('name', fields.CharField(max_length=250)),
            ],
            options={'table': 'theme_translations', 'app': 'models', 'unique_together': (('theme', 'language'),), 'pk_attr': 'id'},
            bases=['Model'],
        ),
            # English (and future non-Russian) full-text search over translated name + description.
        ops.RunSQL(
            sql=[
                "ALTER TABLE game_translations ADD COLUMN search tsvector GENERATED ALWAYS AS "
                "(to_tsvector('english'::regconfig, coalesce(name, '') || ' ' || "
                "coalesce(description, ''))) STORED",
                "CREATE INDEX game_translations_search_idx ON game_translations USING gin (search)",
                "CREATE INDEX game_translations_name_trgm_idx ON game_translations "
                "USING gin (name ext.gin_trgm_ops)",
            ],
            reverse_sql=[
                "DROP INDEX IF EXISTS game_translations_name_trgm_idx",
                "DROP INDEX IF EXISTS game_translations_search_idx",
                "ALTER TABLE game_translations DROP COLUMN IF EXISTS search",
            ],
        ),
]
