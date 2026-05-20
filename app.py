import json
import os
import shutil
import time
import uuid
from datetime import datetime

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'hrtracker-secret-key-2026')

# DATA_DIR is configurable so Railway/Heroku deployments can point to a
# persistent volume (e.g. DATA_DIR=/data). Locally it falls back to ./data.
DATA_DIR = os.environ.get('DATA_DIR', 'data')
DATA_FILE = os.path.join(DATA_DIR, 'applications.json')
VOICE_DIR = os.path.join(DATA_DIR, 'voice_notes')

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


# --- Helpers ---

def load_applications():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_applications(applications):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(applications, f, ensure_ascii=False, indent=2)


def find_application(applications, app_id):
    return next((a for a in applications if a['id'] == app_id), None)


def find_interview(application, interview_id):
    if not application:
        return None
    return next(
        (iv for iv in application.get('interviews', []) if iv['id'] == interview_id),
        None,
    )


def find_app_and_interview(applications, app_id, interview_id):
    app_obj = find_application(applications, app_id)
    if not app_obj:
        return None, None
    return app_obj, find_interview(app_obj, interview_id)


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


def voice_path(app_id, interview_id):
    return os.path.join(
        VOICE_DIR,
        os.path.basename(app_id),
        os.path.basename(interview_id),
    )


def application_has_date_in_range(application, desde_date, hasta_date):
    """Return True if any interview's fecha_entrevista falls in the given range."""
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
    """Sort key: most recent interview fecha, nulls last, then created_at."""
    fechas = [
        iv.get('fecha_entrevista') for iv in application.get('interviews', [])
        if iv.get('fecha_entrevista')
    ]
    return max(fechas) if fechas else (application.get('created_at', '') or '0000')


# --- Routes: Applications ---

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

    applications = load_applications()
    existing_ids = {a['id'] for a in applications}
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
        'beneficios': [b for b in request.form.getlist('beneficios') if b in ALLOWED_BENEFICIOS],
        'beneficios_otros': request.form.get('beneficios_otros', '').strip(),
        'notas': request.form.get('notas', '').strip(),
        'interviews': [],
    }

    applications.append(application)
    save_applications(applications)
    flash('Postulación guardada correctamente.', 'success')
    return redirect(url_for('application_detail', app_id=new_id))


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


@app.route('/application/<app_id>/edit')
def edit_application(app_id):
    applications = load_applications()
    application = find_application(applications, app_id)
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
    applications = load_applications()
    application = find_application(applications, app_id)
    if not application:
        abort(404)

    empresa = request.form.get('empresa', '').strip()
    puesto = request.form.get('puesto', '').strip()

    if not empresa or not puesto:
        flash('Empresa y puesto son obligatorios.', 'danger')
        return redirect(url_for('edit_application', app_id=app_id))

    etapa = request.form.get('etapa', application['etapa'])
    if etapa not in ALLOWED_ETAPAS:
        etapa = application['etapa']

    modalidad = request.form.get('modalidad', '')
    if modalidad not in ALLOWED_MODALIDADES:
        modalidad = ''

    application['empresa'] = empresa
    application['puesto'] = puesto
    application['etapa'] = etapa
    application['modalidad'] = modalidad
    application['salario_min'] = parse_salary(request.form.get('salario_min'))
    application['salario_max'] = parse_salary(request.form.get('salario_max'))
    application['notas'] = request.form.get('notas', '').strip()
    application['beneficios'] = [b for b in request.form.getlist('beneficios') if b in ALLOWED_BENEFICIOS]
    application['beneficios_otros'] = request.form.get('beneficios_otros', '').strip()
    application['updated_at'] = now_str()

    save_applications(applications)
    flash('Postulación actualizada correctamente.', 'success')
    return redirect(url_for('application_detail', app_id=app_id))


@app.route('/application/<app_id>/delete', methods=['POST'])
def delete_application(app_id):
    applications = load_applications()
    application = find_application(applications, app_id)
    if not application:
        abort(404)

    # Cascade-delete all voice notes for this application
    shutil.rmtree(
        os.path.join(VOICE_DIR, os.path.basename(app_id)),
        ignore_errors=True,
    )
    applications = [a for a in applications if a['id'] != app_id]
    save_applications(applications)
    flash('Postulación eliminada.', 'success')
    return redirect(url_for('index'))


@app.route('/application/<app_id>/rating', methods=['POST'])
def update_rating(app_id):
    payload = request.get_json(silent=True) or {}
    rating = parse_rating(payload.get('rating'))

    applications = load_applications()
    application = find_application(applications, app_id)
    if not application:
        return jsonify({'error': 'Postulación no encontrada'}), 404

    application['rating'] = rating
    application['updated_at'] = now_str()
    save_applications(applications)
    return jsonify({'ok': True, 'rating': rating}), 200


# --- Routes: Interviews (nested under Applications) ---

