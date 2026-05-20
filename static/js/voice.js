// ============================================================
// voice.js — Voice-to-text (Web Speech API) + Voice note
//             recording (MediaRecorder API)
// ============================================================

// --- VOICE TO TEXT ---

function initVoiceToText() {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  const micBtns = document.querySelectorAll('.mic-btn');

  if (!SpeechRecognition) {
    micBtns.forEach(btn => {
      btn.disabled = true;
      btn.title = 'Tu navegador no soporta dictado por voz (usá Chrome o Edge)';
      const icon = btn.querySelector('i');
      if (icon) icon.className = 'fas fa-microphone-slash';
    });
    return;
  }

  micBtns.forEach(btn => {
    let recognition = null;
    let isListening = false;

    // Find or create the interim display span
    const container = btn.closest('.input-group, .form-section-title, .mb-3, p');
    const interimSpan = container
      ? container.parentElement
          ? container.parentElement.querySelector('.interim-text')
          : null
      : null;

    btn.addEventListener('click', () => {
      if (isListening) {
        recognition.stop();
        return;
      }

      const targetId = btn.dataset.target;
      const target = document.getElementById(targetId);
      if (!target) return;

      recognition = new SpeechRecognition();
      recognition.lang = 'es-ES';
      recognition.continuous = false;
      recognition.interimResults = true;

      setListening(true);

      recognition.onresult = event => {
        let interim = '';
        let finalText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) {
            finalText += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }
        if (interimSpan) interimSpan.textContent = interim;
        if (finalText) {
          const current = target.value.trim();
          target.value = current
            ? current + ' ' + finalText.trim()
            : finalText.trim();
          if (interimSpan) interimSpan.textContent = '';
        }
      };

      recognition.onerror = () => setListening(false);
      recognition.onend = () => setListening(false);

      recognition.start();
    });

    function setListening(active) {
      isListening = active;
      if (active) {
        btn.classList.add('btn-danger');
        btn.classList.remove('btn-outline-secondary');
        const icon = btn.querySelector('i');
        if (icon) icon.className = 'fas fa-microphone-alt';
      } else {
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-outline-secondary');
        const icon = btn.querySelector('i');
        if (icon) icon.className = 'fas fa-microphone';
        if (interimSpan) interimSpan.textContent = '';
      }
    }
  });
}


// --- VOICE NOTE RECORDER ---

function initVoiceRecorder(applicationId, interviewId, prefix) {
  const recordBtn = document.getElementById(`record-btn-${prefix}`);
  if (!recordBtn) return;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    recordBtn.disabled = true;
    recordBtn.title = 'Tu navegador no soporta grabación de audio';
    return;
  }

  const stopBtn = document.getElementById(`stop-btn-${prefix}`);
  const recordingIndicator = document.getElementById(`recording-indicator-${prefix}`);

  let mediaRecorder = null;
  let chunks = [];

  recordBtn.addEventListener('click', async () => {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      alert('No se pudo acceder al micrófono. Por favor, concedé permisos de audio.');
      return;
    }

    chunks = [];

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : '';

    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});

    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());

      const ext = mimeType.includes('ogg') ? '.ogg' : '.webm';
      const blob = new Blob(chunks, { type: mimeType || 'audio/webm' });
      const formData = new FormData();
      formData.append('audio', blob, `nota${ext}`);

      recordBtn.disabled = true;
      recordBtn.innerHTML =
        '<i class="fas fa-spinner fa-spin me-1"></i>Guardando...';

      try {
        const resp = await fetch(
          `/application/${applicationId}/interview/${interviewId}/voice`,
          { method: 'POST', body: formData },
        );
        if (!resp.ok) throw new Error('Server error');
        const data = await resp.json();
        appendVoiceNote(data, applicationId, interviewId, prefix);
        const empty = document.getElementById(`voice-notes-empty-${prefix}`);
        if (empty) empty.style.display = 'none';
      } catch {
        alert('Error al guardar la nota de voz. Intentá de nuevo.');
      } finally {
        recordBtn.disabled = false;
        recordBtn.innerHTML =
          '<i class="fas fa-microphone me-1"></i>Grabar';
      }
    };

    mediaRecorder.start();

    recordBtn.style.display = 'none';
    stopBtn.style.display = 'inline-block';
    recordingIndicator.style.display = 'inline-flex';
  });

  stopBtn.addEventListener('click', () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    recordBtn.style.display = 'inline-block';
    stopBtn.style.display = 'none';
    recordingIndicator.style.display = 'none';
  });
}


function appendVoiceNote(data, applicationId, interviewId, prefix) {
  const list = document.getElementById(`voice-notes-list-${prefix}`);
  const div = document.createElement('div');
  div.className =
    'voice-note-item d-flex align-items-center gap-2 mb-2 p-2 border rounded';
  div.dataset.filename = data.filename;
  div.innerHTML = `
    <span class="text-muted small text-nowrap">
      <i class="fas fa-clock me-1"></i>${data.created_at}
    </span>
    <audio controls src="${data.url}" class="flex-grow-1" style="height:36px; min-width:0;"></audio>
    <button type="button"
            class="btn btn-sm btn-outline-danger delete-voice-btn flex-shrink-0"
            data-filename="${data.filename}"
            data-app-id="${applicationId}"
            data-interview-id="${interviewId}"
            data-prefix="${prefix}"
            title="Eliminar nota">
      <i class="fas fa-trash"></i>
    </button>
  `;
  list.appendChild(div);
  div.querySelector('.delete-voice-btn').addEventListener('click', handleDeleteVoiceNote);
}


async function handleDeleteVoiceNote(e) {
  const btn = e.currentTarget;
  const filename = btn.dataset.filename;
  const applicationId = btn.dataset.appId;
  const interviewId = btn.dataset.interviewId;
  const prefix = btn.dataset.prefix || interviewId;

  if (!confirm('¿Eliminás esta nota de voz?')) return;

  try {
    const resp = await fetch(
      `/application/${applicationId}/interview/${interviewId}/voice/${filename}`,
      { method: 'DELETE' },
    );
    if (!resp.ok) throw new Error();
    btn.closest('.voice-note-item').remove();
    const list = document.getElementById(`voice-notes-list-${prefix}`);
    if (list && list.children.length === 0) {
      const empty = document.getElementById(`voice-notes-empty-${prefix}`);
      if (empty) empty.style.display = 'block';
    }
  } catch {
    alert('No se pudo eliminar la nota. Intentá de nuevo.');
  }
}
