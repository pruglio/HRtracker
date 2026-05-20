# Interview Datetime + Home Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional interview time, computed "Próxima entrevista" status, an upcoming-interviews panel on home, and stage-ordered application list.

**Architecture:** Pure Python logic for computed fields (no new DB queries at runtime). One new DB column (`hora_entrevista TEXT`). All changes stay in `app.py` + three templates. No new routes.

**Tech Stack:** Flask 3, supabase-py 2.10.0, Jinja2, Bootstrap 5, pytest

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| Supabase migration | Apply | Add `hora_entrevista TEXT DEFAULT ''` to `interviews` |
| `app.py` | Modify | Add `ETAPA_ORDER`, `compute_proxima_entrevista()`, update `index()`, update `create_interview`/`update_interview` |
| `tests/test_home_features.py` | Create | Unit tests for pure Python logic |
| `templates/interview_form.html` | Modify | Split date field into date + time side by side |
| `templates/_interview_card.html` | Modify | Show time alongside date in header |
| `templates/index.html` | Modify | Add upcoming panel, add "Próxima entrevista" column, pass `upcoming_interviews` |

---

## Task 1: DB schema — add hora_entrevista

**Files:**
- Supabase project: `ynquzbhxfqobrlyzwkbv`

- [ ] **Step 1: Apply migration**

Use the Supabase MCP tool `apply_migration` with:
- project_id: `ynquzbhxfqobrlyzwkbv`
- name: `add_hora_entrevista`
- query:
```sql
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS hora_entrevista TEXT NOT NULL DEFAULT '';
```

- [ ] **Step 2: Verify column exists**

Use `execute_sql`:
```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'interviews' AND column_name = 'hora_entrevista';
```

Expected: one row with `column_name = hora_entrevista`, `data_type = text`, `column_default = ''`.

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "feat: add hora_entrevista column to interviews (Supabase migration applied)"
```

---

## Task 2: Backend — pure helpers + index() + interview routes

**Files:**
- Modify: `app.py`
- Create: `tests/test_home_features.py`

### 2a — Write failing tests

- [ ] **Step 1: Create `tests/test_home_features.py`**

```python
import pytest
from app import compute_proxima_entrevista, ETAPA_ORDER, sort_key_latest_interview


