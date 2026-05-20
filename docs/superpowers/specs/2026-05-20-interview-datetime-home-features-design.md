# Design: Interview Datetime + Home Features

**Date:** 2026-05-20
**Project:** HRtracker
**Status:** Approved

---

## Summary

Four improvements to HRtracker:
1. Add optional time field to interviews (alongside existing date)
2. Add computed "Próxima entrevista" column to the applications list
3. Add "Próximas entrevistas" panel at the top of home
4. Sort applications by stage (most advanced first)

No changes to deployment or data architecture — Supabase + Vercel stay as-is.

---

## Architecture

All logic is Python/Jinja2. No new routes needed. Changes touch:
- Supabase schema: one new column (`hora_entrevista`)
- `app.py`: two new helper functions, updated insert/update dicts, updated sort
- `templates/index.html`: new panel + new column + new sort
- `templates/interview_form.html`: new time input
- `templates/_interview_card.html`: show time alongside date

---

## Feature 1: Interview Time Field

### DB

Add nullable column to `interviews`:
```sql
ALTER TABLE interviews ADD COLUMN hora_entrevista TEXT DEFAULT '';
```

Format: `HH:MM` (24h). Empty string when not set.

### Form (`interview_form.html`)

The existing date input (`col-md-6`) splits into two `col-md-3` inputs side by side:

```html
<div class="col-md-3">
  <label>Fecha <span class="text-muted small">(opcional)</span></label>
  <input type="date" name="fecha_entrevista" value="...">
</div>
<div class="col-md-3">
  <label>Hora <span class="text-muted small">(opcional)</span></label>
  <input type="time" name="hora_entrevista" value="...">
</div>
```

### app.py

`create_interview` and `update_interview` both include:
```python
'hora_entrevista': request.form.get('hora_entrevista', '').strip(),
```

### Card display (`_interview_card.html`)

Show time next to date when present:
```
Fecha: 2026-06-10 14:30   (when both set)
Fecha: 2026-06-10         (date only)
Sin fecha                 (neither set)
```

---

## Feature 2: Computed "Próxima entrevista" Status

Calculated in Python after loading applications. Added as a key `proxima_entrevista` on each application dict.

### Logic

```python
from datetime import date

def compute_proxima_entrevista(application):
    today = date.today().isoformat()
    interviews = application.get('interviews', [])
    has_undated = any(not iv.get('fecha_entrevista') for iv in interviews)
    has_future = any(
        iv.get('fecha_entrevista', '') >= today
        for iv in interviews
        if iv.get('fecha_entrevista')
    )
    if has_future:
        return 'Coordinada'
    if has_undated:
        return 'A coordinar'
    return 'Esperando'
```

Called once per application inside `index()` after loading, before filtering.

### Display

Desktop table: new column "Próxima entrevista" with colored badge:
- `Coordinada` → `badge bg-success`
- `A coordinar` → `badge bg-warning text-dark`
- `Esperando` → `badge bg-secondary`

Mobile card: small badge below the stage badge.

---

## Feature 3: "Próximas entrevistas" Panel

Shown at the top of home, **above** the filters. Hidden entirely if no future interviews exist.

### Data

Built in `index()` from already-loaded applications (no extra DB query):

```python
today = date.today().isoformat()
upcoming = []
for app in all_applications:
    for iv in app.get('interviews', []):
        fecha = iv.get('fecha_entrevista', '')
        if fecha and fecha >= today:
            upcoming.append({
                'empresa': app['empresa'],
                'puesto': app['puesto'],
                'app_id': app['id'],
                'fecha': fecha,
                'hora': iv.get('hora_entrevista', ''),
                'entrevistador': iv.get('entrevistador_nombre', ''),
            })
upcoming.sort(key=lambda x: (x['fecha'], x['hora'] or '99:99'))
```

Passed to template as `upcoming_interviews`.

### Template

```html
{% if upcoming_interviews %}
<div class="card shadow-sm mb-4">
  <div class="card-header py-2">
    <h6 class="mb-0"><i class="fas fa-calendar-alt me-2 text-primary"></i>Próximas entrevistas</h6>
  </div>
  <div class="card-body p-0">
    <table class="table table-sm mb-0">
      <tbody>
        {% for iv in upcoming_interviews %}
        <tr>
          <td><a href="{{ url_for('application_detail', app_id=iv.app_id) }}">{{ iv.empresa }}</a><br><small class="text-muted">{{ iv.puesto }}</small></td>
          <td>{{ iv.fecha }}{% if iv.hora %} {{ iv.hora }}{% endif %}</td>
          <td class="text-muted small">{{ iv.entrevistador or '—' }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
```

---

## Feature 4: Sort Applications by Stage

Stage priority order (index 0 = highest priority):

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

Defined as a module-level constant in `app.py`.

Sort in `index()`, replacing the current `sort_key_latest_interview` single-key sort:

```python
filtered.sort(
    key=lambda a: (
        ETAPA_ORDER.get(a.get('etapa', ''), 99),
        # within same stage: most recent interview first (inverted)
        sort_key_latest_interview(a),
    )
)
```

Since `sort_key_latest_interview` returns a string and we want descending order for it within each stage group, we negate it by inverting: sort ascending on a tuple `(etapa_order, -latest_interview_timestamp)`. Because timestamps are strings, invert using a wrapper that negates lexicographic order — simplest approach is a two-pass sort or using a `key` that wraps the string comparison.

Practical implementation: sort by `(etapa_order, latest_interview_desc)` where `latest_interview_desc` is computed as a string that sorts in reverse — prepend a constant and reverse it, or simply sort stable in two passes:

```python
# Two-pass stable sort (simpler and correct)
filtered.sort(key=sort_key_latest_interview, reverse=True)       # pass 1: by recency desc
filtered.sort(key=lambda a: ETAPA_ORDER.get(a.get('etapa', ''), 99))  # pass 2: by stage asc
```

Python's sort is stable so pass 2 preserves the recency order within each stage group.

---

## Files Changed

| File | Change |
|------|--------|
| Supabase migration | Add `hora_entrevista TEXT DEFAULT ''` to `interviews` |
| `app.py` | Add `ETAPA_ORDER`, `compute_proxima_entrevista()`, update `index()`, update `create_interview`/`update_interview` |
| `templates/index.html` | Add upcoming panel, add proxima column, update sort |
| `templates/interview_form.html` | Split date field → date + time |
| `templates/_interview_card.html` | Show time next to date |

---

## Out of Scope

- Filtering by próxima entrevista status
- Notifications / reminders for upcoming interviews
- Timezone handling (all times stored and displayed as local)
