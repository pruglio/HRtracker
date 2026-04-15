import json
import os
import shutil
import time
import uuid
from datetime import datetime

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)

app = Flask(__name__)
app.secret_key = 'hrtracker-secret-key-2026'

DATA_FILE = 'data/interviews.json'
VOICE_DIR = 'data/voice_notes'

ALLOWED_ETAPAS = [
    'Aplicado', 'Pantalla HR', 'Técnica', 'Final',
    'Oferta', 'Rechazado', 'Descartado'
]
ALLOWED_MODALIDADES = ['Remoto', 'Presencial', 'Híbrido']
ALLOWED_EXTENSIONS = {'.webm', '.ogg', '.wav', '.mp4', '.m4a'}


# --- Helpers ---

def load_interviews():
    os.makedirs('data', exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_interviews(interviews):
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(interviews, f, ensure_ascii=False, indent=2)


def find_by_id(interviews, interview_id):
    return next((i for i in interviews if i['id'] == interview_id), None)


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


def parse_date_filter(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


# --- Routes ---

@app.route('/')
def index():
    interviews = load_interviews()

    # Filters
    f_etapa = request.args.get('etapa', '').strip()
    f_empresa = request.args.get('empresa', '').strip()
    f_desde = request.args.get('desde', '').strip()
    f_hasta = request.args.get('hasta', '').strip()

    filtered = interviews

    if f_etapa and f_etapa in ALLOWED_ETAPAS:
        filtered = [i for i in filtered if i.get('etapa') == f_etapa]

    if f_empresa:
        filtered = [i for i in filtered
                    if f_empresa.lower() in i.get('empresa', '').lower()]

    desde_date = parse_date_filter(f_desde)
    if desde_date:
        filtered = [i for i in filtered
                    if i.get('fecha_entrevista') and
                    datetime.strptime(i['fecha_entrevista'], '%Y-%m-%d').date() >= desde_date]

    hasta_date = parse_date_filter(f_hasta)
    if hasta_date:
        filtered = [i for i in filtered
                    if i.get('fecha_entrevista') and
                    datetime.strptime(i['fecha_entrevista'], '%Y-%m-%d').date() <= hasta_date]

    # Sort by fecha_entrevista descending, nulls last
    filtered.sort(
        key=lambda i: i.get('fecha_entrevista') or '0000-00-00',
        reverse=True
    )

    return render_template(
        'index.html',
        interviews=filtered,
        total=len(interviews),
        etapas=ALLOWED_ETAPAS,
        f_etapa=f_etapa,
        f_empresa=f_empresa,
        f_desde=f_desde,
        f_hasta=f_hasta,
    )


@app.route('/interview/new')
def new_interview():
    return render_template(
        'interview_form.html',
        interview=None,
        etapas=ALLOWED_ETAPAS,
        modalidades=ALLOWED_MODALIDADES,
    )


@app.route('/interview', methods=['POST'])
def create_interview():
    empresa = request.form.get('empresa', '').strip()
    puesto = request.form.get('puesto', '').strip()

    if not empresa or not puesto:
        flash('Empresa y puesto son obligatorios.', 'danger')
        return redirect(url_for('new_interview'))

    etapa = request.form.get('etapa', 'Aplicado')
    if etapa not in ALLOWED_ETAPAS:
        etapa = 'Aplicado'

    modalidad = request.form.get('modalidad', '')
    if modalidad not in ALLOWED_MODALIDADES:
        modalidad = ''

    interviews = load_interviews()
    existing_ids = {i['id'] for i in interviews}
    new_id = make_id(existing_ids)

    interview = {
        'id': new_id,
        'created_at': now_str(),
        'updated_at': now_str(),
        'empresa': empresa,
        'puesto': puesto,
        'fecha_entrevista': request.form.get('fecha_entrevista', '').strip() or None,
        'etapa': etapa,
        'entrevistador_nombre': request.form.get('entrevistador_nombre', '').strip(),
        'entrevistador_email': request.form.get('entrevistador_email', '').strip(),
        'entrevistador_linkedin': request.form.get('entrevistador_linkedin', '').strip(),
        'salario_min': parse_salary(request.form.get('salario_min')),
        'salario_max': parse_salary(request.form.get('salario_max')),
        'modalidad': modalidad,
        'notas': request.form.get('notas', '').strip(),
        'voice_notes': [],
    }

    interviews.append(interview)
    save_interviews(interviews)
    flash('Entrevista guardada correctamente.', 'success')
    return redirect(url_for('detail', interview_id=new_id))


@app.route('/interview/<interview_id>')
def detail(interview_id):
    interviews = load_interviews()
    interview = find_by_id(interviews, interview_id)
    if not interview:
        abort(404)
    return render_template('interview_detail.html', interview=interview)


@app.route('/interview/<interview_id>/edit')
def edit_interview(interview_id):
    interviews = load_interviews()
    interview = find_by_id(interviews, interview_id)
    if not interview:
        abort(404)
    return render_template(
        'interview_form.html',
        interview=interview,
        etapas=ALLOWED_ETAPAS,
        modalidades=ALLOWED_MODALIDADES,
    )


@app.route('/interview/<interview_id>/edit', methods=['POST'])
def update_interview(interview_id):
    interviews = load_interviews()
    interview = find_by_id(interviews, interview_id)
    if not interview:
        abort(404)

    empresa = request.form.get('empresa', '').strip()
    puesto = request.form.get('puesto', '').strip()

    if not empresa or not puesto:
        flash('Empresa y puesto son obligatorios.', 'danger')
        return redirect(url_for('edit_interview', interview_id=interview_id))

    etapa = request.form.get('etapa', interview['etapa'])
    if etapa not in ALLOWED_ETAPAS:
        etapa = interview['etapa']

    modalidad = request.form.get('modalidad', '')
    if modalidad not in ALLOWED_MODALIDADES:
        modalidad = ''

    interview['empresa'] = empresa
    interview['puesto'] = puesto
    interview['fecha_entrevista'] = request.form.get('fecha_entrevista', '').strip() or None
    interview['etapa'] = etapa
    interview['entrevistador_nombre'] = request.form.get('entrevistador_nombre', '').strip()
    interview['entrevistador_email'] = request.form.get('entrevistador_email', '').strip()
    interview['entrevistador_linkedin'] = request.form.get('entrevistador_linkedin', '').strip()
    interview['salario_min'] = parse_salary(request.form.get('salario_min'))
    interview['salario_max'] = parse_salary(request.form.get('salario_max'))
    interview['modalidad'] = modalidad
    interview['notas'] = request.form.get('notas', '').strip()
    interview['updated_at'] = now_str()

    save_interviews(interviews)
    flash('Entrevista actualizada correctamente.', 'success')
    return redirect(url_for('detail', interview_id=interview_id))


@app.route('/interview/<interview_id>/delete', methods=['POST'])
def delete_interview(interview_id):
    interviews = load_interviews()
    interview = find_by_id(interviews, interview_id)
    if not interview:
        abort(404)

    shutil.rmtree(os.path.join(VOICE_DIR, interview_id), ignore_errors=True)
    interviews = [i for i in interviews if i['id'] != interview_id]
    save_interviews(interviews)
    flash('Entrevista eliminada.', 'success')
    return redirect(url_for('index'))


@app.route('/interview/<interview_id>/voice', methods=['POST'])
def upload_voice(interview_id):
    interviews = load_interviews()
    interview = find_by_id(interviews, interview_id)
    if not interview:
        return jsonify({'error': 'Entrevista no encontrada'}), 404

    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'No se recibió archivo de audio'}), 400

    original_name = audio_file.filename or 'nota.webm'
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = '.webm'

    filename = f"nota_{int(time.time() * 1000)}{ext}"
    voice_dir = os.path.join(VOICE_DIR, interview_id)
    os.makedirs(voice_dir, exist_ok=True)
    audio_file.save(os.path.join(voice_dir, filename))

    created_at = now_str()
    interview['voice_notes'].append({
        'filename': filename,
        'created_at': created_at,
    })
    save_interviews(interviews)

    return jsonify({
        'filename': filename,
        'url': url_for('serve_voice', interview_id=interview_id, filename=filename),
        'created_at': created_at,
    }), 201


@app.route('/interview/<interview_id>/voice/<filename>', methods=['DELETE'])
def delete_voice(interview_id, filename):
    safe_filename = os.path.basename(filename)
    interviews = load_interviews()
    interview = find_by_id(interviews, interview_id)
    if not interview:
        return jsonify({'error': 'Entrevista no encontrada'}), 404

    filepath = os.path.join(VOICE_DIR, interview_id, safe_filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    interview['voice_notes'] = [
        vn for vn in interview['voice_notes']
        if vn['filename'] != safe_filename
    ]
    save_interviews(interviews)
    return jsonify({'ok': True}), 200


@app.route('/voice/<interview_id>/<filename>')
def serve_voice(interview_id, filename):
    safe_filename = os.path.basename(filename)
    voice_dir = os.path.join(VOICE_DIR, os.path.basename(interview_id))
    return send_from_directory(voice_dir, safe_filename)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port)
