/* Shared helpers: Telegram bootstrap, authenticated fetch, MathLive setup. */

export const tg = window.Telegram ? window.Telegram.WebApp : null;

/* The session data is attached to the URL as #tgWebAppData=... by Telegram.
   Some clients/networks fail to load telegram-web-app.js, so window.Telegram
   never appears — but the fragment IS still present. Read it directly as a
   reliable fallback that works even when the external script is blocked. */
function initDataFromHash() {
  try {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    return params.get('tgWebAppData') || '';
  } catch (_) {
    return '';
  }
}

/* Current initData at call time (not at module load). Prefers the library,
   falls back to the URL fragment. */
export function currentInitData() {
  const fromLibrary = tg && typeof tg.initData === 'string' ? tg.initData : '';
  return fromLibrary || initDataFromHash();
}

/* True when we can see a session — evaluated on demand. */
export function hasSession() {
  return Boolean(currentInitData());
}

/* Surface a script failure as a red banner instead of a silently dead page. */
export function reportFatal(message) {
  if (typeof window.__msFatal === 'function') window.__msFatal(message);
}

/* Page opened via a link or a client that didn't deliver initData.
   Check dynamically with retries so we don't mis-classify a slow library load. */
export function warnOutsideTelegram() {
  const notice = document.getElementById('tg-notice');
  if (!notice) return;

  const check = () => {
    if (hasSession()) return;
    const libLoaded = Boolean(window.Telegram);
    const hashPresent = /^#.*tgWebAppData=/.test(window.location.hash);
    notice.textContent =
      'Sahifa Telegram sessiyasisiz ochildi — saqlash ishlamaydi. ' +
      'Sahifani yopib, bot menyusidagi «Test tekshirish» yoki ' +
      '«Test yaratish» tugmasini bosing. ' +
      `(texnik: js=${libLoaded ? 'bor' : 'yo‘q'}, belgi=${hashPresent ? 'bor' : 'yo‘q'})`;
    notice.classList.add('visible');
  };

  check();
  setTimeout(check, 500);
  setTimeout(check, 2000);
  setTimeout(check, 5000);
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
        : 'Server xatosi. Qayta urinib ko‘ring.');
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