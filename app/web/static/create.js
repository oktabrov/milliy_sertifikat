import {
  tg,
  api,
  bootstrap,
  configureMathKeyboard,
  degradeMathFields,
  mathLiveReady,
  readAnswerField,
  reportFatal,
  startStatusBadge,
  warnOutsideTelegram,
} from '/app/static/tg.js';

const state = {
  title: '',
  subjects: [],
  code: null,
  questions: [], // {number, type, options}
  // Multiple choice only; open answers are read from the DOM at save time so a
  // MathLive build that does not emit `input` events cannot lose them.
  choices: new Map(), // "12" -> "A"
};

/* The paper shape is fixed, matching the Milliy sertifikat format: 35 closed
   questions then 10 open ones. Closed questions carry four options each,
   except questions 33-35 which always have six (A-F). */
const CLOSED_QUESTIONS = 35;
const OPEN_QUESTIONS = 10;
const OPTIONS_PER_QUESTION = 4;
const SIX_OPTION_QUESTIONS = new Set([33, 34, 35]);

/* The full answer key.

   Multiple choice maps to a single letter. Each open part maps to an ARRAY of
   every accepted answer, in the order the author entered them — a student who
   matches any one of them is marked correct. */
function collectKey() {
  const key = {};
  state.choices.forEach((value, name) => {
    key[name] = value;
  });
  document.querySelectorAll('math-field, input.plain-field').forEach((element) => {
    const name = element.dataset.key;
    if (!name) return;
    const value = readAnswerField(element).trim();
    if (!value) return;
    if (!Array.isArray(key[name])) key[name] = [];
    // Same answer typed twice is the author's slip, not two accepted forms.
    if (!key[name].includes(value)) key[name].push(value);
  });
  return key;
}

const el = (id) => document.getElementById(id);

bootstrap();
startStatusBadge();
warnOutsideTelegram();

/* --- Wiring: delegated, registered before anything can throw ---------------
   One listener on document routes clicks by element id. Per-element listeners
   die together with whatever threw during module setup; delegation keeps the
   buttons alive, and a failure becomes a visible banner instead of a silent
   page that "does not respond". */

const actions = {
  'setup-submit': () => buildKeySheet(),
  'save-btn': () => {
    saveTest();
  },
  'close-btn': () => {
    if (tg) tg.close();
    else window.close();
  },
};

document.addEventListener('click', (event) => {
  if (!(event.target instanceof Element)) return;
  const action = event.target.closest('[id]');
  if (action && actions[action.id]) actions[action.id]();
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  const field = event.target instanceof Element ? event.target : null;
  if (field && field.closest('#setup-step') && !field.classList.contains('btn')) {
    buildKeySheet();
  }
});

/* --- Step 1: shape -------------------------------------------------------- */

function buildKeySheet() {
  const error = el('setup-error');
  error.textContent = '';

  const title = el('title-input').value.trim();
  if (title.length < 3) {
    error.textContent = 'Test nomini kiriting (kamida 3 ta belgi).';
    return;
  }

  state.title = title;
  state.code = el('code-input').value.trim() || null;
  state.subjects = el('subjects-input')
    .value.split(',')
    .map((subject) => subject.trim())
    .filter(Boolean);

  state.questions = [];
  for (let index = 0; index < CLOSED_QUESTIONS; index += 1) {
    const number = index + 1;
    const optionCount = SIX_OPTION_QUESTIONS.has(number)
      ? Math.max(OPTIONS_PER_QUESTION, 6)
      : OPTIONS_PER_QUESTION;
    state.questions.push({ number, type: 'mc', options: optionCount });
  }
  for (let index = 0; index < OPEN_QUESTIONS; index += 1) {
    state.questions.push({ number: CLOSED_QUESTIONS + index + 1, type: 'open' });
  }

  try {
    renderKeySheet();
  } catch (problem) {
    reportFatal(problem && problem.message ? problem.message : String(problem));
  }
}

function renderKeySheet() {
  el('setup-step').classList.add('hidden');
  el('key-step').classList.remove('hidden');
  el('key-progress').classList.remove('hidden');

  el('key-title').textContent = `▮ ${state.title} – ${state.questions.length} ta savol`;

  const container = el('key-questions');
  container.innerHTML = '';
  state.questions.forEach((question) => {
    container.appendChild(
      question.type === 'open' ? buildOpenKey(question) : buildChoiceKey(question)
    );
  });

  if (!mathLiveReady()) {
    setTimeout(() => {
      if (!mathLiveReady()) degradeMathFields(container);
    }, 2500);
  }
  configureMathKeyboard();

  updateCount();
}

function buildChoiceKey(question) {
  const card = document.createElement('div');
  card.className = 'q';

  const label = document.createElement('div');
  label.className = 'q-label';
  label.textContent = `${question.number}-savol:`;
  card.appendChild(label);

  const options = document.createElement('div');
  options.className = 'options';

  'ABCDEF'
    .slice(0, question.options)
    .split('')
    .forEach((letter) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'opt';
      button.textContent = letter;
      button.setAttribute('aria-pressed', 'false');
      button.addEventListener('click', () => {
        options.querySelectorAll('.opt').forEach((other) =>
          other.setAttribute('aria-pressed', 'false')
        );
        button.setAttribute('aria-pressed', 'true');
        state.choices.set(String(question.number), letter);
        updateCount();
      });
      options.appendChild(button);
    });

  card.appendChild(options);
  return card;
}

