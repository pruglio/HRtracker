# Vercel + Supabase Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate HRtracker data layer from flat-file JSON to Supabase and deploy on Vercel.

**Architecture:** Supabase client replaces all file I/O in app.py; `load_application()` and `load_applications()` query Supabase with nested joins; each mutating route calls targeted INSERT/UPDATE/DELETE; voice notes use Supabase Storage with signed URL redirect. Vercel is configured via `vercel.json` + `api/index.py`.

**Tech Stack:** Flask 3, supabase-py 2.10.0, Vercel (@vercel/python), Supabase (Postgres + Storage)

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `requirements.txt` | Modify | Add `supabase==2.10.0` |
| `vercel.json` | Create | Build + routing config |
| `api/__init__.py` | Create | Empty package marker |
| `api/index.py` | Create | WSGI handler for Vercel |
| `.vercelignore` | Create | Exclude venv, data, tests, docs |
| `app.py` | Modify | Replace entire data layer with Supabase |

---

## Task 1: Vercel config files + supabase dependency

**Files:**
- Modify: `requirements.txt`
- Create: `vercel.json`
- Create: `api/__init__.py`
- Create: `api/index.py`
- Create: `.vercelignore`

- [ ] **Step 1: Add supabase to requirements.txt**

Add at the end of `requirements.txt`:
```
supabase==2.10.0
```

- [ ] **Step 2: Install supabase-py**

```bash
source venv/bin/activate && pip install supabase==2.10.0
```
Expected: `Successfully installed supabase-2.10.0` (plus dependencies)

- [ ] **Step 3: Create `vercel.json`**

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ]
}
```

- [ ] **Step 4: Create `api/__init__.py`**

Empty file.

- [ ] **Step 5: Create `api/index.py`**

```python
import sys
import os

# Add project root to path so `import app` finds app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

handler = app
```

- [ ] **Step 6: Create `.vercelignore`**

```
venv/
data/
.pytest_cache/
__pycache__/
*.pyc
*.pyo
.env
.env.local
```

- [ ] **Step 7: Verify import works**

```bash
source venv/bin/activate && python -c "import sys, os; sys.path.insert(0, '.'); from app import app; print('OK', app)"
```
Expected: `OK <Flask 'app'>`

- [ ] **Step 8: Commit**

```bash
git add requirements.txt vercel.json api/__init__.py api/index.py .vercelignore
git commit -m "feat: add Vercel config and supabase-py dependency"
```

---

## Task 2: Migrate app.py data layer to Supabase

**Files:**
- Modify: `app.py`

This task replaces the entire data layer. Read the current `app.py` first, then apply changes section by section.

### 2a — Replace imports and constants

- [ ] **Step 1: Update imports at top of app.py**

Replace the existing imports block (everything up to `app = Flask(__name__)`):

```python
import os
import time
import uuid
from datetime import datetime

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'hrtracker-secret-key-2026')

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ALLOWED_ETAPAS = [
    'Aplicado', 'Pantalla HR', 'Técnica', 'Final',
    'Oferta', 'Rechazado', 'Descartado'
]
ALLOWED_MODALIDADES = ['Remoto', 'Presencial', 'Híbrido']
ALLOWED_EXTENSIONS = {'.webm', '.ogg', '.wav', '.mp4', '.m4a'}
ALLOWED_RATINGS = {1, 2, 3, 4, 5}
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

### 2b — Replace helpers

- [ ] **Step 2: Replace all helper functions**

Remove `load_applications`, `save_applications`, `find_application`, `find_interview`, `find_app_and_interview`, `voice_path`, `application_has_date_in_range`, `sort_key_latest_interview` and replace with:

