'use strict';
for (const button of document.querySelectorAll('[data-print]')) button.addEventListener('click', () => window.print());
const search = document.querySelector('#search');
if (search) {
  let destination = 'Tous';
  const normal = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ');
  // Normalize the static catalogue once, not on every keystroke.
  const cards = Array.from(document.querySelectorAll('#guide-grid .card'), card => ({
    card,
    text: normal(card.dataset.search || ''),
  }));
  function filter() {
    // All keywords must match, independently of their order or punctuation.
    const terms = normal(search.value).trim().split(/\s+/).filter(Boolean);
    const selectedDestination = normal(destination);
    let count = 0;
    for (const { card, text } of cards) {
      const matchesDestination = destination === 'Tous' || card.dataset.destination === destination || text.includes(selectedDestination);
      const matches = matchesDestination && terms.every(term => text.includes(term));
      card.hidden = !matches;
      if (matches) count++;
    }
    document.querySelector('#result-count').textContent = `${count} guide${count > 1 ? 's' : ''} pour préparer votre séjour`;
    document.querySelector('#empty').hidden = count !== 0;
  }
  search.addEventListener('input', filter);
  for (const button of document.querySelectorAll('[data-filter]')) button.addEventListener('click', () => {
    destination = button.dataset.filter;
    for (const other of document.querySelectorAll('[data-filter]')) other.setAttribute('aria-pressed', String(other === button));
    filter();
  });
  // Apply a value already present when the browser restores the form.
  filter();
}
