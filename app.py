import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo('America/Montevideo')

import asyncio
import io
import random as _random
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'hrtracker-secret-key-2026')

FONTS_DIR = os.path.join(app.root_path, 'static', 'fonts')
FONT_REGULAR = os.path.join(FONTS_DIR, 'Outfit-Regular.ttf')
FONT_MEDIUM = os.path.join(FONTS_DIR, 'Outfit-Medium.ttf')
FONT_BOLD = os.path.join(FONTS_DIR, 'Outfit-Bold.ttf')
FONT_SCRIPT = os.path.join(FONTS_DIR, 'Pacifico-Regular.ttf')

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# Convenience alias used throughout the module
supabase_client = type('_Proxy', (), {
    '__getattr__': staticmethod(lambda name: getattr(get_supabase(), name))
})()

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

ETAPA_ORDER = {
    'Oferta': 0,
    'Final': 1,
    'Técnica': 2,
    'Pantalla HR': 3,
    'Aplicado': 4,
    'Rechazado': 5,
    'Descartado': 6,
}

DIAS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


# --- Helpers ---

def make_id(existing_ids):
    while True:
        new_id = uuid.uuid4().hex[:8]
        if new_id not in existing_ids:
            return new_id


def now_local() -> datetime:
    """Current datetime in America/Montevideo (naive, for comparison with stored local times)."""
    return datetime.now(APP_TZ).replace(tzinfo=None)


def now_str():
    return now_local().strftime('%Y-%m-%d %H:%M:%S')


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


def is_future_interview(iv, now):
    """Return True if the interview is in the future relative to `now` (a datetime object).

    Rules:
      - No fecha_entrevista → False
      - fecha AND hora both set → parse as full datetime 'YYYY-MM-DD HH:MM', return dt > now
        (if hora is malformed, fall back to date-only comparison)
      - fecha only (no hora, or empty hora) → return fecha >= now.date().isoformat()
    """
    fecha = iv.get('fecha_entrevista')
    if not fecha:
        return False
    hora = iv.get('hora_entrevista', '') or ''
    if hora:
        try:
            interview_dt = datetime.strptime(f'{fecha} {hora}', '%Y-%m-%d %H:%M')
            return interview_dt > now
        except ValueError:
            pass
    return fecha >= now.date().isoformat()


def compute_proxima_entrevista(application, now):
    """Return a dict with status and next interview info for an application.

    now: datetime object for comparison (injected for testability).
    Rules:
      - 'Coordinada'  → at least one interview that is_future_interview
      - 'A coordinar' → at least one interview without a date
      - 'Esperando'   → no interviews, or all interviews are in the past

    Returns:
        {
            'status': 'Coordinada' | 'A coordinar' | 'Esperando',
            'next_fecha': str,  # set when status == 'Coordinada', else ''
            'next_hora': str,   # set when status == 'Coordinada' and hora present, else ''
        }
    """
    interviews = application.get('interviews', [])
    has_undated = any(not iv.get('fecha_entrevista') for iv in interviews)
    future_ivs = [iv for iv in interviews if is_future_interview(iv, now)]
    if future_ivs:
        next_iv = min(future_ivs, key=lambda iv: (iv.get('fecha_entrevista', ''), iv.get('hora_entrevista', '') or '99:99'))
        return {
            'status': 'Coordinada',
            'next_fecha': next_iv.get('fecha_entrevista', ''),
            'next_hora': next_iv.get('hora_entrevista', '') or '',
        }
    if has_undated:
        return {'status': 'A coordinar', 'next_fecha': '', 'next_hora': ''}
    return {'status': 'Esperando', 'next_fecha': '', 'next_hora': ''}


def format_proxima_fecha(fecha, hora=''):
    """Format fecha as 'Martes 10/05/2026' (+ hora if set)."""
    if not fecha:
        return ''
    try:
        dt = datetime.strptime(fecha, '%Y-%m-%d')
        dia = DIAS_ES[dt.weekday()]
        formatted = f"{dia} {dt.strftime('%d/%m/%Y')}"
        if hora:
            formatted += f" {hora}"
        return formatted
    except ValueError:
        return fecha


