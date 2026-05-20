import json
import os
import pytest
import app as app_module
from app import app as flask_app


@pytest.fixture
def app(tmp_path):
    """Flask app con DATA_DIR apuntando a un directorio temporal."""
    flask_app.config['TESTING'] = True
    # Redirigir I/O a tmp_path para cada test
    app_module.DATA_DIR = str(tmp_path)
    app_module.DATA_FILE = str(tmp_path / 'applications.json')
    app_module.VOICE_DIR = str(tmp_path / 'voice_notes')
    yield flask_app
    flask_app.config['TESTING'] = False


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_with_one(client):
    """Crea una postulación base y devuelve (client, app_id)."""
    rv = client.post('/application', data={
        'empresa': 'Acme',
        'puesto': 'Dev',
        'etapa': 'Aplicado',
    }, follow_redirects=False)
    assert rv.status_code == 302, f"Expected redirect, got {rv.status_code}: {rv.data}"
    # El redirect va a /application/<id>
    location = rv.headers['Location']
    app_id = location.rstrip('/').split('/')[-1]
    return client, app_id