class TestComputeProximaEntrevista:
    def test_no_interviews_returns_esperando(self):
        app = {'interviews': []}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Esperando'

    def test_all_past_interviews_returns_esperando(self):
        app = {'interviews': [{'fecha_entrevista': '2026-05-01'}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Esperando'

    def test_future_interview_returns_coordinada(self):
        app = {'interviews': [{'fecha_entrevista': '2026-07-01'}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Coordinada'

    def test_today_counts_as_future(self):
        app = {'interviews': [{'fecha_entrevista': '2026-06-01'}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Coordinada'

    def test_undated_interview_no_key_returns_a_coordinar(self):
        app = {'interviews': [{}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'A coordinar'

    def test_undated_interview_empty_string_returns_a_coordinar(self):
        app = {'interviews': [{'fecha_entrevista': ''}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'A coordinar'

    def test_future_beats_undated(self):
        """If there is a future AND an undated interview, Coordinada wins."""
        app = {'interviews': [
            {'fecha_entrevista': '2026-07-01'},
            {'fecha_entrevista': ''},
        ]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Coordinada'


class TestEtapaOrder:
    def test_oferta_beats_aplicado(self):
        assert ETAPA_ORDER['Oferta'] < ETAPA_ORDER['Aplicado']

    def test_rechazado_after_aplicado(self):
        assert ETAPA_ORDER['Rechazado'] > ETAPA_ORDER['Aplicado']

    def test_descartado_is_last(self):
        assert ETAPA_ORDER['Descartado'] == max(ETAPA_ORDER.values())

    def test_oferta_is_first(self):
        assert ETAPA_ORDER['Oferta'] == min(ETAPA_ORDER.values())

    def test_stage_sort_order(self):
        """Two-pass stable sort puts advanced stages first."""
        apps = [
            {'etapa': 'Aplicado', 'interviews': []},
            {'etapa': 'Oferta', 'interviews': []},
            {'etapa': 'Final', 'interviews': []},
            {'etapa': 'Rechazado', 'interviews': []},
        ]
        apps.sort(key=sort_key_latest_interview, reverse=True)
        apps.sort(key=lambda a: ETAPA_ORDER.get(a.get('etapa', ''), 99))
        assert [a['etapa'] for a in apps] == ['Oferta', 'Final', 'Aplicado', 'Rechazado']
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source venv/bin/activate && pytest tests/test_home_features.py -v 2>&1 | head -30
```

Expected: `ImportError` or `AttributeError` — `compute_proxima_entrevista` and `ETAPA_ORDER` don't exist yet.

### 2b — Add ETAPA_ORDER constant

- [ ] **Step 3: Add `ETAPA_ORDER` to `app.py` after the `BENEFICIOS_LABELS` block (after line 52)**

Add this block immediately after the closing `}` of `BENEFICIOS_LABELS`:

```python
ETAPA_ORDER = {
    'Oferta': 0,
    'Final': 1,
    'Técnica': 2,
    'Pantalla HR': 3,
    'Aplicado': 4,
    'Rechazado': 5,
    'Descartado': 6,
}
```

### 2c — Add compute_proxima_entrevista helper

- [ ] **Step 4: Add `compute_proxima_entrevista` to `app.py` after `sort_key_latest_interview` (after line 167)**

Add this function immediately after `sort_key_latest_interview`:

```python
def compute_proxima_entrevista(application, today_str):
    """Return 'Coordinada', 'A coordinar', or 'Esperando' for an application.

    today_str: ISO date string 'YYYY-MM-DD' for comparison (injected for testability).
    Rules:
      - 'Coordinada'  → at least one interview with fecha >= today
      - 'A coordinar' → at least one interview without a date
      - 'Esperando'   → no interviews, or all interviews have past dates
    """
    interviews = application.get('interviews', [])
    has_undated = any(not iv.get('fecha_entrevista') for iv in interviews)
    has_future = any(
        iv.get('fecha_entrevista', '') >= today_str
        for iv in interviews
        if iv.get('fecha_entrevista')
    )
    if has_future:
        return 'Coordinada'
    if has_undated:
        return 'A coordinar'
    return 'Esperando'
```

### 2d — Run tests (should pass now)

- [ ] **Step 5: Run tests — verify they pass**

```bash
source venv/bin/activate && pytest tests/test_home_features.py -v
```

Expected: all 12 tests PASS.

### 2e — Update index()

- [ ] **Step 6: Replace the entire `index()` route in `app.py`**

Find and replace the block starting with `@app.route('/')` through the closing `return render_template(...)` call. Replace with:

```python
@app.route('/')
def index():
    applications = load_applications()
    today_str = datetime.today().strftime('%Y-%m-%d')

    # Attach computed status to every application
    for a in applications:
        a['proxima_entrevista'] = compute_proxima_entrevista(a, today_str)

    # Build upcoming interviews panel from ALL applications (before filtering)
    upcoming_interviews = []
    for a in applications:
        for iv in a.get('interviews', []):
            fecha = iv.get('fecha_entrevista', '')
            if fecha and fecha >= today_str:
                upcoming_interviews.append({
                    'empresa': a['empresa'],
                    'puesto': a['puesto'],
                    'app_id': a['id'],
                    'fecha': fecha,
                    'hora': iv.get('hora_entrevista', ''),
                    'entrevistador': iv.get('entrevistador_nombre', ''),
                })
    upcoming_interviews.sort(key=lambda x: (x['fecha'], x['hora'] or '99:99'))

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

    # Two-pass stable sort: recency descending, then stage ascending
    filtered.sort(key=sort_key_latest_interview, reverse=True)
    filtered.sort(key=lambda a: ETAPA_ORDER.get(a.get('etapa', ''), 99))

    return render_template(
        'index.html',
        applications=filtered,
        total=len(applications),
        etapas=ALLOWED_ETAPAS,
        f_etapa=f_etapa,
        f_empresa=f_empresa,
        f_desde=f_desde,
        f_hasta=f_hasta,
        upcoming_interviews=upcoming_interviews,
    )
```

### 2f — Update interview routes to include hora_entrevista

- [ ] **Step 7: Update `create_interview` — add `hora_entrevista` to the interview dict**

In `create_interview`, the dict currently has `'notas': request.form.get('notas', '').strip()` as the last field. Add `hora_entrevista` before `notas`:

```python
    interview = {
        'id': new_id,
        'application_id': app_id,
        'created_at': now_str(),
        'updated_at': now_str(),
        'fecha_entrevista': request.form.get('fecha_entrevista', '').strip() or None,
        'hora_entrevista': request.form.get('hora_entrevista', '').strip(),
        'entrevistador_nombre': request.form.get('entrevistador_nombre', '').strip(),
        'entrevistador_email': request.form.get('entrevistador_email', '').strip(),
        'entrevistador_linkedin': request.form.get('entrevistador_linkedin', '').strip(),
        'notas': request.form.get('notas', '').strip(),
    }
```

- [ ] **Step 8: Update `update_interview` — add `hora_entrevista` to the update dict**

In `update_interview`, the `.update({...})` call currently has `'fecha_entrevista': ...` as the first field. Add `hora_entrevista` after it:

```python
    supabase_client.table('interviews').update({
        'fecha_entrevista': request.form.get('fecha_entrevista', '').strip() or None,
        'hora_entrevista': request.form.get('hora_entrevista', '').strip(),
        'entrevistador_nombre': request.form.get('entrevistador_nombre', '').strip(),
        'entrevistador_email': request.form.get('entrevistador_email', '').strip(),
        'entrevistador_linkedin': request.form.get('entrevistador_linkedin', '').strip(),
        'notas': request.form.get('notas', '').strip(),
        'updated_at': now_str(),
    }).eq('id', interview_id).execute()
```

- [ ] **Step 9: Verify import starts cleanly**

```bash
source venv/bin/activate && python -c "from app import app, compute_proxima_entrevista, ETAPA_ORDER; print('OK')"
```

Expected: `OK`

- [ ] **Step 10: Run all tests**

```bash
source venv/bin/activate && pytest tests/test_home_features.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 11: Commit**

```bash
git add app.py tests/test_home_features.py
git commit -m "feat: add ETAPA_ORDER, compute_proxima_entrevista, hora_entrevista to interview routes, stage sort"
```

---

## Task 3: Templates

**Files:**
- Modify: `templates/interview_form.html`
- Modify: `templates/_interview_card.html`
- Modify: `templates/index.html`

### 3a — Interview form: date + time

- [ ] **Step 1: Update `templates/interview_form.html` — split the date field into date + time**

Find this block (currently `col-md-6`):
```html
          <div class="col-md-6">
              <label for="fecha_entrevista" class="form-label">Fecha <span class="text-muted small">(opcional)</span></label>
              <input type="date" class="form-control" id="fecha_entrevista" name="fecha_entrevista"
                     value="{{ interview.fecha_entrevista if interview and interview.fecha_entrevista else '' }}">
            </div>
```

Replace with two `col-md-3` inputs side by side:
```html
            <div class="col-md-3">
              <label for="fecha_entrevista" class="form-label">Fecha <span class="text-muted small">(opcional)</span></label>
              <input type="date" class="form-control" id="fecha_entrevista" name="fecha_entrevista"
                     value="{{ interview.fecha_entrevista if interview and interview.fecha_entrevista else '' }}">
            </div>
            <div class="col-md-3">
              <label for="hora_entrevista" class="form-label">Hora <span class="text-muted small">(opcional)</span></label>
              <input type="time" class="form-control" id="hora_entrevista" name="hora_entrevista"
                     value="{{ interview.hora_entrevista if interview and interview.hora_entrevista else '' }}">
            </div>
```

### 3b — Interview card: show time alongside date

- [ ] **Step 2: Update `templates/_interview_card.html` — show hora next to fecha in the header**

Find this span in the card header:
```html
        <span class="fw-semibold">
          <i class="fas fa-calendar-alt text-primary me-1"></i>
          Entrevista {% if iv.fecha_entrevista %}del <span class="fw-bold">{{ iv.fecha_entrevista }}</span>{% else %}<span class="text-muted fw-normal">(sin fecha)</span>{% endif %}
        </span>
```

Replace with:
```html
        <span class="fw-semibold">
          <i class="fas fa-calendar-alt text-primary me-1"></i>
          Entrevista {% if iv.fecha_entrevista %}del <span class="fw-bold">{{ iv.fecha_entrevista }}{% if iv.hora_entrevista %} {{ iv.hora_entrevista }}{% endif %}</span>{% else %}<span class="text-muted fw-normal">(sin fecha)</span>{% endif %}
        </span>
```

### 3c — index.html: upcoming panel

- [ ] **Step 3: Add the upcoming interviews panel to `templates/index.html` — immediately before the `{# --- Filter card --- #}` block**

```html
{# --- Upcoming interviews panel --- #}
{% if upcoming_interviews %}
<div class="card shadow-sm mb-4">
  <div class="card-header py-2 bg-white">
    <h6 class="mb-0"><i class="fas fa-calendar-check me-2 text-primary"></i>Próximas entrevistas</h6>
  </div>
  <div class="card-body p-0">
    <table class="table table-sm table-hover mb-0 align-middle">
      <tbody>
        {% for iv in upcoming_interviews %}
        <tr>
          <td class="ps-3">
            <a href="{{ url_for('application_detail', app_id=iv.app_id) }}"
               class="fw-semibold text-decoration-none text-dark">{{ iv.empresa }}</a>
            <br><small class="text-muted">{{ iv.puesto }}</small>
          </td>
          <td class="text-nowrap">
            <i class="fas fa-calendar-alt text-primary me-1"></i>
            {{ iv.fecha }}{% if iv.hora %} {{ iv.hora }}{% endif %}
          </td>
          <td class="text-muted small">
            {% if iv.entrevistador %}<i class="fas fa-user me-1"></i>{{ iv.entrevistador }}{% else %}—{% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
```

### 3d — index.html: Próxima entrevista column in desktop table

- [ ] **Step 4: Add "Próxima entrevista" column header to the desktop table `<thead>` in `templates/index.html`**

Find the `<thead>` row:
```html
            <tr>
              <th>Empresa / Puesto</th>
              <th>Etapa</th>
              <th>Rating</th>
              <th>Modalidad</th>
              <th>Salario</th>
              <th class="text-center" title="Cantidad de entrevistas">
                <i class="fas fa-comments"></i>
              </th>
              <th class="text-end">Acciones</th>
            </tr>
```

Replace with (new column after Etapa):
```html
            <tr>
              <th>Empresa / Puesto</th>
              <th>Etapa</th>
              <th>Próxima entrevista</th>
              <th>Rating</th>
              <th>Modalidad</th>
              <th>Salario</th>
              <th class="text-center" title="Cantidad de entrevistas">
                <i class="fas fa-comments"></i>
              </th>
              <th class="text-end">Acciones</th>
            </tr>
```

- [ ] **Step 5: Add "Próxima entrevista" cell to each desktop table row**

Find the existing `<td>` block for Etapa in the `{% for app in applications %}` loop:
```html
              <td>
                <span class="badge badge-etapa bg-{{ badge_colors.get(app.etapa, 'secondary') }}">
                  {{ app.etapa }}
                </span>
              </td>
```

After it, add the new cell:
```html
              <td>
                {% set proxima = app.proxima_entrevista %}
                {% if proxima == 'Coordinada' %}
                  <span class="badge bg-success">Coordinada</span>
                {% elif proxima == 'A coordinar' %}
                  <span class="badge bg-warning text-dark">A coordinar</span>
                {% else %}
                  <span class="badge bg-secondary">Esperando</span>
                {% endif %}
              </td>
```

- [ ] **Step 6: Add "Próxima entrevista" badge to mobile cards**

In the mobile cards section, find the `<div class="d-flex flex-wrap gap-2 mt-2 small text-muted">` block and add a badge after the stage badge. Find the section that shows the stage badge in the mobile card:

```html
          <span class="badge badge-etapa bg-{{ badge_colors.get(app.etapa, 'secondary') }} ms-2 flex-shrink-0">
            {{ app.etapa }}
          </span>
```

Below that `</div>` that closes `d-flex justify-content-between`, add:
```html
        <div class="mt-1">
          {% set proxima = app.proxima_entrevista %}
          {% if proxima == 'Coordinada' %}
            <span class="badge bg-success">Coordinada</span>
          {% elif proxima == 'A coordinar' %}
            <span class="badge bg-warning text-dark">A coordinar</span>
          {% else %}
            <span class="badge bg-secondary">Esperando</span>
          {% endif %}
        </div>
```

- [ ] **Step 7: Smoke test — start server locally and verify home loads**

```bash
source venv/bin/activate && \
  SUPABASE_URL=https://ynquzbhxfqobrlyzwkbv.supabase.co \
  SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlucXV6Ymh4ZnFvYnJseXp3a2J2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyOTY0ODAsImV4cCI6MjA5NDg3MjQ4MH0.VvShv5EK2dMt-WsAIzhJ_w21UJC3yIcYYG0X2InXW5o \
  FLASK_SECRET_KEY=9e476439ba68c13207dfd55ac780c4e859088d5e519f667d37cc6b261d9d3339 \
  python app.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:5002/
```

Expected: `200`

Stop the server:
```bash
pkill -f "python app.py"
```

- [ ] **Step 8: Commit**

```bash
git add templates/interview_form.html templates/_interview_card.html templates/index.html
git commit -m "feat: interview time field, proxima entrevista column, upcoming panel, stage sort on home"
```

---

## Task 4: Deploy

- [ ] **Step 1: Push to GitHub**

```bash
git push
```

- [ ] **Step 2: Deploy to Vercel**

```bash
vercel --prod --yes --scope pablorug-2599s-projects
```

Expected: `Production: https://hrtracker-one.vercel.app` — `READY`

- [ ] **Step 3: Verify production**

```bash
curl -s -o /dev/null -w "%{http_code}" https://hrtracker-one.vercel.app/
```

Expected: `200`

Open https://hrtracker-one.vercel.app in the browser and verify:
- Home loads with stage-ordered applications
- Próxima entrevista column shows correct badge
- Create a new interview with date + time → verify time appears in the card
- Any upcoming (future-dated) interview appears in the "Próximas entrevistas" panel