def get_staleness_days(app_entry, today):
    """Return days since last activity on this application."""
    best = None
    for key in ('updated_at', 'created_at'):
        s = app_entry.get(key)
        if not s:
            continue
        try:
            d = datetime.strptime(s[:10], '%Y-%m-%d').date()
            if best is None or d > best:
                best = d
        except (ValueError, TypeError):
            continue
    if best is None:
        return 0
    return (today - best).days


def compute_activity_stats(applications):
    """Return dict with total_apps, total_interviews, response_rate."""
    total_apps = len(applications)
    total_interviews = sum(len(a.get('interviews', [])) for a in applications)
    if total_apps == 0:
        response_rate = 0
    else:
        apps_with_interviews = sum(1 for a in applications if a.get('interviews'))
        response_rate = int(apps_with_interviews * 100 / total_apps)
    return {
        'total_apps': total_apps,
        'total_interviews': total_interviews,
        'response_rate': response_rate,
    }


def compute_heatmap(applications, today, weeks=12):
    """Return a 12×7 nested list of activity counts (week × day, Mon=0)."""
    days = weeks * 7  # 84
    start_date = today - timedelta(days=days - 1)

    counts = {}
    for i in range(days):
        d = start_date + timedelta(days=i)
        counts[d.isoformat()] = 0

    for a in applications:
        # App created
        created = a.get('created_at')
        if created:
            try:
                d_str = created[:10]
                if d_str in counts:
                    counts[d_str] += 1
            except (TypeError, ValueError):
                pass

        # Interviews: count the actual interview date (fecha_entrevista),
        # not when the record was entered — this shows real activity over time
        for iv in a.get('interviews', []):
            fecha = iv.get('fecha_entrevista')
            if fecha:
                try:
                    d_str = fecha[:10]
                    if d_str in counts:
                        counts[d_str] += 1
                except (TypeError, ValueError):
                    pass

    # Reshape into 12×7
    result = []
    for w in range(weeks):
        week_row = []
        for d in range(7):
            day_offset = w * 7 + d
            day_date = start_date + timedelta(days=day_offset)
            week_row.append(counts.get(day_date.isoformat(), 0))
        result.append(week_row)
    return result


PIPELINE_STAGES = ['Aplicado', 'Pantalla HR', 'Técnica', 'Final', 'Oferta']


