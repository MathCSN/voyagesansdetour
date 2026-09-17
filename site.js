'use strict';
for (const button of document.querySelectorAll('[data-print]')) button.addEventListener('click', () => window.print());
const search = document.querySelector('#search');
if (search) {
  let destination = 'Tous';
  const cards = Array.from(document.querySelectorAll('#guide-grid .card'));
  const normal = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  function filter() {
    const query = normal(search.value.trim());
    let count = 0;
    for (const card of cards) {
      const text = normal(card.dataset.search || '');
      const matches = (destination === 'Tous' || card.dataset.destination === destination || text.includes(normal(destination))) && text.includes(query);
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
}
