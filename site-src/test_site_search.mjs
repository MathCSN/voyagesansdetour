import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

// No dependencies or external calls. Execute the actual browser script against
// a minimal DOM double; this does not replace a full browser/accessibility test.
// VSD_SEARCH_SCRIPT allows replaying these regressions against a previous script.
const source = readFileSync(process.env.VSD_SEARCH_SCRIPT || new URL('./dist/site.js', import.meta.url), 'utf8');
const guides = [
  ['lisbonne', 'Lisbonne', 'Lisbonne en 3 jours, sans voiture et sans courir Trois journées par quartier, les transports utiles et les réservations à prévoir pour découvrir Lisbonne sans louer de voiture. Itinéraires'],
  ['porto', 'Porto', 'Porto en 3 jours : du Douro à l’océan, sans voiture Un itinéraire de trois jours à Porto : centre historique, Gaia et Atlantique, avec les bons réflexes pour les transports. Itinéraires'],
  ['sintra', 'Sintra', 'Sintra depuis Lisbonne : organiser une journée sans voiture Train, accès au palais de Pena et programme réaliste : les décisions à prendre pour visiter Sintra depuis Lisbonne. Excursions'],
  ['comparatif', 'Portugal', 'Lisbonne ou Porto : quelle ville choisir pour un premier séjour ? Comparez Lisbonne et Porto selon votre temps, vos envies et vos déplacements, sans réduire le choix à un classement. Bien choisir'],
  ['train', 'Portugal', 'Lisbonne–Porto en train : choisir les gares et réserver simplement Alfa Pendular ou Intercidades, gares de départ, arrivée à Campanhã et réservation : préparer son trajet Lisbonne–Porto. Transports'],
  ['quartiers', 'Lisbonne', 'Où dormir à Lisbonne sans voiture : choisir son quartier Baixa, Chiado, Alfama, Bairro Alto ou Cais do Sodré : choisir une base à Lisbonne selon les pentes, les transports et le bruit. Où dormir'],
  ['aeroport', 'Porto', 'Aéroport de Porto au centre-ville : métro, correspondances et choix de l’arrivée Choisir son trajet depuis l’aéroport de Porto : ligne E, titre Andante, correspondances, bagages et solution de repli pour une arrivée tardive. Transports'],
];

function element(properties = {}) {
  const listeners = new Map();
  const attributes = {};
  return {
    dataset: {}, hidden: false, ...properties, attributes,
    addEventListener(name, callback) {
      const callbacks = listeners.get(name) || [];
      callbacks.push(callback);
      listeners.set(name, callbacks);
    },
    setAttribute(name, value) { attributes[name] = value; },
    dispatch(name) { for (const callback of listeners.get(name) || []) callback(); },
  };
}

function setup({ value = '', hasSearch = true, entries = guides } = {}) {
  const search = hasSearch ? element({ value }) : null;
  const cards = entries.map(([id, destination, text]) => element({ id, dataset: { destination, search: text } }));
  const filters = ['Tous', 'Lisbonne', 'Porto', 'Sintra'].map(filter => {
    const button = element({ dataset: { filter } });
    button.setAttribute('aria-pressed', String(filter === 'Tous'));
    return button;
  });
  const count = element({ textContent: `${cards.length} guides pour préparer votre séjour` });
  const empty = element({ hidden: true });
  const printButton = element();
  let printCalls = 0;
  const document = {
    querySelector(selector) {
      return { '#search': search, '#result-count': count, '#empty': empty }[selector] ?? null;
    },
    querySelectorAll(selector) {
      return { '#guide-grid .card': cards, '[data-filter]': filters, '[data-print]': [printButton] }[selector] || [];
    },
  };
  runInNewContext(source, { document, window: { print() { printCalls++; } } }, { timeout: 1000 });
  return {
    cards, filters, count, empty,
    input(value) { search.value = value; search.dispatch('input'); },
    select(destination) {
      const button = filters.find(item => item.dataset.filter === destination);
      assert.ok(button, `Unknown fixture filter: ${destination}`);
      button.dispatch('click');
    },
    visible() { return cards.filter(card => !card.hidden).map(card => card.id); },
    print() { printButton.dispatch('click'); return printCalls; },
  };
}

const allIds = guides.map(([id]) => id);

test('published copy and generator source stay identical', () => {
  assert.equal(readFileSync(new URL('../site.js', import.meta.url), 'utf8'), readFileSync(new URL('./dist/site.js', import.meta.url), 'utf8'));
});