@app.route('/application/<app_id>/interview/new')
def new_interview(app_id):
    applications = load_applications()
    application = find_application(applications, app_id)
    if not application:
        abort(404)
    return render_template(
        'interview_form.html',
        application=application,
        interview=None,
    )


@app.route('/application/<app_id>/interview', methods=['POST'])
def create_interview(app_id):
    applications = load_applications()
    application = find_application(applications, app_id)
    if not application:
        abort(404)

    existing_ids = {iv['id'] for iv in application.get('interviews', [])}
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
        'voice_notes': [],
    }

    application.setdefault('interviews', []).append(interview)
    application['updated_at'] = now_str()
    save_applications(applications)
    flash('Entrevista agregada.', 'success')
    return redirect(
        url_for('application_detail', app_id=app_id) + f'#iv-{new_id}'
    )


@app.route('/application/<app_id>/interview/<interview_id>/edit')
def edit_interview(app_id, interview_id):
    applications = load_applications()
    application, interview = find_app_and_interview(applications, app_id, interview_id)
    if not application or not interview:
        abort(404)
    return render_template(
        'interview_form.html',
        application=application,
        interview=interview,
    )


@app.route('/application/<app_id>/interview/<interview_id>/edit', methods=['POST'])
def update_interview(app_id, interview_id):
    applications = load_applications()
    application, interview = find_app_and_interview(applications, app_id, interview_id)
    if not application or not interview:
        abort(404)

    interview['fecha_entrevista'] = request.form.get('fecha_entrevista', '').strip() or None
    interview['entrevistador_nombre'] = request.form.get('entrevistador_nombre', '').strip()
    interview['entrevistador_email'] = request.form.get('entrevistador_email', '').strip()
    interview['entrevistador_linkedin'] = request.form.get('entrevistador_linkedin', '').strip()
    interview['notas'] = request.form.get('notas', '').strip()
    interview['updated_at'] = now_str()
    application['updated_at'] = now_str()

    save_applications(applications)
    flash('Entrevista actualizada.', 'success')
    return redirect(
        url_for('application_detail', app_id=app_id) + f'#iv-{interview_id}'
    )


@app.route('/application/<app_id>/interview/<interview_id>/delete', methods=['POST'])
def delete_interview(app_id, interview_id):
    applications = load_applications()
    application, interview = find_app_and_interview(applications, app_id, interview_id)
    if not application or not interview:
        abort(404)

    # Cascade-delete the voice subdirectory for this interview
    shutil.rmtree(voice_path(app_id, interview_id), ignore_errors=True)
    application['interviews'] = [
        iv for iv in application.get('interviews', []) if iv['id'] != interview_id
    ]
    application['updated_at'] = now_str()
    save_applications(applications)
    flash('Entrevista eliminada.', 'success')
    return redirect(url_for('application_detail', app_id=app_id))


# --- Routes: Voice notes (nested) ---

@app.route('/application/<app_id>/interview/<interview_id>/voice', methods=['POST'])
def upload_voice(app_id, interview_id):
    applications = load_applications()
    application, interview = find_app_and_interview(applications, app_id, interview_id)
    if not application or not interview:
        return jsonify({'error': 'Entrevista no encontrada'}), 404

    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'No se recibió archivo de audio'}), 400

    original_name = audio_file.filename or 'nota.webm'
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = '.webm'

    filename = f"nota_{int(time.time() * 1000)}{ext}"
    target_dir = voice_path(app_id, interview_id)
    os.makedirs(target_dir, exist_ok=True)
    audio_file.save(os.path.join(target_dir, filename))

    created_at = now_str()
    interview.setdefault('voice_notes', []).append({
        'filename': filename,
        'created_at': created_at,
    })
    interview['updated_at'] = created_at
    application['updated_at'] = created_at
    save_applications(applications)

    return jsonify({
        'filename': filename,
        'url': url_for(
            'serve_voice',
            app_id=app_id,
            interview_id=interview_id,
            filename=filename,
        ),
        'created_at': created_at,
    }), 201


@app.route(
    '/application/<app_id>/interview/<interview_id>/voice/<filename>',
    methods=['DELETE'],
)
def delete_voice(app_id, interview_id, filename):
    safe_filename = os.path.basename(filename)
    applications = load_applications()
    application, interview = find_app_and_interview(applications, app_id, interview_id)
    if not application or not interview:
        return jsonify({'error': 'Entrevista no encontrada'}), 404

    filepath = os.path.join(voice_path(app_id, interview_id), safe_filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    interview['voice_notes'] = [
        vn for vn in interview.get('voice_notes', [])
        if vn['filename'] != safe_filename
    ]
    interview['updated_at'] = now_str()
    application['updated_at'] = now_str()
    save_applications(applications)
    return jsonify({'ok': True}), 200


@app.route('/voice/<app_id>/<interview_id>/<filename>')
def serve_voice(app_id, interview_id, filename):
    safe_filename = os.path.basename(filename)
    target_dir = voice_path(app_id, interview_id)
    return send_from_directory(target_dir, safe_filename)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
