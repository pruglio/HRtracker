# Postal de Oferta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Botón "Postal de oferta" en el detalle de postulaciones en etapa Oferta, que genera un PNG 1080×1080 con Pillow y lo comparte por WhatsApp con cierre fijo "ahora sí al País Vasco en Paz!! jaja".

**Architecture:** Endpoint Flask `/api/postal/<app_id>` que devuelve PNG generado on-demand con Pillow (sin persistir). Frontend agrega botón condicional + modal con preview + share JS reutilizando el patrón ya existente del share de notas TTS. Bonus: confetti.js dispara una vez por sesión cuando se abre un detalle en etapa Oferta.

**Tech Stack:** Flask, Pillow, Jinja2, vanilla JS, Web Share API, canvas-confetti (CDN).

---

### Task 1: Setup — Pillow y fuentes Outfit

**Files:**
- Modify: `requirements.txt`
- Create: `static/fonts/Outfit-Regular.ttf`
- Create: `static/fonts/Outfit-Medium.ttf`
- Create: `static/fonts/Outfit-Bold.ttf`
- Create: `static/fonts/Outfit-Italic.ttf`

- [ ] **Step 1: Agregar Pillow a requirements.txt**

Editar `requirements.txt` y agregar al final:

```
Pillow
```

- [ ] **Step 2: Descargar las 4 fuentes Outfit**

Ejecutar desde la raíz del proyecto:

```bash
mkdir -p static/fonts
cd static/fonts
curl -sL -o Outfit-Regular.ttf "https://github.com/googlefonts/Outfit/raw/main/fonts/ttf/Outfit-Regular.ttf"
curl -sL -o Outfit-Medium.ttf "https://github.com/googlefonts/Outfit/raw/main/fonts/ttf/Outfit-Medium.ttf"
curl -sL -o Outfit-Bold.ttf "https://github.com/googlefonts/Outfit/raw/main/fonts/ttf/Outfit-Bold.ttf"
curl -sL -o Outfit-Italic.ttf "https://github.com/googlefonts/Outfit/raw/main/fonts/ttf/Outfit-Italic.ttf"
ls -lh Outfit-*.ttf
```

Expected: cada archivo entre 40KB y 80KB.

Si Outfit no tiene Italic (algunas variantes Google Fonts solo tienen un Italic en otra subfolder), fallback: usar `Outfit-Regular.ttf` para el slot "Italic" — pero antes intentar la URL.

- [ ] **Step 3: Instalar Pillow localmente y validar**

```bash
source venv/bin/activate
pip install Pillow
python -c "from PIL import Image, ImageDraw, ImageFont; f = ImageFont.truetype('static/fonts/Outfit-Bold.ttf', 72); print('OK', f.size)"
```

