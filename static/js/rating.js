// ============================================================
// rating.js — 1-5 star rating widget (AJAX, no page reload)
// ============================================================

function initRatingStars() {
  document.querySelectorAll('.rating-stars').forEach(container => {
    // Attach click handlers to each individual star
    container.querySelectorAll('i[data-value]').forEach(star => {
      star.addEventListener('click', () => {
        const value = parseInt(star.dataset.value, 10);
        saveRating(container, value);
      });
    });

    // Clear-rating icon
    const clearBtn = container.querySelector('.clear-rating');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        saveRating(container, null);
      });
    }
  });
}


async function saveRating(container, rating) {
  const appId = container.dataset.appId;
  const previous = parseInt(container.dataset.rating, 10) || 0;

  // Optimistic UI update
  renderRating(container, rating);

  try {
    const resp = await fetch(`/application/${appId}/rating`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating: rating }),
    });
    if (!resp.ok) throw new Error('Server error');
    const data = await resp.json();
    // Sync with server response
    renderRating(container, data.rating);
  } catch {
    // Revert
    renderRating(container, previous || null);
    alert('No se pudo guardar el rating. Intentá de nuevo.');
  }
}


function renderRating(container, rating) {
  const value = rating || 0;
  container.dataset.rating = value;
  container.querySelectorAll('i[data-value]').forEach(star => {
    const sv = parseInt(star.dataset.value, 10);
    if (value && sv <= value) {
      star.classList.add('fas', 'text-warning');
      star.classList.remove('far', 'text-muted');
    } else {
      star.classList.add('far', 'text-muted');
      star.classList.remove('fas', 'text-warning');
    }
  });
  const clearBtn = container.querySelector('.clear-rating');
  if (clearBtn) {
    clearBtn.style.display = value ? '' : 'none';
  }
}
