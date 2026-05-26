# Postal de Oferta — Design Spec

**Fecha:** 2026-05-26
**Estado:** Aprobado para implementación
**Goal:** Cuando una postulación llega a etapa "Oferta", el usuario puede generar una postal visual (PNG cuadrado 1080×1080) con los datos clave y compartirla por WhatsApp con su novia. El cierre fijo es *"ahora sí al País Vasco en Paz!! jaja"*.

---

## Trigger y entrada

- Botón **"Postal de oferta"** (`fa-envelope-open-text`, `btn-primary`) en el header del detalle de la postulación, visible solo si `application.etapa == 'Oferta'`.
- Click abre un modal Bootstrap con:
  - Preview de la postal (img tag con `src=/api/postal/<app_id>`)
  - Botón **"Compartir por WhatsApp"** (`btn-success`, `fab fa-whatsapp`)
  - Botón **"Descargar PNG"** (secundario)
  - Botón cancelar

## Generación de la postal

**Endpoint:** `GET /api/postal/<app_id>` → devuelve `image/png`

- Solo responde si la postulación existe y está en etapa `Oferta`. Si no, devuelve 404.
- Sin caché HTTP (header `Cache-Control: no-store`) — la postal puede regenerarse si cambia el puesto/empresa.

**Implementación con Pillow:**

- Canvas: 1080×1080, fondo gradiente lineal vertical de `#FEF3C7` (top) a `#DBEAFE` (bottom)
- Confetti decorativo: 35 elementos (mezcla de círculos pequeños 8-14px y triángulos), colores `#F59E0B`, `#EF4444`, `#10B981`, `#3B82F6`, opacidad 0.5-0.7, posiciones pseudo-aleatorias pero determinísticas (semilla = `app_id`) para que la misma postulación genere siempre la misma postal
- Layout vertical centrado:

  ```
  ✦ ¡TENGO UNA OFERTA! ✦         (Outfit Bold 56px, color #0F172A, top ~140px)

  en                              (Outfit Regular 28px, color #64748B)

  {EMPRESA}                       (Outfit Bold 72px, color #2563EB, centro vertical superior)

  para el puesto de               (Outfit Regular 28px, color #64748B)

  {PUESTO}                        (Outfit Medium 36px, color #0F172A)

  📍 {MODALIDAD}                  (Outfit Medium 24px, chip con borde redondeado,
                                   solo si application.modalidad no es null)

  ──────────                      (separador, 80px de ancho, color #94A3B8)

  ahora sí al País Vasco en Paz!! jaja
                                  (Outfit Italic 42px, color #DC2626, ~bottom 220px)

  {DD / MM / YYYY}                (Outfit Regular 20px, color #94A3B8, bottom 80px)
  ```

- Sin salario, sin rating, sin beneficios — solo lo de arriba.

**Fuentes:** se incluyen los .ttf de Outfit en `static/fonts/` (Bold, Italic, Medium, Regular). Si por alguna razón no se encuentran, fallback al DejaVu Sans que viene con Pillow.

## Compartir por WhatsApp

Reutiliza el patrón existente del WhatsApp share de notas (en `application_detail.html`):

1. Fetch a `/api/postal/<app_id>` → blob
2. Crear `File` con nombre `oferta-{empresa-slug}.png` y type `image/png`
3. Detección de mobile via `/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)`
4. **Mobile + canShare**: `navigator.share({ files: [file], title: empresa + ' — Oferta!', text: 'ahora sí al País Vasco en Paz!! jaja' })`
5. **Desktop o sin canShare**: descarga el PNG + abre `wa.me/?text=...` con texto pre-armado:
   > `*¡Recibí la oferta de {EMPRESA}!* Mirá la postal — ahora sí al País Vasco en Paz!! jaja`

Sin emoji en el texto pre-armado (decisión: limpio).

## Bonus celebratorio (alcance mínimo, opcional pero incluido)

Cuando se carga el detalle de una postulación en etapa `Oferta`, una sola vez por sesión por postulación:

- Disparar `canvas-confetti` (cargado por CDN, ~5kb): 2 ráfagas, 200 partículas total, colores `['#F59E0B', '#EF4444', '#10B981', '#3B82F6', '#2563EB']`
- Control: `sessionStorage.getItem('confetti-app-' + appId)` — si existe no dispara
- Después de disparar, `sessionStorage.setItem('confetti-app-' + appId, '1')`

## Archivos a tocar

**Crear:**
- `static/fonts/Outfit-Bold.ttf`, `Outfit-Italic.ttf`, `Outfit-Medium.ttf`, `Outfit-Regular.ttf` (descargar de Google Fonts una vez, incluir en repo)

**Modificar:**
- `requirements.txt` — agregar `Pillow` (sin pin de versión, latest)
- `app.py` — nueva ruta `GET /api/postal/<app_id>` + helper `generate_offer_postcard(app_dict) -> BytesIO`
- `templates/application_detail.html` — botón condicional en header + modal + JS para share/download/confetti

## Constraints técnicas

- **Vercel serverless:** Pillow funciona bien en lambda Python, pero las fuentes deben estar en el repo (no descargarlas en runtime)
- **Tamaño del PNG:** target <300KB (compresión PNG nivel 6, optimize=True). 1080×1080 con poca complejidad gráfica debería caer cómodo.
- **Memoria del lambda:** Pillow consume ~50MB pico para 1080×1080. Vercel free tier permite 1024MB, sin problema.

## Out of scope

- Personalizar el mensaje por postulación (decisión: fijo)
- Mostrar salario (decisión: no)
- Otros formatos (story vertical 1080×1920): si después se pide, fácil de agregar como segundo endpoint
- Persistir las postales generadas (regeneración on-demand cada vez)

## Verificación

Después de implementar:
1. Cambiar una postulación a `Oferta` desde edit form
2. Volver al detalle → confetti dispara una vez
3. Clic en "Postal de oferta" → modal con preview cargado
4. **Mobile real (iPhone/Android):** clic en "Compartir por WhatsApp" → share sheet con WhatsApp visible
5. **Desktop:** clic descarga el PNG + abre tab de WhatsApp Web con texto pre-armado
6. Comprobar que el PNG tiene: empresa, puesto, modalidad (si la hay), mensaje del País Vasco, fecha
7. Recargar el detalle → confetti NO vuelve a disparar (sessionStorage)
8. Cambiar etapa a otra cosa (ej. Final) → botón "Postal de oferta" desaparece