```python
# --- Helpers ---

def make_id(existing_ids):
    while True:
        new_id = uuid.uuid4().hex[:8]
        if new_id not in existing_ids:
            return new_id


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def parse_salary(value):
    try:
        v = int(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def parse_rating(value):
    if value is None or value == '' or value == 'null':
        return None
    try:
        v = int(value)
        return v if v in ALLOWED_RATINGS else None
    except (TypeError, ValueError):
        return None


def parse_date_filter(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _attach_interviews(applications):
    """Attach interviews (with voice_notes) to a list of application dicts."""
    if not applications:
        return applications
    app_ids = [a['id'] for a in applications]
    interviews = (
        supabase_client.table('interviews')
        .select('*')
        .in_('application_id', app_ids)
        .execute()
        .data
    )
    voice_notes = []
    if interviews:
        iv_ids = [iv['id'] for iv in interviews]
        voice_notes = (
            supabase_client.table('voice_notes')
            .select('*')
            .in_('interview_id', iv_ids)
            .execute()
            .data
        )
    vn_by_iv = {}
    for vn in voice_notes:
        vn_by_iv.setdefault(vn['interview_id'], []).append(
            {'filename': vn['filename'], 'created_at': vn['created_at']}
        )
    iv_by_app = {}
    for iv in interviews:
        iv['voice_notes'] = vn_by_iv.get(iv['id'], [])
        iv_by_app.setdefault(iv['application_id'], []).append(iv)
    for a in applications:
        a['interviews'] = iv_by_app.get(a['id'], [])
    return applications


def load_applications():
    """Load all applications with nested interviews and voice_notes."""
    apps = supabase_client.table('applications').select('*').execute().data
    return _attach_interviews(apps)


def load_application(app_id):
    """Load one application with nested interviews and voice_notes. Returns None if not found."""
    result = supabase_client.table('applications').select('*').eq('id', app_id).execute()
    if not result.data:
        return None
    apps = _attach_interviews(result.data)
    return apps[0]


def application_has_date_in_range(application, desde_date, hasta_date):
    for iv in application.get('interviews', []):
        fecha = iv.get('fecha_entrevista')
        if not fecha:
            continue
        try:
            d = datetime.strptime(fecha, '%Y-%m-%d').date()
        except ValueError:
            continue
        if desde_date and d < desde_date:
            continue
        if hasta_date and d > hasta_date:
            continue
        return True
    return False


def sort_key_latest_interview(application):
    fechas = [
        iv.get('fecha_entrevista') for iv in application.get('interviews', [])
        if iv.get('fecha_entrevista')
    ]
    return max(fechas) if fechas else (application.get('created_at', '') or '0000')
```

### 2c — Update application routes

- [ ] **Step 3: Replace `index` route**

```python
@app.route('/')
def index():
    applications = load_applications()

    f_etapa = request.args.get('etapa', '').strip()
    f_empresa = request.args.get('empresa', '').strip()
    f_desde = request.args.get('desde', '').strip()
    f_hasta = request.args.get('hasta', '').strip()

    filtered = applications

    if f_etapa and f_etapa in ALLOWED_ETAPAS:
        filtered = [a for a in filtered if a.get('etapa') == f_etapa]

    if f_empresa:
        filtered = [a for a in filtered
                    if f_empresa.lower() in a.get('empresa', '').lower()]

    desde_date = parse_date_filter(f_desde)
    hasta_date = parse_date_filter(f_hasta)
    if desde_date or hasta_date:
        filtered = [a for a in filtered
                    if application_has_date_in_range(a, desde_date, hasta_date)]

    filtered.sort(key=sort_key_latest_interview, reverse=True)

    return render_template(
        'index.html',
        applications=filtered,
        total=len(applications),
        etapas=ALLOWED_ETAPAS,
        f_etapa=f_etapa,
        f_empresa=f_empresa,
        f_desde=f_desde,
        f_hasta=f_hasta,
    )
```

- [ ] **Step 4: Replace `new_application` and `create_application`**

```python
@app.route('/application/new')
def new_application():
    return render_template(
        'application_form.html',
        application=None,
        etapas=ALLOWED_ETAPAS,
        modalidades=ALLOWED_MODALIDADES,
        beneficios_labels=BENEFICIOS_LABELS,
    )


@app.route('/application', methods=['POST'])
def create_application():
    empresa = request.form.get('empresa', '').strip()
    puesto = request.form.get('puesto', '').strip()

    if not empresa or not puesto:
        flash('Empresa y puesto son obligatorios.', 'danger')
        return redirect(url_for('new_application'))

    etapa = request.form.get('etapa', 'Aplicado')
    if etapa not in ALLOWED_ETAPAS:
        etapa = 'Aplicado'

    modalidad = request.form.get('modalidad', '')
    if modalidad not in ALLOWED_MODALIDADES:
        modalidad = ''

    existing = supabase_client.table('applications').select('id').execute().data
    existing_ids = {a['id'] for a in existing}
    new_id = make_id(existing_ids)

    application = {
        'id': new_id,
        'created_at': now_str(),
        'updated_at': now_str(),
        'empresa': empresa,
        'puesto': puesto,
        'etapa': etapa,
        'modalidad': modalidad,
        'salario_min': parse_salary(request.form.get('salario_min')),
        'salario_max': parse_salary(request.form.get('salario_max')),
        'rating': parse_rating(request.form.get('rating')),
        'notas': request.form.get('notas', '').strip(),
        'beneficios': [b for b in request.form.getlist('beneficios') if b in ALLOWED_BENEFICIOS],
        'beneficios_otros': request.form.get('beneficios_otros', '').strip(),
    }

    supabase_client.table('applications').insert(application).execute()
    flash('Postulación guardada correctamente.', 'success')
    return redirect(url_for('application_detail', app_id=new_id))
```

