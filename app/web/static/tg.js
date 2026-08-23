/* Shared helpers: Telegram bootstrap, authenticated fetch, MathLive setup. */

export const tg = window.Telegram ? window.Telegram.WebApp : null;

/* The session data is attached to the URL as #tgWebAppData=... by Telegram.
   Some clients/networks fail to load telegram-web-app.js, so window.Telegram
   never appears — but the fragment IS still present. Read it directly as a
   reliable fallback that works even when the external script is blocked.

   Additionally, the Telegram library stores initParams in sessionStorage under
   the key '__telegram__initParams'. On some clients/platforms, the hash may
   arrive after the initial load (delivered via postMessage), but sessionStorage
   from a previous successful open persists. */
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

/* Current initData at call time (not at module load). Prefers the library,
   falls back to the URL fragment, then to sessionStorage. */
export function currentInitData() {
  const fromLibrary = tg && typeof tg.initData === 'string' ? tg.initData : '';
  return fromLibrary || initDataFromHash() || initDataFromSessionStorage();
}

/* True when we can see a session — evaluated on demand. */
export function hasSession() {
  return Boolean(currentInitData());
}

/* A one-line, always-on status readout in the corner. When something is wrong
   the user can screenshot it and the cause is immediately obvious — no
   devtools, no guessing. */
function paintStatus() {
  const badge = document.getElementById('session-badge');
  if (!badge) return;
  const libLoaded = Boolean(window.Telegram);
  const hashPresent = /^#.*tgWebAppData=/.test(window.location.hash);
  const session = hasSession();
  badge.textContent =
    (libLoaded ? 'Telegram ✓' : 'Telegram ✗') +
    ' · ' +
    (hashPresent ? 'belgi ✓' : 'belgi ✗') +
    ' · ' +
    (session ? 'sessiya ✓' : 'sessiya ✗');
  badge.classList.toggle('bad', !session);
}

export function startStatusBadge() {
  if (!document.getElementById('session-badge')) {
    const badge = document.createElement('div');
    badge.id = 'session-badge';
    document.body.appendChild(badge);
  }
  paintStatus();
  setTimeout(paintStatus, 500);
  setTimeout(paintStatus, 2000);
}

/* Surface a script failure as a red banner instead of a silently dead page. */
export function reportFatal(message) {
  if (typeof window.__msFatal === 'function') window.__msFatal(message);
}

/* Page opened via a link or a client that didn't deliver initData.
   Check dynamically with retries so we don't mis-classify a slow library load.

   On some Telegram client versions/platforms, initData may arrive
   asynchronously via postMessage from the parent container rather than being
   present in the URL hash at page load. We retry aggressively for up to 10
   seconds and auto-dismiss the warning the moment a session appears. */
export function warnOutsideTelegram() {
  const notice = document.getElementById('tg-notice');
  if (!notice) return;

  /* Once session is found, hide the warning and stop checking. */
  let resolved = false;

  const check = () => {
    if (resolved) return;
    if (hasSession()) {
      resolved = true;
      notice.classList.remove('visible');
      paintStatus();
      return;
    }
    notice.textContent =
      'Telegram sessiyasi yuklanmoqda… Agar bu xabar yo'qolmasa, ' +
      'sahifani yopib, bot menyusidagi «Test tekshirish» yoki ' +
      '«Test yaratish» tugmasini bosing.';
    notice.classList.add('visible');
  };

  /* Check at load, then at increasing intervals up to 10 seconds. */
  check();
  const delays = [100, 300, 500, 1000, 2000, 3000, 5000, 8000, 10000];
  delays.forEach((delay) => setTimeout(check, delay));

  /* After all retries, if still no session, show the final message. */
  setTimeout(() => {
    if (resolved) return;
    paintStatus();
    /* Check one last time — initData may have arrived during the wait. */
    if (hasSession()) {
      resolved = true;
      notice.classList.remove('visible');
      return;
    }
    notice.textContent =
      'Sahifa Telegram sessiyasisiz ochildi — saqlash ishlamaydi. ' +
      'Sahifani yopib, bot menyusidagi «Test tekshirish» yoki ' +
      '«Test yaratish» tugmasini bosing.';
  }, 12000);
}

/* Initialise Telegram WebApp UI helpers if the library loaded. */
export function bootstrap() {
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
    if (tg.colorScheme === 'dark') document.body.classList.add('tg-dark');
  } catch (_) {
    /* Library may throw on some clients; UI works without it. */
  }
}

/* Every API call carries initData; server verifies its HMAC. */
export async function api(path, options = {}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  headers['Authorization'] = `tma ${currentInitData()}`;

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
        : 'Server xatosi. Qayta urinib ko'ring.');
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