Expected: `OK 72`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt static/fonts/Outfit-*.ttf
git commit -m "chore: agregar Pillow y fuentes Outfit para postal de oferta"
```

---

### Task 2: Backend — helper `generate_offer_postcard()`

**Files:**
- Modify: `app.py` (agregar imports + helper + ruta)

- [ ] **Step 1: Agregar imports al top de app.py**

Después de los imports existentes de `io` y `asyncio`, agregar:

```python
from PIL import Image, ImageDraw, ImageFont
import random as _random
```

(Si `import io` ya está, no duplicar. Si `random` ya está como `random`, usar el alias para no chocar.)

- [ ] **Step 2: Constantes de paths a las fuentes**

Agregar cerca de `APP_TZ`:

```python
FONTS_DIR = os.path.join(app.root_path, 'static', 'fonts')
FONT_REGULAR = os.path.join(FONTS_DIR, 'Outfit-Regular.ttf')
FONT_MEDIUM  = os.path.join(FONTS_DIR, 'Outfit-Medium.ttf')
FONT_BOLD    = os.path.join(FONTS_DIR, 'Outfit-Bold.ttf')
FONT_ITALIC  = os.path.join(FONTS_DIR, 'Outfit-Italic.ttf')
```

- [ ] **Step 3: Helper `generate_offer_postcard(app_entry)`**

Agregar antes de las rutas (cerca de los otros helpers como `compute_proxima_entrevista`):

```python
def generate_offer_postcard(app_entry):
    """
    Genera una postal PNG 1080x1080 para una postulación en etapa Oferta.
    Devuelve BytesIO con el PNG listo para servir.
    """
    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), '#FEF3C7')
    draw = ImageDraw.Draw(img, 'RGBA')

    # Gradiente vertical #FEF3C7 -> #DBEAFE
    top = (254, 243, 199)
    bot = (219, 234, 254)
    for y in range(H):
        t = y / H
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Confetti decorativo determinístico por app_id
    rng = _random.Random(app_entry['id'])
    confetti_colors = [(245,158,11),(239,68,68),(16,185,129),(59,130,246)]
    for _ in range(35):
        x = rng.randint(40, W - 40)
        y = rng.randint(40, H - 40)
        size = rng.randint(8, 14)
        color = rng.choice(confetti_colors) + (int(255 * rng.uniform(0.5, 0.7)),)
        shape = rng.choice(['circle', 'tri'])
        if shape == 'circle':
            draw.ellipse([x, y, x+size, y+size], fill=color)
        else:
            draw.polygon([(x, y+size), (x+size, y+size), (x+size/2, y)], fill=color)

    # Fuentes
    f_title    = ImageFont.truetype(FONT_BOLD, 56)
    f_small    = ImageFont.truetype(FONT_REGULAR, 28)
    f_empresa  = ImageFont.truetype(FONT_BOLD, 72)
    f_puesto   = ImageFont.truetype(FONT_MEDIUM, 36)
    f_modal    = ImageFont.truetype(FONT_MEDIUM, 24)
    f_mensaje  = ImageFont.truetype(FONT_ITALIC, 42)
    f_fecha    = ImageFont.truetype(FONT_REGULAR, 20)

    def center_text(text, font, y, fill='#0F172A'):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) / 2, y), text, font=font, fill=fill)
        return bbox[3] - bbox[1]  # alto

    y = 140
    center_text('¡TENGO UNA OFERTA!', f_title, y, fill='#0F172A')
    y += 90

    center_text('en', f_small, y, fill='#64748B')
    y += 50

    empresa = (app_entry.get('empresa') or '').strip()
    # Si la empresa es muy larga, reducir font dinámicamente
    f_emp = f_empresa
    for size in (72, 60, 50, 44):
        f_emp = ImageFont.truetype(FONT_BOLD, size)
        bbox = draw.textbbox((0, 0), empresa, font=f_emp)
        if (bbox[2] - bbox[0]) <= W - 120:
            break
    bbox = draw.textbbox((0, 0), empresa, font=f_emp)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, y), empresa, font=f_emp, fill='#2563EB')
    y += 110

    center_text('para el puesto de', f_small, y, fill='#64748B')
    y += 45

    puesto = (app_entry.get('puesto') or '').strip()
    # Reducir si es muy largo
    f_pue = f_puesto
    for size in (36, 32, 28, 24):
        f_pue = ImageFont.truetype(FONT_MEDIUM, size)
        bbox = draw.textbbox((0, 0), puesto, font=f_pue)
        if (bbox[2] - bbox[0]) <= W - 120:
            break
    bbox = draw.textbbox((0, 0), puesto, font=f_pue)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, y), puesto, font=f_pue, fill='#0F172A')
    y += 90

    # Chip de modalidad (si existe)
    modalidad = (app_entry.get('modalidad') or '').strip()
    if modalidad:
        chip_text = f'📍  {modalidad}'
        bbox = draw.textbbox((0, 0), chip_text, font=f_modal)
        cw = bbox[2] - bbox[0] + 40
        ch = bbox[3] - bbox[1] + 20
        cx = (W - cw) / 2
        draw.rounded_rectangle([cx, y, cx + cw, y + ch], radius=16,
                               fill='#FFFFFF', outline='#2563EB', width=2)
        draw.text((cx + 20, y + 10), chip_text, font=f_modal, fill='#2563EB')
        y += ch + 40

    # Separador
    sep_y = y + 30
    draw.line([(W/2 - 80, sep_y), (W/2 + 80, sep_y)], fill='#94A3B8', width=2)

    # Mensaje fijo del País Vasco
    mensaje = 'ahora sí al País Vasco en Paz!! jaja'
    bbox = draw.textbbox((0, 0), mensaje, font=f_mensaje)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, H - 280), mensaje, font=f_mensaje, fill='#DC2626')

    # Fecha
    fecha = datetime.now(APP_TZ).strftime('%d / %m / %Y')
    bbox = draw.textbbox((0, 0), fecha, font=f_fecha)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, H - 100), fecha, font=f_fecha, fill='#94A3B8')

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True, compress_level=6)
    buf.seek(0)
    return buf