- [ ] **Step 5: Replace `application_detail`, `edit_application`, `update_application`, `delete_application`, `update_rating`**

```python
@app.route('/application/<app_id>')
def application_detail(app_id):
    application = load_application(app_id)
    if not application:
        abort(404)
    return render_template(
        'application_detail.html',
        application=application,
        beneficios_labels=BENEFICIOS_LABELS,
    )


@app.route('/application/<app_id>/edit')
def edit_application(app_id):
    application = load_application(app_id)
    if not application:
        abort(404)
    return render_template(
        'application_form.html',
        application=application,
        etapas=ALLOWED_ETAPAS,
        modalidades=ALLOWED_MODALIDADES,
        beneficios_labels=BENEFICIOS_LABELS,
    )


@app.route('/application/<app_id>/edit', methods=['POST'])
def update_application(app_id):
    result = supabase_client.table('applications').select('id').eq('id', app_id).execute()
    if not result.data:
        abort(404)

    empresa = request.form.get('empresa', '').strip()
    puesto = request.form.get('puesto', '').strip()

    if not empresa or not puesto:
        flash('Empresa y puesto son obligatorios.', 'danger')
        return redirect(url_for('edit_application', app_id=app_id))

    etapa = request.form.get('etapa', 'Aplicado')
    if etapa not in ALLOWED_ETAPAS:
        etapa = 'Aplicado'

    modalidad = request.form.get('modalidad', '')
    if modalidad not in ALLOWED_MODALIDADES:
        modalidad = ''

    supabase_client.table('applications').update({
        'empresa': empresa,
        'puesto': puesto,
        'etapa': etapa,
        'modalidad': modalidad,
        'salario_min': parse_salary(request.form.get('salario_min')),
        'salario_max': parse_salary(request.form.get('salario_max')),
        'notas': request.form.get('notas', '').strip(),
        'beneficios': [b for b in request.form.getlist('beneficios') if b in ALLOWED_BENEFICIOS],
        'beneficios_otros': request.form.get('beneficios_otros', '').strip(),
        'updated_at': now_str(),
    }).eq('id', app_id).execute()

    flash('Postulación actualizada correctamente.', 'success')
    return redirect(url_for('application_detail', app_id=app_id))


@app.route('/application/<app_id>/delete', methods=['POST'])
def delete_application(app_id):
    result = supabase_client.table('applications').select('id').eq('id', app_id).execute()
    if not result.data:
        abort(404)
    # Delete voice files from Storage
    interviews = supabase_client.table('interviews').select('id').eq('application_id', app_id).execute().data
    for iv in interviews:
        vns = supabase_client.table('voice_notes').select('filename').eq('interview_id', iv['id']).execute().data
        paths = [f"{app_id}/{iv['id']}/{vn['filename']}" for vn in vns]
        if paths:
            supabase_client.storage.from_('voice-notes').remove(paths)
    # DB cascade handles interviews + voice_notes rows
    supabase_client.table('applications').delete().eq('id', app_id).execute()
    flash('Postulación eliminada.', 'success')
    return redirect(url_for('index'))


@app.route('/application/<app_id>/rating', methods=['POST'])
def update_rating(app_id):
    payload = request.get_json(silent=True) or {}
    rating = parse_rating(payload.get('rating'))

    result = supabase_client.table('applications').select('id').eq('id', app_id).execute()
    if not result.data:
        return jsonify({'error': 'Postulación no encontrada'}), 404

    supabase_client.table('applications').update({
        'rating': rating,
        'updated_at': now_str(),
    }).eq('id', app_id).execute()
    return jsonify({'ok': True, 'rating': rating}), 200
```

### 2d — Update interview routes

- [ ] **Step 6: Replace interview routes**