const MAX_ACCEPTED_ANSWERS = 20;

/* One input row. Several rows can share a key: each is another accepted form
   of the same answer. */
function buildAnswerRow(key, { removable }) {
  const row = document.createElement('div');
  row.className = 'answer-row';

  const wrapper = document.createElement('div');
  wrapper.className = 'field';

  const field = document.createElement('math-field');
  field.dataset.key = key;
  field.setAttribute('virtual-keyboard-mode', 'onfocus');
  field.addEventListener('input', updateCount);
  field.addEventListener('blur', updateCount);
  wrapper.appendChild(field);
  row.appendChild(wrapper);

  if (removable) {
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'row-remove';
    remove.textContent = '×';
    remove.title = 'Bu javobni o‘chirish';
    remove.addEventListener('click', () => {
      row.remove();
      updateCount();
    });
    row.appendChild(remove);
  }

  return row;
}

function buildOpenKey(question) {
  const card = document.createElement('div');
  card.className = 'q';

  const label = document.createElement('div');
  label.className = 'q-label';
  label.innerHTML =
    `${question.number}-savol: <span class="q-hint">to‘g‘ri javobni yozing. ` +
    `Bir xil javobning turli ko‘rinishlarini qo‘shishingiz mumkin ` +
    `(masalan 3/4, 0.75) — o‘quvchi shulardan birini yozsa, javob to‘g‘ri ` +
    `hisoblanadi. b) bo‘sh qolishi mumkin.</span>`;
  card.appendChild(label);

  ['a', 'b'].forEach((part) => {
    const key = `${question.number}${part}`;

    const block = document.createElement('div');
    block.className = 'part-block';

    const tag = document.createElement('div');
    tag.className = 'part-label';
    tag.textContent = `${part})`;
    block.appendChild(tag);

    const rows = document.createElement('div');
    rows.className = 'answer-rows';
    // The first row is never removable, so a part always keeps one input.
    rows.appendChild(buildAnswerRow(key, { removable: false }));
    block.appendChild(rows);

    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'add-answer';
    add.textContent = '+ Yana javob qo‘shish';
    add.addEventListener('click', () => {
      if (rows.querySelectorAll('math-field, input.plain-field').length >= MAX_ACCEPTED_ANSWERS) {
        return;
      }
      const row = buildAnswerRow(key, { removable: true });
      rows.appendChild(row);
      const field = row.querySelector('math-field, input.plain-field');
      if (field && field.focus) field.focus();
      updateCount();
    });
    block.appendChild(add);

    card.appendChild(block);
  });

  return card;
}

/* An open question counts as answered once part a) has at least one accepted
   answer; b) is optional, and extra accepted forms are always optional. */
function missingQuestions(key = collectKey()) {
  return state.questions.filter((question) => {
    if (question.type === 'mc') return !key[String(question.number)];
    const accepted = key[`${question.number}a`];
    return !accepted || accepted.length === 0;
  });
}

function updateCount() {
  const missing = missingQuestions().length;
  const total = state.questions.length;
  el('key-count').textContent = `To‘ldirildi: ${total - missing} / ${total}`;
}

/* --- Step 3: save --------------------------------------------------------- */

async function saveTest() {
  const error = el('save-error');
  error.textContent = '';

  const key = collectKey();
  const missing = missingQuestions(key);
  if (missing.length) {
    error.textContent = `To‘ldirilmagan savollar: ${missing
      .slice(0, 8)
      .map((question) => question.number)
      .join(', ')}${missing.length > 8 ? '…' : ''}`;
    return;
  }

  const questions = state.questions.map((question) => {
    if (question.type === 'mc') {
      return {
        number: question.number,
        type: 'mc',
        options: question.options,
        answer: key[String(question.number)],
      };
    }
    // Each part carries every accepted form: {"a": ["3/4", "0.75"]}.
    const parts = {};
    ['a', 'b'].forEach((part) => {
      const accepted = key[`${question.number}${part}`];
      if (accepted && accepted.length) parts[part] = accepted;
    });
    return { number: question.number, type: 'open', parts };
  });

  const button = el('save-btn');
  button.disabled = true;
  try {
    const created = await api('/api/test', {
      method: 'POST',
      body: JSON.stringify({
        title: state.title,
        subjects: state.subjects,
        code: state.code,
        questions,
      }),
    });
    showDone(created);
  } catch (problem) {
    error.textContent = problem.message;
    button.disabled = false;
  }
}

function showDone(created) {
  el('key-step').classList.add('hidden');
  el('key-progress').classList.add('hidden');
  el('done-step').classList.remove('hidden');
  el('done-text').innerHTML =
    `<b>${escapeHtml(created.title)}</b><br />Test kodi: ` +
    `<b style="font-size:20px">${escapeHtml(created.code)}</b><br />` +
    `${created.question_count} ta savol<br /><br />` +
    `Shu kodni o‘quvchilarga yuboring.`;
  if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
  });
}