def compute_report_data(applications, now_dt):
    """Compute all data needed for the /report page."""
    from collections import defaultdict

    today = now_dt.date()
    fourteen_days = today + timedelta(days=14)
    INACTIVE = {'Rechazado', 'Descartado'}

    # Basic counts
    total_apps = len(applications)
    active_apps = sum(1 for a in applications if a.get('etapa') not in INACTIVE)
    total_interviews = sum(len(a.get('interviews', [])) for a in applications)
    if total_apps == 0:
        response_rate = 0
    else:
        apps_with_interviews = sum(1 for a in applications if a.get('interviews'))
        response_rate = int(apps_with_interviews * 100 / total_apps)

    # Funnel
    stage_counts = {}
    for a in applications:
        e = a.get('etapa', '')
        stage_counts[e] = stage_counts.get(e, 0) + 1

    first_count = stage_counts.get('Aplicado', 0) or 1
    funnel = []
    for stage in PIPELINE_STAGES:
        count = stage_counts.get(stage, 0)
        pct = round(count / first_count * 100) if first_count > 0 else 0
        funnel.append({'etapa': stage, 'count': count, 'pct': pct})

    # Upcoming interviews (next 14 days), sorted by date ASC
    upcoming_with_key = []
    for a in applications:
        for iv in a.get('interviews', []):
            fecha_str = iv.get('fecha_entrevista', '')
            if not fecha_str:
                continue
            try:
                iv_date = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except Exception:
                continue
            if today <= iv_date <= fourteen_days:
                upcoming_with_key.append((fecha_str, {
                    'empresa': a['empresa'],
                    'puesto': a['puesto'],
                    'app_id': a['id'],
                    'fecha_fmt': format_proxima_fecha(fecha_str),
                    'hora': iv.get('hora_entrevista', ''),
                    'entrevistador': iv.get('entrevistador_nombre', ''),
                    'etapa': a.get('etapa', ''),
                }))
    upcoming_with_key.sort(key=lambda x: x[0])
    upcoming = [x[1] for x in upcoming_with_key]

    # By stage (active apps grouped)
    stage_buckets = defaultdict(list)
    for a in applications:
        if a.get('etapa') not in INACTIVE:
            stage_buckets[a.get('etapa', 'Sin etapa')].append(a)

    by_stage = []
    for stage in PIPELINE_STAGES:
        if stage in stage_buckets:
            by_stage.append({'etapa': stage, 'apps': stage_buckets[stage]})
    for stage, apps in stage_buckets.items():
        if stage not in PIPELINE_STAGES:
            by_stage.append({'etapa': stage, 'apps': apps})

    # High-value apps: Final + Oferta
    high_value = [a for a in applications if a.get('etapa') in ('Final', 'Oferta')]

    return {
        'generated_at': now_dt.strftime('%d/%m/%Y %H:%M'),
        'total_apps': total_apps,
        'active_apps': active_apps,
        'response_rate': response_rate,
        'total_interviews': total_interviews,
        'funnel': funnel,
        'upcoming': upcoming,
        'upcoming_count': len(upcoming),
        'by_stage': by_stage,
        'high_value': high_value,
        'high_value_count': len(high_value),
    }


# --- Routes: Applications ---

@app.route('/')
def index():
    applications = load_applications()
    now_dt = now_local()

    # Attach computed status to every application
    for a in applications:
        proxima = compute_proxima_entrevista(a, now_dt)
        a['proxima_entrevista'] = proxima['status']
        a['proxima_entrevista_label'] = format_proxima_fecha(proxima['next_fecha'], proxima['next_hora']) if proxima['status'] == 'Coordinada' else ''

    # Build upcoming interviews panel from ALL applications (before filtering)
    upcoming_interviews = []
    for a in applications:
        for iv in a.get('interviews', []):
            if is_future_interview(iv, now_dt):
                upcoming_interviews.append({
                    'empresa': a['empresa'],
                    'puesto': a['puesto'],
                    'app_id': a['id'],
                    'fecha': iv.get('fecha_entrevista', ''),
                    'hora': iv.get('hora_entrevista', ''),
                    'entrevistador': iv.get('entrevistador_nombre', ''),
                })
    upcoming_interviews.sort(key=lambda x: (x['fecha'], x['hora'] or '99:99'))

    today = now_dt.date()

    # Urgent interview: first upcoming interview that is today or tomorrow
    urgent_iv = None
    tomorrow = today + timedelta(days=1)
    for iv_entry in upcoming_interviews:
        iv_date_str = iv_entry['fecha']
        try:
            iv_date = datetime.strptime(iv_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            continue
        if iv_date <= tomorrow:
            urgent_iv = iv_entry
            break

    # Group active applications (before filters, always show all active)
    INACTIVE_ETAPAS = {'Rechazado', 'Descartado'}
    active_apps = [a for a in applications if a.get('etapa') not in INACTIVE_ETAPAS]

    needs_attention = []
    this_week = []
    al_dia = []

    for a in active_apps:
        staleness = get_staleness_days(a, today)
        a['staleness_days'] = staleness
        proxima = a.get('proxima_entrevista', '')
        etapa = a.get('etapa', '')

        if proxima == 'Coordinada':
            this_week.append(a)
        elif etapa in ('Aplicado',) and staleness >= 7:
            needs_attention.append(a)
        elif etapa in ('Pantalla HR', 'Técnica', 'Final') and proxima == 'A coordinar':
            needs_attention.append(a)
        else:
            al_dia.append(a)

    # Sidebar: first upcoming interview app
    next_iv_app = None
    if this_week:
        next_iv_app = this_week[0]

    activity_stats = compute_activity_stats(applications)
    heatmap_weeks = compute_heatmap(applications, today)

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
        urgent_iv=urgent_iv,
        needs_attention=needs_attention,
        this_week=this_week,
        al_dia=al_dia,
        next_iv_app=next_iv_app,
        activity_stats=activity_stats,
        heatmap_weeks=heatmap_weeks,
        today_str=today.strftime('%Y-%m-%d'),
    )


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
    # Delete voice files from Storage before DB delete
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


