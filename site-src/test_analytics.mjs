import test from 'node:test';
import assert from 'node:assert/strict';
import {installAnalytics} from './dist/analytics.mjs';

const KEY = 'vsd.audience-consent.v1';
const ID = 'G-9EB7Q36YYM';
const NOW = Date.parse('2026-09-27T12:00:00Z');
const TTL = 180 * 86400000;
const receipt = (choice, decidedAt = NOW) => JSON.stringify({version: 1, choice, decidedAt});
function harness({stored, enabled = true, url = 'https://voyagesansdetour.fr/portugal/?email=secret@example.net#private', blockedStorage = false, refusedCookie = false} = {}) {
  let time = NOW, reloads = 0, failOneWrite = false;
  const writes = [], scripts = [], store = new Map(stored ? [[KEY, stored]] : []);
  const cookies = new Map([['_ga','123'],['_ga_9EB7Q36YYM','456'],['essential','keep']]);
  if (refusedCookie) cookies.set('vsd_audience_refused','1');
  const elements = new Map();
  function element() {
    const events = new Map();
    return {hidden: true, dataset: {}, textContent: '', events, focused: false,
      addEventListener(name, callback) { events.set(name, callback); },
      click() { events.get('click')?.(); }, focus() { this.focused = true; }, remove() { this.removed = true; }};
  }
  const cfg = element(); cfg.dataset = {measurementId: ID, enabled: String(enabled)};
  elements.set('[data-vsd-analytics]', cfg);
  elements.set('link[rel="canonical"]', {href: 'https://voyagesansdetour.fr/portugal/'});
  for (const selector of ['#audience-choice', '#audience-status', '[data-audience-accept]', '[data-audience-refuse]', '[data-audience-settings]']) elements.set(selector, element());
  const events = new Map(), documentEvents = new Map(), timers = [];
  const window = {location: Object.assign(new URL(url), {reload() { reloads++; }}),
    localStorage: {getItem(key) { return store.get(key) ?? null; }, setItem(key, value) {
      if (failOneWrite) { failOneWrite = false; throw Error('transient failure'); }
      if (blockedStorage) throw Error('blocked'); store.set(key, value);
    }, removeItem(key) { store.delete(key); }},
    setTimeout(fn, delay) { timers.push({fn, delay}); return timers.length; }, clearTimeout() {},
    addEventListener(name, callback) { events.set(name, callback); }};
  const document = {title: 'Portugal sans voiture', visibilityState: 'visible',
    referrer: 'https://mail.example/inbox?email=secret@example.net#private',
    querySelector(selector) { return elements.get(selector) ?? null; },
    querySelectorAll(selector) { return [elements.get(selector)].filter(Boolean); },
    createElement(name) { assert.equal(name, 'script'); return element(); },
    head: {append(tag) { scripts.push(tag); }},
    addEventListener(name, callback) { documentEvents.set(name, callback); },
    get cookie() { return [...cookies].map(([key,value]) => `${key}=${value}`).join('; '); },
    set cookie(value) {
      writes.push(value);
      const [key,contents] = value.split(';')[0].split('=');
      if (value.includes('Max-Age=0;')) cookies.delete(key); else cookies.set(key,contents);
    }};
  return {window, document, store, scripts, writes, cookies, elements, events, timers, documentEvents,
    start() { installAnalytics(window, document, () => time); },
    advance(value) { time += value; }, get reloads() { return reloads; },
    failNextWrite() { failOneWrite = true; },
    click(selector) { elements.get(selector).click(); },
    commands() { return (window.dataLayer || []).map(args => [...args]); }};
}

test('first visit and refusal make no Google request or dataLayer, and retain the same refusal', () => {
  const h = harness(); h.start();
  assert.equal(h.scripts.length, 0); assert.equal(h.window.dataLayer, undefined);
  assert.equal(h.elements.get('#audience-choice').hidden, false);
  h.click('[data-audience-refuse]');
  const saved = h.store.get(KEY);
  assert.equal(JSON.parse(saved).choice, 'refused');
  assert.equal(h.scripts.length, 0); assert.equal(h.window.gtag, undefined);
  const next = harness({stored: saved}); next.start();
  assert.equal(next.scripts.length, 0); assert.equal(next.elements.get('#audience-choice').hidden, true);
  assert.equal(next.store.get(KEY), saved);
});

