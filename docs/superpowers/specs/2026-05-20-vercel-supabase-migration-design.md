# Design: Vercel + Supabase Migration

**Date:** 2026-05-20
**Project:** HRtracker
**Status:** Approved

---

## Summary

Migrate HRtracker from flat-file JSON storage (Railway) to Supabase (PostgreSQL + Storage) and deploy on Vercel (free tier). No changes to UI or business logic — only the data layer and deployment target change.

---

## Architecture

```
Browser → Vercel (Flask serverless) → Supabase (Postgres + Storage)
```

**Vercel:**
- `vercel.json` routes all requests to `api/index.py`
- `api/index.py` imports and exposes the Flask WSGI app
- Static files and templates served by Flask from project root
- `.vercelignore` excludes `venv/`, `data/`, `tests/`

**Supabase project:** `ynquzbhxfqobrlyzwkbv`
- URL: `https://ynquzbhxfqobrlyzwkbv.supabase.co`
- Auth: anon key (RLS disabled — single-user personal app)

---

## Database Schema

Already migrated to Supabase. Tables:

```sql
applications (id TEXT PK, empresa, puesto, etapa, modalidad,
              salario_min INT, salario_max INT, rating INT,
              notas, beneficios JSONB, beneficios_otros,
              created_at, updated_at)

interviews   (id TEXT PK, application_id TEXT FK→applications CASCADE,
              fecha_entrevista, entrevistador_nombre, email, linkedin,
              notas, created_at, updated_at)

voice_notes  (id SERIAL PK, interview_id TEXT FK→interviews CASCADE,
              filename TEXT, created_at TEXT)
```

RLS disabled on all tables. Indexes on `interviews.application_id` and `voice_notes.interview_id`.

---

## Storage

**Bucket:** `voice-notes` (private, 50MB per file)
- Path convention: `<app_id>/<interview_id>/<filename>`
- Anon RLS policies: SELECT / INSERT / UPDATE / DELETE all permitted
- Serving: Flask `serve_voice` route generates a 1-hour signed URL and redirects

---

## Code Changes

### New files
- `vercel.json` — Vercel build + routing config
- `api/__init__.py` — empty, makes `api/` a package
- `api/index.py` — exposes Flask app as `handler`
- `.vercelignore` — excludes venv, data, tests, docs

### Modified files
- `requirements.txt` — add `supabase==2.10.0`
- `app.py` — replace JSON file I/O with Supabase queries throughout

### Removed patterns
- `DATA_DIR`, `DATA_FILE`, `VOICE_DIR` constants and env vars
- `load_applications()` / `save_applications()` functions replaced by targeted per-route queries
- `shutil.rmtree` cascade deletes replaced by DB CASCADE constraints
- `send_from_directory` for voice replaced by Supabase Storage signed URL redirect

### New patterns in app.py
```python
# Client init
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Read one application with nested interviews + voice_notes
def load_application(app_id): ...

# Read all applications with nested structure (for index + filtering)
def load_applications(): ...

# Each mutating route calls supabase_client.table('...').insert/update/delete directly
```

---

## Environment Variables (Vercel dashboard)

| Variable | Value |
|----------|-------|
| `SUPABASE_URL` | `https://ynquzbhxfqobrlyzwkbv.supabase.co` |
| `SUPABASE_KEY` | anon key (from Supabase dashboard → Settings → API) |
| `FLASK_SECRET_KEY` | `9e476439ba68c13207dfd55ac780c4e859088d5e519f667d37cc6b261d9d3339` |

---

## Out of Scope

- Authentication / multi-user support
- Supabase Realtime
- CDN-cached static files (Flask serves them directly)
- Any UI changes
