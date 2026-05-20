import json
import app as app_module


def test_create_application_saves_beneficios(client):
    """Beneficios válidos se guardan en la aplicación."""
    rv = client.post('/application', data={
        'empresa': 'Acme',
        'puesto': 'Dev',
        'beneficios': ['obra_social', 'bono_anual'],
        'beneficios_otros': 'Auto de empresa',
    }, follow_redirects=False)
    assert rv.status_code == 302

    with open(app_module.DATA_FILE) as f:
        apps = json.load(f)

    assert len(apps) == 1
    assert apps[0]['beneficios'] == ['obra_social', 'bono_anual']
    assert apps[0]['beneficios_otros'] == 'Auto de empresa'


def test_create_application_filters_invalid_beneficios(client):
    """Claves inválidas son descartadas silenciosamente."""
    rv = client.post('/application', data={
        'empresa': 'Acme',
        'puesto': 'Dev',
        'beneficios': ['obra_social', 'coche_oficial_invalido'],
    }, follow_redirects=False)
    assert rv.status_code == 302

    with open(app_module.DATA_FILE) as f:
        apps = json.load(f)

    assert apps[0]['beneficios'] == ['obra_social']


def test_create_application_empty_beneficios(client):
    """Sin beneficios seleccionados se guardan listas/strings vacíos."""
    rv = client.post('/application', data={
        'empresa': 'Acme',
        'puesto': 'Dev',
    }, follow_redirects=False)
    assert rv.status_code == 302

    with open(app_module.DATA_FILE) as f:
        apps = json.load(f)

    assert apps[0]['beneficios'] == []
    assert apps[0]['beneficios_otros'] == ''


def test_update_application_updates_beneficios(app_with_one):
    """update_application reemplaza beneficios correctamente."""
    client, app_id = app_with_one

    rv = client.post(f'/application/{app_id}/edit', data={
        'empresa': 'Acme',
        'puesto': 'Dev',
        'beneficios': ['home_office', 'horario_flexible'],
        'beneficios_otros': '',
    }, follow_redirects=False)
    assert rv.status_code == 302

    with open(app_module.DATA_FILE) as f:
        apps = json.load(f)

    app_obj = next(a for a in apps if a['id'] == app_id)
    assert app_obj['beneficios'] == ['home_office', 'horario_flexible']
    assert app_obj['beneficios_otros'] == ''