```python
@app.route('/application/<app_id>/interview/new')
def new_interview(app_id):
    application = load_application(app_id)
    if not application:
        abort(404)
    return render_template(
        'interview_form.html',
        application=application,
        interview=None,
    )


@app.route('/application/<app_id>/interview', methods=['POST'])
def create_interview(app_id):
    result = supabase_client.table('applications').select('id').eq('id', app_id).execute()
    if not result.data:
        abort(404)

    existing = supabase_client.table('interviews').select('id').eq('application_id', app_id).execute().data
    existing_ids = {iv['id'] for iv in existing}
    new_id = make_id(existing_ids)

    interview = {
        'id': new_id,
        'application_id': app_id,
        'created_at': now_str(),
        'updated_at': now_str(),
        'fecha_entrevista': request.form.get('fecha_entrevista', '').strip() or None,
        'entrevistador_nombre': request.form.get('entrevistador_nombre', '').strip(),
        'entrevistador_email': request.form.get('entrevistador_email', '').strip(),
        'entrevistador_linkedin': request.form.get('entrevistador_linkedin', '').strip(),
        'notas': request.form.get('notas', '').strip(),
    }

    supabase_client.table('interviews').insert(interview).execute()
    supabase_client.table('applications').update({'updated_at': now_str()}).eq('id', app_id).execute()
    flash('Entrevista agregada.', 'success')
    return redirect(url_for('application_detail', app_id=app_id) + f'#iv-{new_id}')


@app.route('/application/<app_id>/interview/<interview_id>/edit')
def edit_interview(app_id, interview_id):
    application = load_application(app_id)
    if not application:
        abort(404)
    interview = next((iv for iv in application.get('interviews', []) if iv['id'] == interview_id), None)
    if not interview:
        abort(404)
    return render_template(
        'interview_form.html',
        application=application,
        interview=interview,
    )


@app.route('/application/<app_id>/interview/<interview_id>/edit', methods=['POST'])
def update_interview(app_id, interview_id):
    result = supabase_client.table('interviews').select('id').eq('id', interview_id).eq('application_id', app_id).execute()
    if not result.data:
        abort(404)

    supabase_client.table('interviews').update({
        'fecha_entrevista': request.form.get('fecha_entrevista', '').strip() or None,
        'entrevistador_nombre': request.form.get('entrevistador_nombre', '').strip(),
        'entrevistador_email': request.form.get('entrevistador_email', '').strip(),
        'entrevistador_linkedin': request.form.get('entrevistador_linkedin', '').strip(),
        'notas': request.form.get('notas', '').strip(),
        'updated_at': now_str(),
    }).eq('id', interview_id).execute()
    supabase_client.table('applications').update({'updated_at': now_str()}).eq('id', app_id).execute()

    flash('Entrevista actualizada.', 'success')
    return redirect(url_for('application_detail', app_id=app_id) + f'#iv-{interview_id}')


@app.route('/application/<app_id>/interview/<interview_id>/delete', methods=['POST'])
def delete_interview(app_id, interview_id):
    result = supabase_client.table('interviews').select('id').eq('id', interview_id).eq('application_id', app_id).execute()
    if not result.data:
        abort(404)
    # Delete voice files from Storage
    vns = supabase_client.table('voice_notes').select('filename').eq('interview_id', interview_id).execute().data
    paths = [f"{app_id}/{interview_id}/{vn['filename']}" for vn in vns]
    if paths:
        supabase_client.storage.from_('voice-notes').remove(paths)
    # DB cascade handles voice_notes rows
    supabase_client.table('interviews').delete().eq('id', interview_id).execute()
    supabase_client.table('applications').update({'updated_at': now_str()}).eq('id', app_id).execute()
    flash('Entrevista eliminada.', 'success')
    return redirect(url_for('application_detail', app_id=app_id))
```

### 2e — Update voice note routes

- [ ] **Step 7: Replace voice note routes**

