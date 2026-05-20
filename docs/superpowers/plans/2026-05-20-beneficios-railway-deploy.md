# Beneficios + Railway Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar campo de beneficios (checkboxes + texto libre) a postulaciones, y hacer deploy en Railway.

**Architecture:** Se agrega `ALLOWED_BENEFICIOS` y `BENEFICIOS_LABELS` como constantes en `app.py`; `create_application` y `update_application` leen los nuevos campos del form; el template de form muestra los checkboxes y el textarea; el template de detalle muestra los beneficios como badges. El deploy en Railway es configuración manual sin cambios de código.

**Tech Stack:** Flask 3, Jinja2, Bootstrap 5, pytest, Railway (gunicorn)

---

## File Map

| File | Acción | Qué cambia |
|------|--------|------------|
| `app.py` | Modify | Agregar `ALLOWED_BENEFICIOS`, `BENEFICIOS_LABELS`; actualizar `create_application`, `update_application`, `new_application`, `edit_application`, `application_detail` |
| `templates/application_form.html` | Modify | Nueva sección "Beneficios" con checkboxes + textarea |
| `templates/application_detail.html` | Modify | Bloque de badges de beneficios |
| `requirements.txt` | Modify | Agregar `pytest` |
| `tests/conftest.py` | Create | Fixtures: `app` (con tmp_path) y `client` |
| `tests/test_beneficios.py` | Create | Tests de parsing y validación de beneficios |

---

## Task 1: Infraestructura de tests

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Agregar pytest a requirements.txt**

Agregar al final de `requirements.txt`:
```
pytest==8.2.2
```

- [ ] **Step 2: Instalar**

```bash
source venv/bin/activate && pip install pytest==8.2.2
```
Expected: `Successfully installed pytest-8.2.2`

- [ ] **Step 3: Crear `tests/__init__.py`**

Archivo vacío:
```python
```

- [ ] **Step 4: Crear `tests/conftest.py`**

```python
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
    # El redirect va a /application/<id>
    location = rv.headers['Location']
    app_id = location.rstrip('/').split('/')[-1]
    return client, app_id
```

- [ ] **Step 5: Verificar que pytest arranca sin errores**

```bash
source venv/bin/activate && pytest tests/ -v --collect-only
```
Expected: `no tests ran` (sin error de importación)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/__init__.py tests/conftest.py
git commit -m "test: set up pytest infrastructure with tmp_path fixtures"
```

---

## Task 2: Backend — constantes y parsing (TDD)

**Files:**
- Create: `tests/test_beneficios.py`
- Modify: `app.py`

- [ ] **Step 1: Escribir tests que fallan**

Crear `tests/test_beneficios.py`:
```python
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
```

- [ ] **Step 2: Correr para verificar que fallan**

```bash
source venv/bin/activate && pytest tests/test_beneficios.py -v
```
Expected: 4 FAILED con `KeyError: 'beneficios'` o similar

- [ ] **Step 3: Implementar en `app.py`**

Después de `ALLOWED_RATINGS = {1, 2, 3, 4, 5}` agregar:

```python
ALLOWED_BENEFICIOS = {
    'obra_social', 'bono_anual', 'stock_options', 'home_office',
    'horario_flexible', 'vacaciones_extra', 'vehiculo', 'comidas',
}

BENEFICIOS_LABELS = {
    'obra_social': 'Obra social / prepaga',
    'bono_anual': 'Bono anual',
    'stock_options': 'Stock options / equity',
    'home_office': 'Home office',
    'horario_flexible': 'Horario flexible',
    'vacaciones_extra': 'Vacaciones extra (+15 días)',
    'vehiculo': 'Vehículo / transporte',
    'comidas': 'Comidas / viáticos',
}
```

- [ ] **Step 4: Actualizar `create_application`**

Dentro del dict `application = { ... }`, después de `'rating': parse_rating(...)`, agregar:
```python
        'beneficios': [b for b in request.form.getlist('beneficios') if b in ALLOWED_BENEFICIOS],
        'beneficios_otros': request.form.get('beneficios_otros', '').strip(),
```

- [ ] **Step 5: Actualizar `update_application`**

En la sección donde se asignan los campos del application (después de `application['notas'] = ...`), agregar:
```python
    application['beneficios'] = [b for b in request.form.getlist('beneficios') if b in ALLOWED_BENEFICIOS]
    application['beneficios_otros'] = request.form.get('beneficios_otros', '').strip()
```

- [ ] **Step 6: Correr tests para verificar que pasan**

```bash
source venv/bin/activate && pytest tests/test_beneficios.py -v
```
Expected: 4 PASSED

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_beneficios.py
git commit -m "feat: add beneficios field to application model with validation"
```

---

## Task 3: Template — formulario de postulación

**Files:**
- Modify: `templates/application_form.html`
- Modify: `app.py` (pasar `BENEFICIOS_LABELS` a los routes del form)

- [ ] **Step 1: Pasar `BENEFICIOS_LABELS` a `new_application` y `edit_application`**

En `new_application`:
```python
    return render_template(
        'application_form.html',
        application=None,
        etapas=ALLOWED_ETAPAS,
        modalidades=ALLOWED_MODALIDADES,
        beneficios_labels=BENEFICIOS_LABELS,
    )
```

En `edit_application`:
```python
    return render_template(
        'application_form.html',
        application=application,
        etapas=ALLOWED_ETAPAS,
        modalidades=ALLOWED_MODALIDADES,
        beneficios_labels=BENEFICIOS_LABELS,
    )
```

- [ ] **Step 2: Agregar sección "Beneficios" en `application_form.html`**