test('empty search keeps all guides visible', () => {
  const ui = setup();
  assert.deepEqual(ui.visible(), allIds);
  assert.equal(ui.empty.hidden, true);
});

test('separated keywords find the train guide', () => {
  const ui = setup();
  ui.input('porto train');
  assert.deepEqual(ui.visible(), ['train']);
});

test('keyword order does not matter', () => {
  const ui = setup();
  ui.input('train porto');
  assert.deepEqual(ui.visible(), ['train']);
});

test('all keywords must be present, not just one', () => {
  const ui = setup();
  ui.input('porto train avion');
  assert.deepEqual(ui.visible(), []);
  assert.equal(ui.empty.hidden, false);
});

test('existing accent-insensitive matching is preserved', () => {
  const ui = setup();
  ui.input('aeroport');
  assert.deepEqual(ui.visible(), ['aeroport']);
});

test('case and repeated whitespace do not affect matching', () => {
  const ui = setup();
  ui.input('  AÉROPORT\t MÉTRO\n ');
  assert.deepEqual(ui.visible(), ['aeroport']);
});

test('decomposed accents match composed article text', () => {
  const ui = setup();
  ui.input('ae\u0301roport');
  assert.deepEqual(ui.visible(), ['aeroport']);
});

test('ordinary hyphens match typographic dashes', () => {
  const ui = setup();
  ui.input('Lisbonne-Porto');
  assert.deepEqual(ui.visible(), ['comparatif', 'train']);
});

test('spaces match hyphenated words', () => {
  const ui = setup();
  ui.input('centre ville');
  assert.deepEqual(ui.visible(), ['aeroport']);
});

test('straight apostrophes match typographic apostrophes', () => {
  const ui = setup();
  ui.input("l'aeroport");
  assert.deepEqual(ui.visible(), ['aeroport']);
});

test('numbers remain meaningful keywords', () => {
  const ui = setup();
  ui.input('3 porto');
  assert.deepEqual(ui.visible(), ['porto']);
});

test('punctuation-only input acts like an empty search', () => {
  const ui = setup();
  ui.input(' — , ? ');
  assert.deepEqual(ui.visible(), allIds);
});

test('destination filtering still includes cross-city guides', () => {
  const ui = setup();
  ui.select('Porto');
  assert.deepEqual(ui.visible(), ['porto', 'comparatif', 'train', 'aeroport']);
});

test('destination and keyword filters are combined', () => {
  const ui = setup();
  ui.input('train');
  ui.select('Porto');
  assert.deepEqual(ui.visible(), ['train']);
  ui.select('Sintra');
  assert.deepEqual(ui.visible(), ['sintra']);
});

test('only the chosen destination button is pressed', () => {
  const ui = setup();
  ui.select('Sintra');
  for (const button of ui.filters) {
    assert.equal(button.attributes['aria-pressed'], String(button.dataset.filter === 'Sintra'));
  }
});

test('clearing a query retains the selected destination', () => {
  const ui = setup();
  ui.select('Porto');
  ui.input('inexistant');
  assert.deepEqual(ui.visible(), []);
  ui.input('');
  assert.deepEqual(ui.visible(), ['porto', 'comparatif', 'train', 'aeroport']);
  ui.select('Tous');
  assert.deepEqual(ui.visible(), allIds);
});

test('result count and empty-state text follow every input', () => {
  const ui = setup();
  ui.input('inexistant');
  assert.equal(ui.count.textContent, '0 guide pour préparer votre séjour');
  assert.equal(ui.empty.hidden, false);
  ui.input('train');
  assert.equal(ui.count.textContent, '2 guides pour préparer votre séjour');
  assert.equal(ui.empty.hidden, true);
  ui.input('aeroport');
  assert.equal(ui.count.textContent, '1 guide pour préparer votre séjour');
});

test('a search value present at script startup is applied immediately', () => {
  const ui = setup({ value: 'train Porto' });
  assert.deepEqual(ui.visible(), ['train']);
  assert.equal(ui.count.textContent, '1 guide pour préparer votre séjour');
});

test('missing search metadata does not break filtering', () => {
  const ui = setup({ entries: [['sans-metadata', 'Portugal', undefined]] });
  ui.input('train');
  assert.deepEqual(ui.visible(), []);
  ui.input('');
  assert.deepEqual(ui.visible(), ['sans-metadata']);
});

test('pages without a search field retain their print action', () => {
  const ui = setup({ hasSearch: false });
  assert.equal(ui.print(), 1);
  assert.equal(ui.print(), 2);
});