```

- [ ] **Step 4: Ruta `/api/postal/<app_id>`**

Agregar cerca de la ruta `/api/tts`:

```python
@app.route('/api/postal/<app_id>')
def offer_postcard(app_id):
    app_entry = get_application(app_id)  # usar el helper que ya existe en app.py
    if not app_entry:
        abort(404)
    if app_entry.get('etapa') != 'Oferta':
        abort(404)
    try:
        buf = generate_offer_postcard(app_entry)
    except Exception as e:
        app.logger.exception('Error generando postal de oferta: %s', e)
        abort(500)
    resp = send_file(buf, mimetype='image/png', as_attachment=False,
                     download_name=f'oferta-{app_id}.png')
    resp.headers['Cache-Control'] = 'no-store'
    return resp
```

NOTA: si el helper para obtener una postulación se llama distinto (`get_app`, `fetch_application`, etc.), usar el nombre real. Si no existe un helper, replicar el patrón que usa la vista `application_detail`. El implementer subagent debe leer `app.py` primero para detectar el nombre exacto.

- [ ] **Step 5: Probar localmente**

```bash
source venv/bin/activate && python app.py &
sleep 2
# Buscar una postulación en Oferta
curl -s "http://localhost:5001/" | grep -o 'href="/applications/[^"]*"' | head -3
# Tomar un ID que esté en Oferta y probar:
curl -s -o /tmp/postal.png -w "%{http_code} %{content_type} %{size_download}\n" "http://localhost:5001/api/postal/<ID>"
file /tmp/postal.png
open /tmp/postal.png
kill %1
```

Expected: `200 image/png <bytes>` y el PNG abre y se ve la postal correctamente. Si abre y se ve mal (texto cortado, color raro), ajustar y reintentar.

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat(api): endpoint /api/postal/<app_id> genera PNG de oferta con Pillow"
```

---

### Task 3: Frontend — botón, modal, share y confetti

**Files:**
- Modify: `templates/application_detail.html`

- [ ] **Step 1: Agregar botón condicional en el header card**

En el bloque del header (cerca de los botones "Editar" / "Eliminar"), agregar al inicio del `<div class="d-flex gap-2 flex-shrink-0">`:

```html
{% if application.etapa == 'Oferta' %}
<button type="button" class="btn btn-primary btn-sm"
        data-bs-toggle="modal" data-bs-target="#postalModal">
  <i class="fas fa-envelope-open-text me-1"></i>Postal de oferta
</button>
{% endif %}
```

- [ ] **Step 2: Agregar el modal de la postal antes del cierre `{% endblock %}` del bloque content**

Justo antes del `deleteModal` (o después, no importa el orden):

```html
{% if application.etapa == 'Oferta' %}
<div class="modal fade" id="postalModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">
          <i class="fas fa-envelope-open-text text-primary me-2"></i>Postal de oferta
        </h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body text-center">
        <img id="postalImg"
             src="{{ url_for('offer_postcard', app_id=application.id) }}"
             alt="Postal de oferta"
             class="img-fluid rounded shadow-sm"
             style="max-height:60vh;">
        <p class="text-muted small mt-2 mb-0">
          <i class="fas fa-info-circle me-1"></i>
          Sin salario. Lista para compartir con tu familia.
        </p>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-secondary"
                data-bs-dismiss="modal">Cerrar</button>
        <button type="button" id="postalDownloadBtn" class="btn btn-outline-primary">
          <i class="fas fa-download me-1"></i>Descargar
        </button>
        <button type="button" id="postalShareBtn" class="btn btn-success">
          <i class="fab fa-whatsapp me-1"></i>Compartir por WhatsApp
        </button>
      </div>
    </div>
  </div>
</div>
{% endif %}
```

- [ ] **Step 3: Agregar JS en el bloque `extra_js` (al final del bloque DOMContentLoaded)**

Dentro del `document.addEventListener('DOMContentLoaded', function () { ... })`, antes del cierre, agregar:

