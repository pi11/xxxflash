from tortoise import migrations
from tortoise.migrations import operations as ops
from app.models import Compat, today
from tortoise.fields.base import OnDelete
from tortoise import fields
from tortoise.indexes import Index

class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='Ban',
            fields=[
                ('ip', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=45)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'bans', 'app': 'models', 'pk_attr': 'ip'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='BannedWord',
            fields=[
                ('word', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=100)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'banned_words', 'app': 'models', 'pk_attr': 'word'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Theme',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('name', fields.CharField(max_length=250)),
                ('slug', fields.CharField(unique=True, max_length=100)),
                ('active', fields.BooleanField(default=True)),
                ('sort_order', fields.IntField(default=0)),
                ('game_count', fields.IntField(default=0)),
            ],
            options={'table': 'themes', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='User',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('username', fields.CharField(unique=True, max_length=150)),
                ('email', fields.CharField(null=True, unique=True, max_length=254)),
                ('is_staff', fields.BooleanField(default=False)),
                ('is_active', fields.BooleanField(default=True)),
                ('score', fields.IntField(default=0)),
                ('avatar', fields.CharField(null=True, max_length=255)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('last_login', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'users', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Game',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('name', fields.CharField(max_length=150)),
                ('description', fields.TextField(default='', unique=False)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='games', on_delete=OnDelete.RESTRICT)),
                ('swf_path', fields.CharField(max_length=255)),
                ('thumb_path', fields.CharField(null=True, max_length=255)),
                ('filesize', fields.BigIntField(default=0)),
                ('rate', fields.IntField(default=0)),
                ('views', fields.IntField(default=0)),
                ('xrate', fields.FloatField(default=0)),
                ('active', fields.BooleanField(default=True)),
                ('published_at', fields.DateField(default=today)),
                ('sha512', fields.CharField(unique=True, max_length=128)),
                ('swf_version', fields.SmallIntField(null=True)),
                ('is_as3', fields.BooleanField(default=False)),
                ('width', fields.IntField(default=0)),
                ('height', fields.IntField(default=0)),
                ('compat', fields.CharEnumField(default=Compat.UNKNOWN, description='UNKNOWN: unknown\nOK: ok\nAS3: as3\nBROKEN: broken\nMISSING: missing', enum_type=Compat, max_length=10)),
                ('themes', fields.ManyToManyField('models.Theme', unique=True, db_constraint=True, through='game_themes', forward_key='theme_id', backward_key='game_id', related_name='games', on_delete=OnDelete.CASCADE)),
            ],
            options={'table': 'games', 'app': 'models', 'indexes': [Index(fields=['active', 'published_at']), Index(fields=['rate']), Index(fields=['xrate']), Index(fields=['views'])], 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Comment',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('game', fields.ForeignKeyField('models.Game', source_field='game_id', db_constraint=True, to_field='id', related_name='comments', on_delete=OnDelete.CASCADE)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='comments', on_delete=OnDelete.CASCADE)),
                ('text', fields.TextField(unique=False)),
                ('ip', fields.CharField(null=True, max_length=45)),
                ('ua', fields.CharField(null=True, max_length=250)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'comments', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='LoginToken',
            fields=[
                ('token_hash', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='login_tokens', on_delete=OnDelete.CASCADE)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('expires_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('used_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'login_tokens', 'app': 'models', 'pk_attr': 'token_hash'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Screenshot',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('game', fields.ForeignKeyField('models.Game', source_field='game_id', db_constraint=True, to_field='id', related_name='screenshots', on_delete=OnDelete.CASCADE)),
                ('image_path', fields.CharField(max_length=255)),
            ],
            options={'table': 'screenshots', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Vote',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('game', fields.ForeignKeyField('models.Game', source_field='game_id', db_constraint=True, to_field='id', related_name='votes', on_delete=OnDelete.CASCADE)),
                ('ip', fields.CharField(max_length=45)),
                ('value', fields.SmallIntField()),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', null=True, db_constraint=True, to_field='id', related_name='votes', on_delete=OnDelete.SET_NULL)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'votes', 'app': 'models', 'indexes': [Index(fields=['game_id', 'ip'])], 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