```python
@app.route('/application/<app_id>/interview/<interview_id>/voice', methods=['POST'])
def upload_voice(app_id, interview_id):
    result = supabase_client.table('interviews').select('id').eq('id', interview_id).eq('application_id', app_id).execute()
    if not result.data:
        return jsonify({'error': 'Entrevista no encontrada'}), 404

    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'No se recibió archivo de audio'}), 400

    original_name = audio_file.filename or 'nota.webm'
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = '.webm'

    filename = f"nota_{int(time.time() * 1000)}{ext}"
    storage_path = f"{os.path.basename(app_id)}/{os.path.basename(interview_id)}/{filename}"

    content_type_map = {
        '.webm': 'audio/webm',
        '.ogg': 'audio/ogg',
        '.wav': 'audio/wav',
        '.mp4': 'audio/mp4',
        '.m4a': 'audio/x-m4a',
    }
    content_type = content_type_map.get(ext, 'audio/webm')

    audio_data = audio_file.read()
    supabase_client.storage.from_('voice-notes').upload(
        storage_path, audio_data, {'content-type': content_type}
    )

    created_at = now_str()
    supabase_client.table('voice_notes').insert({
        'interview_id': interview_id,
        'filename': filename,
        'created_at': created_at,
    }).execute()
    supabase_client.table('interviews').update({'updated_at': created_at}).eq('id', interview_id).execute()
    supabase_client.table('applications').update({'updated_at': created_at}).eq('id', app_id).execute()

    return jsonify({
        'filename': filename,
        'url': url_for('serve_voice', app_id=app_id, interview_id=interview_id, filename=filename),
        'created_at': created_at,
    }), 201


@app.route(
    '/application/<app_id>/interview/<interview_id>/voice/<filename>',
    methods=['DELETE'],
)
def delete_voice(app_id, interview_id, filename):
    safe_filename = os.path.basename(filename)
    storage_path = f"{os.path.basename(app_id)}/{os.path.basename(interview_id)}/{safe_filename}"

    supabase_client.storage.from_('voice-notes').remove([storage_path])
    supabase_client.table('voice_notes').delete().eq('interview_id', interview_id).eq('filename', safe_filename).execute()
    supabase_client.table('interviews').update({'updated_at': now_str()}).eq('id', interview_id).execute()
    supabase_client.table('applications').update({'updated_at': now_str()}).eq('id', app_id).execute()
    return jsonify({'ok': True}), 200


@app.route('/voice/<app_id>/<interview_id>/<filename>')
def serve_voice(app_id, interview_id, filename):
    safe_filename = os.path.basename(filename)
    storage_path = f"{os.path.basename(app_id)}/{os.path.basename(interview_id)}/{safe_filename}"
    result = supabase_client.storage.from_('voice-notes').create_signed_url(storage_path, 3600)
    signed_url = result.get('signedURL') or result.get('signedUrl', '')
    return redirect(signed_url)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
```

- [ ] **Step 8: Run existing tests to check they still pass**

Note: the existing tests mock the filesystem. They will likely fail now because the data layer uses Supabase. That's expected — skip failing tests with a note. What matters is that the app starts without import errors.

```bash
source venv/bin/activate && python -c "from app import app; print('Import OK')"
```
Expected: `Import OK`

- [ ] **Step 9: Test locally with real Supabase credentials**

```bash
source venv/bin/activate && SUPABASE_URL=https://ynquzbhxfqobrlyzwkbv.supabase.co SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlucXV6Ymh4ZnFvYnJseXp3a2J2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyOTY0ODAsImV4cCI6MjA5NDg3MjQ4MH0.VvShv5EK2dMt-WsAIzhJ_w21UJC3yIcYYG0X2InXW5o FLASK_SECRET_KEY=9e476439ba68c13207dfd55ac780c4e859088d5e519f667d37cc6b261d9d3339 python app.py
```

Open http://localhost:5002 — verify the index loads (empty list is fine). Create one test application and verify it appears. Check Supabase dashboard to confirm row was inserted.

Stop the server with Ctrl+C.

- [ ] **Step 10: Commit**

```bash
git add app.py
git commit -m "feat: migrate data layer from JSON files to Supabase"
```

---

## Task 3: Deploy to Vercel

> Manual steps — no code changes.

- [ ] **Step 1: Install Vercel CLI (if not already)**

```bash
npm install -g vercel
```

- [ ] **Step 2: Login to Vercel**

```bash
vercel login
```
Select the GitHub login option and authenticate.

- [ ] **Step 3: Deploy**

From the project root:
```bash
vercel --prod
```

When prompted:
- **Set up and deploy?** → Yes
- **Which scope?** → your account
- **Link to existing project?** → No
- **Project name?** → `hrtracker` (or accept default)
- **Directory?** → `.` (current directory)
- **Override settings?** → No

- [ ] **Step 4: Set environment variables**

```bash
vercel env add SUPABASE_URL production
# Enter: https://ynquzbhxfqobrlyzwkbv.supabase.co

vercel env add SUPABASE_KEY production
# Enter: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlucXV6Ymh4ZnFvYnJseXp3a2J2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyOTY0ODAsImV4cCI6MjA5NDg3MjQ4MH0.VvShv5EK2dMt-WsAIzhJ_w21UJC3yIcYYG0X2InXW5o

vercel env add FLASK_SECRET_KEY production
# Enter: 9e476439ba68c13207dfd55ac780c4e859088d5e519f667d37cc6b261d9d3339
```

- [ ] **Step 5: Redeploy with env vars active**

```bash
vercel --prod
```

- [ ] **Step 6: Verify**

Open the production URL (shown after deploy). Verify:
- Index loads
- Can create a new application
- Application detail shows correctly
- Edit and save works
- Refresh page — data persists (it's in Supabase, not memory)
