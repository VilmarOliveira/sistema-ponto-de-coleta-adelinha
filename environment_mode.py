"""Explicit staging mode; never enables Flask's debug/testing mode."""
import hashlib
import json
import os
from pathlib import Path
from flask import current_app, has_app_context
from psycopg.conninfo import conninfo_to_dict


def is_test_environment(config=None):
    if str(os.getenv('SITE_ENVIRONMENT', '')).strip().lower() == 'test':
        return True
    if config is None and has_app_context():
        config = current_app.config
    return str((config or {}).get('SITE_ENVIRONMENT', '')).strip().lower() == 'test'


def database_fingerprint(database):
    if str(database).startswith(('postgresql://', 'postgres://')):
        c = conninfo_to_dict(database)
        identity = (c.get('host', '').lower().replace('-pooler.', '.'), c.get('dbname'), c.get('port', '5432'))
    else:
        identity = ('sqlite', str(Path(database).resolve()))
    return hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()


def test_integration_enabled(name, config=None):
    """Explicit opt-in for Google/Gmail only; payment guards stay unconditional."""
    if name not in ('GOOGLE_LOGIN', 'EMAIL'):
        return False
    if config is None and has_app_context():
        config = current_app.config
    key = 'STAGING_' + name + '_ENABLED'
    return str((config or {}).get(key, os.getenv(key, '0'))).strip().lower() in ('1', 'true')
