/* Shared helpers: Telegram bootstrap, authenticated fetch, MathLive setup. */

export const tg = window.Telegram ? window.Telegram.WebApp : null;

/* --- Auth: two methods, tried in order ------------------------------------ */

/* 1. initData from the Telegram library or URL hash (standard method). */
function initDataFromHash() {
  try {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    return params.get('tgWebAppData') || '';
  } catch (_) {
    return '';
  }
}

function initDataFromSessionStorage() {
  try {
    const raw = window.sessionStorage.getItem('__telegram__initParams');
    if (!raw) return '';
    const params = JSON.parse(raw);
    return (params && params.tgWebAppData) || '';
  } catch (_) {
    return '';
  }
}

export function currentInitData() {
  const fromLibrary = tg && typeof tg.initData === 'string' ? tg.initData : '';
  return fromLibrary || initDataFromHash() || initDataFromSessionStorage();
}

/* 2. Bot-signed token from URL query parameter (fallback). */
function tokenFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get('token') || '';
  } catch (_) {
    return '';
  }
}

/* True when we have ANY auth method available. */
export function hasSession() {
  return Boolean(currentInitData() || tokenFromUrl());
}

/* --- Status badge --------------------------------------------------------- */

function paintStatus() {
  const badge = document.getElementById('session-badge');
  if (!badge) return;
  const initData = Boolean(currentInitData());
  const token = Boolean(tokenFromUrl());
  const session = initData || token;

  const parts = [];
  parts.push(window.Telegram ? 'TG \u2713' : 'TG \u2717');
  parts.push(initData ? 'init \u2713' : 'init \u2717');
  parts.push(token ? 'token \u2713' : 'token \u2717');
  badge.textContent = parts.join(' \u00b7 ');
  badge.classList.toggle('bad', !session);
}

export function startStatusBadge() {
  if (!document.getElementById('session-badge')) {
    const badge = document.createElement('div');
    badge.id = 'session-badge';
    document.body.appendChild(badge);
  }
  paintStatus();
}

/* Surface a script failure as a red banner instead of a silently dead page. */
export function reportFatal(message) {
  if (typeof window.__msFatal === 'function') window.__msFatal(message);
}

/* Warn if no auth is available at all. */
export function warnOutsideTelegram() {
  const notice = document.getElementById('tg-notice');
  if (!notice) return;

  if (hasSession()) {
    notice.classList.remove('visible');
    paintStatus();
    return;
  }

  /* No auth at all. */
  notice.textContent =
    'Sahifa Telegram sessiyasisiz ochildi. ' +
    'Sahifani yopib, bot menyusidagi /ms tugmasini bosing.';
  notice.classList.add('visible');
}

/* Initialise Telegram WebApp UI helpers if the library loaded. */
export function bootstrap() {
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
    if (tg.colorScheme === 'dark') document.body.classList.add('tg-dark');
  } catch (_) {}
}

/* Every API call carries auth: initData (preferred) or token (fallback). */
export async function api(path, options = {}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});

  const initData = currentInitData();
  const token = tokenFromUrl();

  if (initData) {
    headers['Authorization'] = 'tma ' + initData;
  }
  if (token) {
    headers['X-App-Token'] = token;
  }

  const response = await fetch(path, Object.assign({}, options, { headers }));
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }

  if (!response.ok) {
    const message =
      (payload && (payload.error || payload.detail)) ||
      (response.status === 401
        ? 'Avtorizatsiya xatosi. Mini ilovani bot orqali oching.'
        : 'Server xatosi. Qayta urinib ko\u2019ring.');
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return payload;
}

export function configureMathKeyboard() {
  if (!window.mathVirtualKeyboard) return;
  try {
    window.mathVirtualKeyboard.layouts = ['numeric', 'symbols', 'alphabetic', 'greek'];
  } catch (_) {}
}

export function mathLiveReady() {
  return typeof window.customElements !== 'undefined' && !!customElements.get('math-field');
}

export function degradeMathFields(root) {
  root.querySelectorAll('math-field').forEach((field) => {
    const input = document.createElement('input');
    input.type = 'text';
    input.dataset.key = field.dataset.key;
    input.className = 'plain-field';
    input.setAttribute('inputmode', 'text');
    field.replaceWith(input);
  });
}

export function readAnswerField(element) {
  if (!element) return '';
  if (element.tagName === 'MATH-FIELD') return element.getValue('latex') || '';
  return element.value || '';
}

export function writeAnswerField(element, value) {
  if (!element) return;
  if (element.tagName === 'MATH-FIELD') element.setValue(value || '');
  else element.value = value || '';
}