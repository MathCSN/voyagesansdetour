// No Google request, preload or consent ping before a persisted opt-in.
const KEY = 'vsd.audience-consent.v1';
const REFUSAL_COOKIE = 'vsd_audience_refused';
const TTL = 180 * 24 * 60 * 60 * 1000;
const ORIGIN = 'https://voyagesansdetour.fr';

export function installAnalytics(window, document, now = Date.now) {
  const config = document.querySelector('[data-vsd-analytics]');
  const id = config?.dataset.measurementId;
  if (!/^G-[A-Z0-9]+$/.test(id || '')) return;
  const disable = `ga-disable-${id}`;
  window[disable] = true;
  // Only reviewed public builds and known canonical pages may collect.
  if (config.dataset.enabled !== 'true' || window.location.origin !== ORIGIN) return;
  let canonical;
  try { canonical = new URL(document.querySelector('link[rel="canonical"]').href); }
  catch { return; }
  if (canonical.origin !== ORIGIN || canonical.search || canonical.hash ||
      canonical.pathname !== window.location.pathname || canonical.pathname === '/404.html') return;
  const panel = document.querySelector('#audience-choice');
  const status = document.querySelector('#audience-status');
  const settings = [...document.querySelectorAll('[data-audience-settings]')];
  const accept = document.querySelector('[data-audience-accept]');
  const refuse = document.querySelector('[data-audience-refuse]');
  if (!panel || !status || !accept || !refuse) return;
  let loaded = false, tag = null, timer = null, returnFocus = null, storageFailed = false;

  function readChoice() {
    try {
      if (hasRefusalCookie()) return {version: 1, choice: 'refused', decidedAt: now()};
      if (storageFailed) return null;
      const raw = window.localStorage.getItem(KEY);
      const value = JSON.parse(raw);
      const age = now() - value.decidedAt;
      if (!(value.version === 1 && ['accepted', 'refused'].includes(value.choice) &&
          Number.isSafeInteger(value.decidedAt) && age >= 0 && age < TTL)) return null;
      // A stored opt-in is unusable if the browser can no longer retain a refusal.
      if (value.choice === 'accepted') {
        window.localStorage.setItem(KEY, raw);
        if (window.localStorage.getItem(KEY) !== raw) return null;
      }
      return value;
    } catch { return null; }
  }
  function hasRefusalCookie() {
    return document.cookie.split(';').some(part => part.trim() === `${REFUSAL_COOKIE}=1`);
  }
  function clearRefusalCookie() {
    document.cookie = `${REFUSAL_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax; Secure`;
    return !hasRefusalCookie();
  }
  function writeChoice(choice) {
    let saved = false;
    try {
      const value = JSON.stringify({version: 1, choice, decidedAt: now()});
      window.localStorage.setItem(KEY, value);
      saved = window.localStorage.getItem(KEY) === value;
    } catch { /* A transient write failure must never leave an old opt-in usable. */ }
    if (choice === 'accepted') {
      try { return saved && clearRefusalCookie(); } catch { return false; }
    }
    if (saved) return true;
    try { window.localStorage.removeItem(KEY); } catch { /* Try independent refusal storage below. */ }
    try {
      document.cookie = `${REFUSAL_COOKIE}=1; Max-Age=${TTL / 1000}; Path=/; SameSite=Lax; Secure`;
      return hasRefusalCookie();
    } catch { return false; }
  }
  function eraseCookies() {
    // New cookies are host-only. Also clear legacy parent-domain GA cookies.
    const names = document.cookie.split(';').map(part => part.trim().split('=')[0])
      .filter(name => /^_ga(?:_|$)/.test(name));
    for (const name of names) for (const domain of ['', '; Domain=voyagesansdetour.fr', '; Domain=.voyagesansdetour.fr']) {
      document.cookie = `${name}=; Max-Age=0; Path=/${domain}; SameSite=Lax; Secure`;
    }
  }
  function stop(reload = true) {
    window[disable] = true;
    if (timer !== null) window.clearTimeout(timer);
    if (tag) tag.remove();
    if (Array.isArray(window.dataLayer)) window.dataLayer.length = 0;
    eraseCookies();
    // Discard the already-executed third-party code; do not emit a denied ping.
    if (loaded && reload) { loaded = false; window.location.reload(); }
  }
  function scheduleExpiry(choice) {
    if (timer !== null) window.clearTimeout(timer);
    timer = window.setTimeout(sync, Math.min(TTL - (now() - choice.decidedAt), 86400000));
  }
  function load(choice) {
    if (loaded) { scheduleExpiry(choice); return; }
    loaded = true;
    window[disable] = false;
    window.dataLayer = [];
    window.gtag = function () {
      if (!window[disable] && readChoice()?.choice === 'accepted') window.dataLayer.push(arguments);
    };
    const gtag = window.gtag;
    const denied = {ad_storage: 'denied', analytics_storage: 'denied',
      ad_user_data: 'denied', ad_personalization: 'denied'};
    gtag('consent', 'default', denied);
    gtag('consent', 'update', {...denied, analytics_storage: 'granted'});
    gtag('set', 'url_passthrough', false);
    gtag('set', 'ads_data_redaction', true);
    // Override the URL/referrer globally, including automatic GA session events.
    const page = {page_location: canonical.href, page_referrer: '', page_title: document.title};
    const privacy = {...page, allow_google_signals: false, allow_ad_personalization_signals: false,
      send_page_view: false, cookie_domain: 'none', cookie_update: false,
      // Never import arbitrary UTM text from the visitor's URL as campaign data.
      campaign_id: '', campaign_source: '', campaign_medium: '', campaign_name: '',
      campaign_term: '', campaign_content: '',
      cookie_expires: Math.floor((TTL - (now() - choice.decidedAt)) / 1000),
      cookie_flags: 'SameSite=Lax;Secure'};
    gtag('set', privacy);
    gtag('js', new Date(now()));
    gtag('config', id, privacy);
    gtag('event', 'page_view', {...page, send_to: id});
    tag = document.createElement('script');
    tag.async = true;
    tag.referrerPolicy = 'no-referrer';
    tag.src = `https://www.googletagmanager.com/gtag/js?id=${id}`;
    document.head.append(tag);
    scheduleExpiry(choice);
  }
  function sync() {
    const choice = readChoice();
    if (choice?.choice === 'accepted') load(choice);
    else stop();
    panel.hidden = choice !== null;
    status.textContent = choice?.choice === 'accepted' ? 'Mesure d’audience autorisée.' :
      choice?.choice === 'refused' ? 'Mesure d’audience refusée.' : 'Aucune mesure d’audience sans votre accord.';
  }
  function choose(choice) {
    const persisted = writeChoice(choice);
    if (!persisted) {
      storageFailed = true;
      stop(false);
      status.textContent = 'Votre navigateur ne permet pas de mémoriser ce choix. La mesure d’audience reste désactivée ; vous pouvez continuer votre visite.';
      return;
    }
    sync();
    returnFocus?.focus();
  }
  for (const button of settings) {
    button.hidden = false;
    button.addEventListener('click', () => {
      returnFocus = button;
      panel.hidden = false;
      refuse.focus();
    });
  }
  accept.addEventListener('click', () => choose('accepted'));
  refuse.addEventListener('click', () => choose('refused'));
  window.addEventListener('storage', event => { if (event.key === KEY || event.key === null) sync(); });
  window.addEventListener('pageshow', sync);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') sync(); });
  sync();
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') installAnalytics(window, document);
