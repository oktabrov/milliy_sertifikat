/* Shared helpers: Telegram bootstrap, authenticated fetch, MathLive setup. */

export const tg = window.Telegram ? window.Telegram.WebApp : null;

/* True only when the page was really opened by Telegram: initData exists just
   once, at open time, and every API call is verified against it. */
export const hasInitData = Boolean(tg && tg.initData);

/* Surface a script failure as a red banner instead of a silently dead page.
   The inline bootstrap in each HTML file defines the banner plumbing before
   any module runs, so this still works when the module itself is what broke. */
export function reportFatal(message) {
  if (typeof window.__msFatal === 'function') window.__msFatal(message);
}

/* A page opened straight from a browser has no initData, so saving can never
   succeed. Say so at the top instead of after the whole form is filled. */
export function warnOutsideTelegram() {
  const notice = document.getElementById('tg-notice');
  if (hasInitData || !notice) return;
  notice.textContent =
    'Sahifa botdan tashqarida ochilgan — saqlash ishlamaydi. ' +
    'Ilovani botdagi tegishli tugma orqali oching.';
  notice.classList.add('visible');
}

export function bootstrap() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  if (tg.colorScheme === 'dark') document.body.classList.add('tg-dark');
}

/* Every API call carries the initData string Telegram gave the page; the
   server re-derives its HMAC and refuses anything it cannot verify. */
export async function api(path, options = {}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  const initData = tg && tg.initData ? tg.initData : '';
  headers['Authorization'] = `tma ${initData}`;

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

/* The four tabs match the keyboard in the reference bot: 123, symbols, abc,
   greek. MathLive ships all four, so we only need to pin the order. */
export function configureMathKeyboard() {
  if (!window.mathVirtualKeyboard) return;
  try {
    window.mathVirtualKeyboard.layouts = ['numeric', 'symbols', 'alphabetic', 'greek'];
  } catch (_) {
    /* Older MathLive builds expose a different API; the default layout is fine. */
  }
}

export function mathLiveReady() {
  return typeof window.customElements !== 'undefined' && !!customElements.get('math-field');
}

/* If the MathLive bundle fails to load the sheet must still be answerable, so
   every math-field degrades to a plain text input carrying the same name. */
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