test('acceptance loads once, with only canonical URL and advertising disabled', () => {
  const h = harness(); h.start(); h.click('[data-audience-accept]');
  assert.equal(h.scripts.length, 1);
  assert.equal(h.scripts[0].src, `https://www.googletagmanager.com/gtag/js?id=${ID}`);
  assert.equal(h.scripts[0].referrerPolicy, 'no-referrer');
  const commands = h.commands(), config = commands.find(c => c[0] === 'config')[2];
  assert.equal(config.page_location, 'https://voyagesansdetour.fr/portugal/');
  assert.equal(config.page_referrer, ''); assert.equal(config.send_page_view, false);
  assert.equal(config.allow_google_signals, false); assert.equal(config.allow_ad_personalization_signals, false);
  assert.equal(config.cookie_domain, 'none'); assert.equal(config.cookie_update, false);
  assert.ok(['campaign_id','campaign_source','campaign_medium','campaign_name','campaign_term','campaign_content']
    .every(key => config[key] === ''));
  assert.equal(config.cookie_expires, TTL / 1000);
  assert.equal(commands.filter(c => c[0] === 'event').length, 1);
  assert.equal(commands.find(c => c[0] === 'event')[1], 'page_view');
  assert.ok(!JSON.stringify(commands).includes('secret'));
  assert.ok(!JSON.stringify(commands).includes('private'));
  const consent = commands.filter(c => c[0] === 'consent');
  assert.equal(consent[0][2].analytics_storage, 'denied');
  assert.equal(consent[1][2].analytics_storage, 'granted');
  assert.ok(consent.every(c => ['ad_storage','ad_user_data','ad_personalization'].every(k => c[2][k] === 'denied')));
  h.events.get('pageshow')(); h.click('[data-audience-accept]');
  assert.equal(h.scripts.length, 1);
  assert.equal(h.commands().filter(c => c[0] === 'event').length, 1);
});

test('withdrawal disables first, clears only GA cookies, reloads and never sends a denied ping', () => {
  const h = harness({stored: receipt('accepted')}); h.start();
  h.click('[data-audience-settings]');
  assert.equal(h.elements.get('[data-audience-refuse]').focused, true);
  h.click('[data-audience-refuse]');
  assert.equal(h.window[`ga-disable-${ID}`], true); assert.equal(h.reloads, 1);
  assert.equal(h.scripts[0].removed, true); assert.equal(h.commands().length, 0);
  assert.ok(h.writes.some(c => c.startsWith('_ga=')));
  assert.ok(h.writes.some(c => c.startsWith('_ga_9EB7Q36YYM=')));
  assert.ok(h.writes.every(c => !c.startsWith('essential=')));
  h.window.gtag('event', 'should_not_send'); assert.equal(h.commands().length, 0);
  const next = harness({stored: h.store.get(KEY)}); next.start(); assert.equal(next.scripts.length, 0);
});

test('expiry, corrupt receipt and future consent all fail closed', () => {
  for (const stored of [receipt('accepted', NOW - TTL), receipt('accepted', NOW + 1), '{broken', receipt('other')]) {
    const h = harness({stored}); h.start(); assert.equal(h.scripts.length, 0);
    assert.equal(h.window[`ga-disable-${ID}`], true);
  }
  const h = harness({stored: receipt('accepted', NOW - TTL + 500)}); h.start();
  assert.equal(h.timers[0].delay, 500);
  h.advance(501); h.timers[0].fn();
  assert.equal(h.window[`ga-disable-${ID}`], true); assert.equal(h.reloads, 1);
});

test('cross-tab refusal and back-forward cache restoration stop collection', () => {
  const h = harness({stored: receipt('accepted')}); h.start();
  h.store.set(KEY, receipt('refused')); h.events.get('storage')({key: KEY});
  assert.equal(h.window[`ga-disable-${ID}`], true); assert.equal(h.reloads, 1);
  h.events.get('pageshow')(); assert.equal(h.scripts.length, 1);
});

test('unavailable storage cannot use a stale opt-in or start after a click', () => {
  for (const stored of [undefined, receipt('accepted')]) {
    const h = harness({stored, blockedStorage: true}); h.start(); h.click('[data-audience-accept]');
    assert.equal(h.scripts.length, 0); assert.equal(h.window[`ga-disable-${ID}`], true);
    assert.match(h.elements.get('#audience-status').textContent, /reste désactivée/);
  }
});

test('failed refusal write invalidates old opt-in and persists a refusal fallback across navigation', () => {
  const h = harness({stored: receipt('accepted')}); h.start(); h.failNextWrite();
  h.click('[data-audience-refuse]');
  assert.equal(h.window[`ga-disable-${ID}`], true);
  assert.equal(h.store.has(KEY), false);
  assert.equal(h.cookies.get('vsd_audience_refused'), '1');
  const next = harness({stored: h.store.get(KEY), refusedCookie: true}); next.start();
  assert.equal(next.scripts.length, 0);
  assert.equal(next.elements.get('#audience-choice').hidden, true);
  next.click('[data-audience-settings]'); next.click('[data-audience-accept]');
  assert.equal(next.cookies.has('vsd_audience_refused'), false);
  assert.equal(next.scripts.length, 1);
});

test('unverified config, previews and unknown routes never collect even with consent', () => {
  for (const options of [{enabled: false}, {url:'http://localhost:8000/portugal/'},
    {url:'https://voyagesansdetour.fr/unknown-secret@example.net/'}, {url:'https://voyagesansdetour.fr/404.html'}]) {
    const h = harness({...options, stored: receipt('accepted')}); h.start(); assert.equal(h.scripts.length, 0);
  }
});