```javascript
    // ── Postal de oferta: confetti + share ─────────────────────
    {% if application.etapa == 'Oferta' %}
    (function initOfferCelebration() {
      var appId = {{ application.id|tojson }};
      var empresa = {{ application.empresa|tojson }};
      var puesto  = {{ application.puesto|tojson }};
      var postalUrl = '/api/postal/' + appId;

      // Confetti una vez por sesión
      var confettiKey = 'confetti-app-' + appId;
      if (!sessionStorage.getItem(confettiKey)) {
        var script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.3/dist/confetti.browser.min.js';
        script.onload = function() {
          var colors = ['#F59E0B', '#EF4444', '#10B981', '#3B82F6', '#2563EB'];
          confetti({ particleCount: 120, spread: 70, origin: { y: 0.6 }, colors: colors });
          setTimeout(function() {
            confetti({ particleCount: 80, spread: 100, origin: { y: 0.7 }, colors: colors });
          }, 400);
          sessionStorage.setItem(confettiKey, '1');
        };
        document.head.appendChild(script);
      }

      // Slug para el nombre del archivo
      function slug(s) {
        return (s || 'oferta').toLowerCase()
          .replace(/\s+/g, '-')
          .replace(/[^a-z0-9\-]/g, '')
          .slice(0, 40) || 'oferta';
      }

      // Descargar PNG
      var dlBtn = document.getElementById('postalDownloadBtn');
      if (dlBtn) {
        dlBtn.addEventListener('click', async function() {
          var orig = dlBtn.innerHTML;
          dlBtn.disabled = true;
          dlBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Descargando...';
          try {
            var res = await fetch(postalUrl);
            if (!res.ok) throw new Error('Fetch falló');
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = 'oferta-' + slug(empresa) + '.png';
            a.click();
            setTimeout(function() { URL.revokeObjectURL(url); }, 2000);
          } catch (err) {
            alert('No se pudo descargar la postal.');
          } finally {
            dlBtn.disabled = false;
            dlBtn.innerHTML = orig;
          }
        });
      }

      // Compartir por WhatsApp
      var shareBtn = document.getElementById('postalShareBtn');
      if (shareBtn) {
        shareBtn.addEventListener('click', async function() {
          var orig = shareBtn.innerHTML;
          shareBtn.disabled = true;
          shareBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Preparando...';
          try {
            var res = await fetch(postalUrl);
            if (!res.ok) throw new Error('Fetch falló');
            var blob = await res.blob();
            var filename = 'oferta-' + slug(empresa) + '.png';
            var file = new File([blob], filename, { type: 'image/png' });

            var isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
            if (isMobile && navigator.canShare && navigator.canShare({ files: [file] })) {
              await navigator.share({
                files: [file],
                title: empresa + ' — ¡Oferta!',
                text: 'ahora sí al País Vasco en Paz!! jaja'
              });
            } else {
              // Desktop: descarga + abre WhatsApp Web
              var url = URL.createObjectURL(blob);
              var a = document.createElement('a');
              a.href = url; a.download = filename; a.click();
              setTimeout(function() { URL.revokeObjectURL(url); }, 2000);

              var msg = '*¡Recibí la oferta de ' + empresa + '!* Mirá la postal — ahora sí al País Vasco en Paz!! jaja';
              window.open('https://wa.me/?text=' + encodeURIComponent(msg), '_blank');
            }
          } catch (err) {
            if (err.name !== 'AbortError') {
              alert('No se pudo compartir la postal.');
            }
          } finally {
            shareBtn.disabled = false;
            shareBtn.innerHTML = orig;
          }
        });
      }
    })();
    {% endif %}
```

- [ ] **Step 4: Probar localmente**

```bash
source venv/bin/activate && python app.py &
sleep 2
open "http://localhost:5001/"
```

Verificar manualmente:
- Entrar a una postulación en etapa Oferta → confetti dispara una vez
- Botón "Postal de oferta" visible en el header
- Click → modal abre con preview de la postal cargado
- Click "Descargar" → baja un PNG con nombre `oferta-<empresa-slug>.png`
- Click "Compartir por WhatsApp" en desktop → descarga PNG + abre tab de WhatsApp Web con texto pre-armado
- Recargar la página → confetti NO vuelve a disparar
- Cambiar etapa a Final desde edit form → al volver al detalle, botón "Postal de oferta" no aparece

```bash
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add templates/application_detail.html
git commit -m "feat(ui): postal de oferta — botón, modal preview, share WhatsApp y confetti"
```

---

### Task 4: Deploy y verificación en producción

- [ ] **Step 1: Push a GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Deploy a Vercel**

```bash
vercel --prod --yes --scope pablorug-2599s-projects 2>&1 | grep -E "(Error|Production|https://)" | tail -5
```

Expected: línea `Production: https://...` sin errores.

- [ ] **Step 3: Verificar en producción**

```bash
open "https://hrtracker-one.vercel.app/"
```

Manualmente:
- Entrar a una postulación en etapa Oferta
- Confetti dispara
- Botón visible, modal abre con preview
- Compartir desde mobile (iPhone) abre share sheet con WhatsApp como opción
- El PNG en producción se ve idéntico al local (mismas fuentes, mismos colores)