Insertar entre el cierre del bloque Notas (`</textarea>`) y los botones (`{# === Buttons === #}`):

```html
          {# === Beneficios === #}
          <p class="form-section-title">Beneficios</p>
          <div class="row g-2 mb-2">
            {% for key, label in beneficios_labels.items() %}
            <div class="col-6 col-md-3">
              <div class="form-check">
                <input class="form-check-input" type="checkbox"
                       name="beneficios" value="{{ key }}"
                       id="ben-{{ key }}"
                       {% if application and key in (application.beneficios or []) %}checked{% endif %}>
                <label class="form-check-label small" for="ben-{{ key }}">{{ label }}</label>
              </div>
            </div>
            {% endfor %}
          </div>
          <div class="mb-3">
            <label for="beneficios_otros" class="form-label small text-muted">Otros beneficios</label>
            <input type="text" class="form-control form-control-sm" id="beneficios_otros"
                   name="beneficios_otros" placeholder="Ej: 4 semanas de vacaciones, notebook..."
                   value="{{ application.beneficios_otros if application else '' }}">
          </div>
```

- [ ] **Step 3: Verificar manualmente**

```bash
source venv/bin/activate && python app.py
```
Abrir http://localhost:5002/application/new — debe verse la sección "Beneficios" con 8 checkboxes y el campo de texto. Crear una postulación con algunos beneficios y verificar que se guarda en `data/applications.json`.

- [ ] **Step 4: Correr todos los tests**

```bash
source venv/bin/activate && pytest tests/ -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app.py templates/application_form.html
git commit -m "feat: add beneficios checkboxes and free-text field to application form"
```

---

## Task 4: Template — vista de detalle

**Files:**
- Modify: `templates/application_detail.html`
- Modify: `app.py` (pasar `BENEFICIOS_LABELS` al route de detalle)

- [ ] **Step 1: Pasar `BENEFICIOS_LABELS` a `application_detail`**

```python
@app.route('/application/<app_id>')
def application_detail(app_id):
    applications = load_applications()
    application = find_application(applications, app_id)
    if not application:
        abort(404)
    return render_template(
        'application_detail.html',
        application=application,
        beneficios_labels=BENEFICIOS_LABELS,
    )
```

- [ ] **Step 2: Agregar bloque de beneficios en `application_detail.html`**

Insertar después del bloque `{# === Application-level notes === #}` (después del `{% endif %}` que cierra ese bloque) y antes de `{# === Interviews section === #}`:

```html
{# === Beneficios === #}
{% set tiene_beneficios = application.beneficios or application.beneficios_otros %}
{% if tiene_beneficios %}
<div class="card shadow-sm mb-3">
  <div class="card-body">
    <p class="form-section-title mb-2">Beneficios</p>
    {% if application.beneficios %}
    <div class="d-flex flex-wrap gap-1 mb-2">
      {% for key in application.beneficios %}
        <span class="badge rounded-pill border border-primary text-primary">
          {{ beneficios_labels.get(key, key) }}
        </span>
      {% endfor %}
    </div>
    {% endif %}
    {% if application.beneficios_otros %}
    <p class="small text-muted mb-0">
      <i class="fas fa-plus-circle me-1"></i>{{ application.beneficios_otros }}
    </p>
    {% endif %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 3: Verificar manualmente**

```bash
source venv/bin/activate && python app.py
```
Abrir una postulación con beneficios — debe mostrar badges. Abrir una sin beneficios — no debe mostrar la sección. Probar editar y cambiar beneficios.

- [ ] **Step 4: Correr todos los tests**

```bash
source venv/bin/activate && pytest tests/ -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app.py templates/application_detail.html
git commit -m "feat: display beneficios badges on application detail view"
```

---

## Task 5: Deploy en Railway

> No hay cambios de código en este task. Son pasos manuales de configuración.

- [ ] **Step 1: Asegurarse que el repo está en GitHub**

```bash
git remote -v
```
Si no hay remote, crear repo en https://github.com/new y luego:
```bash
git remote add origin https://github.com/<tu-usuario>/HRtracker.git
git push -u origin main
```

- [ ] **Step 2: Crear proyecto en Railway**

1. Ir a https://railway.app → **New Project**
2. Seleccionar **Deploy from GitHub repo**
3. Autorizar Railway en GitHub si es necesario
4. Seleccionar el repo `HRtracker`
5. Railway detecta el `Procfile` y empieza el build automáticamente

- [ ] **Step 3: Agregar volumen persistente**

1. En el dashboard del proyecto, hacer clic en **+ New** → **Volume**
2. En **Mount Path** ingresar: `/data`
3. Hacer clic en **Add Volume**

- [ ] **Step 4: Configurar variables de entorno**

En el servicio web (el que tiene el `Procfile`), ir a **Variables** y agregar:

| Variable | Valor |
|----------|-------|
| `DATA_DIR` | `/data` |
| `FLASK_SECRET_KEY` | Generar con: `python -c "import secrets; print(secrets.token_hex(32))"` |

Railway ya inyecta `PORT` automáticamente — no agregar.

- [ ] **Step 5: Verificar deploy**

1. Ir a **Deployments** — el build debe mostrar `Build successful`
2. Copiar la URL pública (ej: `hrtracker-production.up.railway.app`)
3. Abrir la URL — debe cargar el listado de postulaciones
4. Crear una postulación de prueba y recargar — debe persistir

- [ ] **Step 6: (Opcional) Dominio custom**

En **Settings** → **Networking** → **Custom Domain** se puede agregar un dominio propio.