# --- Routes: Interviews ---

@app.route('/interview/new')
def new_interview_global():
    """Global new-interview page: user picks the application from a dropdown."""
    applications = load_applications()
    applications.sort(key=lambda a: a.get('empresa', '').lower())
    return render_template('interview_form.html', application=None, applications=applications, interview=None)


@app.route('/interview', methods=['POST'])
def create_interview_global():
    """Handle interview creation from the global form (app_id comes from the form body)."""
    app_id = request.form.get('app_id', '').strip()
    if not app_id:
        applications = load_applications()
        applications.sort(key=lambda a: a.get('empresa', '').lower())
        flash('Seleccioná una postulación.', 'danger')
        return render_template('interview_form.html', application=None, applications=applications, interview=None)
    return create_interview(app_id)


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
        'hora_entrevista': request.form.get('hora_entrevista', '').strip(),
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
        'hora_entrevista': request.form.get('hora_entrevista', '').strip(),
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


# --- Routes: Voice notes ---

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


@app.route('/api/tts')
def text_to_speech():
    """Convert written interview notes to MP3 using Microsoft Edge Neural TTS.
    Voice: es-UY-MateoNeural — Uruguayan male, no API key required."""
    text = request.args.get('text', '').strip()
    if not text:
        abort(400)
    text = text[:3000]
    try:
        async def _synthesize():
            communicate = edge_tts.Communicate(text, voice='es-UY-MateoNeural', rate='+30%')
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk['type'] == 'audio':
                    buf.write(chunk['data'])
            buf.seek(0)
            return buf

        buf = asyncio.run(_synthesize())
        return send_file(buf, mimetype='audio/mpeg',
                         as_attachment=False,
                         download_name='notas.mp3')
    except Exception:
        abort(503)


