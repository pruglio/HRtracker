# Design: Beneficios + Deploy en Railway

**Date:** 2026-05-20
**Project:** HRtracker
**Status:** Approved

---

## Summary

Two focused additions to HRtracker:
1. A "benefits" field on job applications (checkboxes + free text)
2. Production deployment on Railway with a persistent volume

---

## 1. Benefits Field

### Data model

Two new fields added to the `application` object in `applications.json`:

```json
"beneficios": ["obra_social", "bono_anual"],
"beneficios_otros": "4 semanas de vacaciones"
```

- `beneficios`: list of string keys from the predefined set (may be empty list)
- `beneficios_otros`: free-text string for anything not covered by checkboxes (may be empty string)

Both fields are optional. Existing applications without these fields are treated as having no benefits recorded.

### Predefined checkbox options

| Key | Label |
|-----|-------|
| `obra_social` | Obra social / prepaga |
| `bono_anual` | Bono anual |
| `stock_options` | Stock options / equity |
| `home_office` | Home office |
| `horario_flexible` | Horario flexible |
| `vacaciones_extra` | Vacaciones extra (+15 días) |
| `vehiculo` | Vehículo / transporte |
| `comidas` | Comidas / viáticos |

### Backend changes (`app.py`)

- `create_application` and `update_application` read `request.form.getlist('beneficios')` (multi-value) and `request.form.get('beneficios_otros', '')`.
- Input is validated: only keys present in the predefined set are accepted; unknown keys are dropped.
- `ALLOWED_BENEFICIOS` constant added (set of valid keys).

### Frontend changes

**`application_form.html`** — new "Beneficios" section below Notas:
- 8 checkboxes in a 2-column grid, pre-checked when editing an existing application
- Textarea "Otros beneficios" below the checkboxes, pre-filled on edit

**`application_detail.html`** — new benefits display block between the info grid and the notes card:
- Rendered as Bootstrap badges (outline style)
- "Otros beneficios" shown as plain text below badges if non-empty
- Entire block hidden when both `beneficios` is empty and `beneficios_otros` is blank

---

## 2. Railway Deploy

### Infrastructure

- **Platform:** Railway (https://railway.app)
- **Runtime:** Python 3.11.9 (`runtime.txt` already present)
- **Process:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` (`Procfile` already present)
- **Persistent storage:** Railway volume mounted at `/data`

### Environment variables

| Variable | Value |
|----------|-------|
| `DATA_DIR` | `/data` |
| `FLASK_SECRET_KEY` | Generated secure random string |
| `PORT` | Set automatically by Railway |

### Deploy steps

1. Push repo to GitHub (if not already)
2. Create new Railway project → "Deploy from GitHub repo"
3. Add a Volume service, mount path `/data`
4. Set `DATA_DIR=/data` and `FLASK_SECRET_KEY` in Railway environment variables
5. Railway auto-detects `Procfile` and triggers deploy
6. Verify app boots and data persists across redeploys

No code changes required for the deploy — the app already reads `DATA_DIR` and `PORT` from the environment.

---

## Out of scope

- Database migration (app stays on flat-file JSON)
- Authentication / multi-user support
- Any other new fields beyond benefits
