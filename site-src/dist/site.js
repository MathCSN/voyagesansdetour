'use strict';
for (const button of document.querySelectorAll('[data-print]')) button.addEventListener('click', () => window.print());
const search = document.querySelector('#search');
if (search) {
  let selected = 'Tous';
  // Les boutons comparent un champ exact de la carte : sa destination (pages pays), son pays (continents et
  // rubriques) ou ses rubriques (tous les guides). La recherche libre porte, elle, sur tout le texte de la carte.
  const by = document.querySelector('#guide-grid').dataset.filterBy;
  const values = card => (by === 'theme' ? (card.dataset.themes || '').split('|') : [by === 'country' ? card.dataset.country : card.dataset.destination]);
  const cards = Array.from(document.querySelectorAll('#guide-grid .card'));
  const normal = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  function filter() {
    const query = normal(search.value.trim());
    let count = 0;
    for (const card of cards) {
      const text = normal(card.dataset.search || '');
      const matches = (selected === 'Tous' || values(card).includes(selected)) && text.includes(query);
      card.hidden = !matches;
      if (matches) count++;
    }
    document.querySelector('#result-count').textContent = `${count} guide${count > 1 ? 's' : ''} pour préparer votre séjour`;
    document.querySelector('#empty').hidden = count !== 0;
  }
  search.addEventListener('input', filter);
  for (const button of document.querySelectorAll('[data-filter]')) button.addEventListener('click', () => {
    selected = button.dataset.filter;
    for (const other of document.querySelectorAll('[data-filter]')) other.setAttribute('aria-pressed', String(other === button));
    filter();
  });
}