def generate_offer_postcard(app_entry):
    """Genera un PNG 1080x1080 celebrando una oferta de trabajo.
    Sin salario. Cierre fijo del País Vasco."""
    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), '#FEF3C7')
    draw = ImageDraw.Draw(img, 'RGBA')

    # Gradiente vertical cálido a frío
    top = (254, 243, 199)
    bot = (219, 234, 254)
    for y in range(H):
        t = y / H
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Confetti decorativo determinístico por app_id
    seed_str = str(app_entry.get('id', ''))
    rng = _random.Random(seed_str)
    confetti_colors = [(245, 158, 11), (239, 68, 68), (16, 185, 129), (59, 130, 246)]
    for _ in range(40):
        x = rng.randint(30, W - 30)
        y = rng.randint(30, H - 30)
        size = rng.randint(8, 16)
        c = rng.choice(confetti_colors) + (int(255 * rng.uniform(0.5, 0.75)),)
        if rng.choice([True, False]):
            draw.ellipse([x, y, x + size, y + size], fill=c)
        else:
            draw.polygon([(x, y + size), (x + size, y + size), (x + size / 2, y)], fill=c)

    # Fuentes
    f_title = ImageFont.truetype(FONT_BOLD, 60)
    f_small = ImageFont.truetype(FONT_REGULAR, 30)
    f_puesto = ImageFont.truetype(FONT_MEDIUM, 40)
    f_modal = ImageFont.truetype(FONT_MEDIUM, 26)
    f_mensaje = ImageFont.truetype(FONT_SCRIPT, 56)
    f_fecha = ImageFont.truetype(FONT_REGULAR, 22)

    def center_text(text, font, y, fill='#0F172A'):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) / 2, y), text, font=font, fill=fill)
        return bbox[3] - bbox[1]

    # Layout centrado vertical: TENGO UNA OFERTA → en → EMPRESA → separador
    center_text('¡TENGO UNA OFERTA!', f_title, 280, fill='#0F172A')

    center_text('en', f_small, 380, fill='#64748B')

    # Empresa grande con reducción de fuente si es larga
    empresa = (app_entry.get('empresa') or '').strip() or '—'
    f_emp = None
    for size in (120, 100, 84, 72, 60):
        f_emp = ImageFont.truetype(FONT_BOLD, size)
        bbox = draw.textbbox((0, 0), empresa, font=f_emp)
        if (bbox[2] - bbox[0]) <= W - 120:
            break
    bbox = draw.textbbox((0, 0), empresa, font=f_emp)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    emp_y = 460
    draw.text(((W - w) / 2, emp_y), empresa, font=f_emp, fill='#2563EB')

    # Separador debajo de la empresa
    sep_y = emp_y + h + 90
    draw.line([(W / 2 - 100, sep_y), (W / 2 + 100, sep_y)], fill='#94A3B8', width=3)

    # Mensaje festivo del País Vasco (script font, rojo cálido)
    mensaje = 'ahora sí al País Vasco en Paz!! jaja'
    bbox = draw.textbbox((0, 0), mensaje, font=f_mensaje)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, H - 280), mensaje, font=f_mensaje, fill='#DC2626')

    # Fecha
    fecha = datetime.now(APP_TZ).strftime('%d / %m / %Y')
    bbox = draw.textbbox((0, 0), fecha, font=f_fecha)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, H - 90), fecha, font=f_fecha, fill='#94A3B8')

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True, compress_level=6)
    buf.seek(0)
    return buf


@app.route('/api/postal/<app_id>')
def offer_postcard(app_id):
    """Devuelve un PNG con la postal celebratoria. Solo si la postulación está en etapa Oferta."""
    app_entry = load_application(app_id)
    if not app_entry:
        abort(404)
    if app_entry.get('etapa') != 'Oferta':
        abort(404)
    try:
        buf = generate_offer_postcard(app_entry)
    except Exception:
        app.logger.exception('Error generando postal de oferta')
        abort(500)
    resp = send_file(buf, mimetype='image/png',
                     as_attachment=False,
                     download_name=f'oferta-{app_id}.png')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/report')
def report():
    applications = load_applications()
    now_dt = now_local()
    today = now_dt.date()

    # Attach proxima_entrevista and staleness to each app
    for a in applications:
        proxima = compute_proxima_entrevista(a, now_dt)
        a['proxima_entrevista'] = proxima['status']
        a['proxima_entrevista_label'] = (
            format_proxima_fecha(proxima['next_fecha'], proxima['next_hora'])
            if proxima['status'] == 'Coordinada' else ''
        )
        a['staleness_days'] = get_staleness_days(a, today)

    # Compute needs_attention (same logic as index())
    INACTIVE_ETAPAS = {'Rechazado', 'Descartado'}
    needs_attention = []
    for a in applications:
        if a.get('etapa') in INACTIVE_ETAPAS:
            continue
        etapa = a.get('etapa', '')
        proxima = a.get('proxima_entrevista', '')
        staleness = a.get('staleness_days', 0)
        if etapa == 'Aplicado' and staleness >= 7:
            needs_attention.append(a)
        elif etapa in ('Pantalla HR', 'Técnica', 'Final') and proxima == 'A coordinar':
            needs_attention.append(a)

    report_data = compute_report_data(applications, now_dt)
    report_data['needs_attention'] = needs_attention

    return render_template('report.html', **report_data)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
