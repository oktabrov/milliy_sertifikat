import {
  tg,
  api,
  bootstrap,
  configureMathKeyboard,
  degradeMathFields,
  mathLiveReady,
  readAnswerField,
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

/* The full answer key: chosen letters plus whatever is in the math fields. */
function collectKey() {
  const key = {};
  state.choices.forEach((value, name) => {
    key[name] = value;
  });
  document.querySelectorAll('math-field, input.plain-field').forEach((element) => {
    const name = element.dataset.key;
    if (!name) return;
    const value = readAnswerField(element).trim();
    if (value) key[name] = value;
  });
  return key;
}

const el = (id) => document.getElementById(id);

bootstrap();

/* --- Step 1: shape -------------------------------------------------------- */

el('setup-submit').addEventListener('click', buildKeySheet);

function buildKeySheet() {
  const error = el('setup-error');
  error.textContent = '';

  const title = el('title-input').value.trim();
  const mcCount = parseInt(el('mc-count').value, 10) || 0;
  const options = parseInt(el('mc-options').value, 10) || 4;
  const openCount = parseInt(el('open-count').value, 10) || 0;

  if (title.length < 3) {
    error.textContent = 'Test nomini kiriting (kamida 3 ta belgi).';
    return;
  }
  if (mcCount + openCount === 0) {
    error.textContent = 'Kamida bitta savol kerak.';
    return;
  }
  if (mcCount + openCount > 120) {
    error.textContent = 'Savollar soni 120 tadan oshmasligi kerak.';
    return;
  }
  if (options < 2 || options > 6) {
    error.textContent = 'Variantlar soni 2 va 6 orasida bo‘lishi kerak.';
    return;
  }

  state.title = title;
  state.code = el('code-input').value.trim() || null;
  state.subjects = el('subjects-input')
    .value.split(',')
    .map((subject) => subject.trim())
    .filter(Boolean);

  state.questions = [];
  for (let index = 0; index < mcCount; index += 1) {
    state.questions.push({ number: index + 1, type: 'mc', options });
  }
  for (let index = 0; index < openCount; index += 1) {
    state.questions.push({ number: mcCount + index + 1, type: 'open' });
  }

  renderKeySheet();
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

function buildOpenKey(question) {
  const card = document.createElement('div');
  card.className = 'q';

  const label = document.createElement('div');
  label.className = 'q-label';
  label.innerHTML =
    `${question.number}-savol: <span class="q-hint">to‘g‘ri javoblarni yozing ` +
    `(b) bo‘sh qolishi mumkin)</span>`;
  card.appendChild(label);

  ['a', 'b'].forEach((part) => {
    const row = document.createElement('div');
    row.className = 'part';

    const tag = document.createElement('div');
    tag.className = 'part-label';
    tag.textContent = `${part})`;
    row.appendChild(tag);

    const wrapper = document.createElement('div');
    wrapper.className = 'field';

    const field = document.createElement('math-field');
    field.dataset.key = `${question.number}${part}`;
    field.setAttribute('virtual-keyboard-mode', 'onfocus');
    field.addEventListener('input', updateCount);
    field.addEventListener('blur', updateCount);

    wrapper.appendChild(field);
    row.appendChild(wrapper);
    card.appendChild(row);
  });

  return card;
}

/* An open question counts as answered once part a) is filled; b) is optional. */
function missingQuestions(key = collectKey()) {
  return state.questions.filter((question) =>
    question.type === 'mc'
      ? !key[String(question.number)]
      : !key[`${question.number}a`]
  );
}

function updateCount() {
  const missing = missingQuestions().length;
  const total = state.questions.length;
  el('key-count').textContent = `To‘ldirildi: ${total - missing} / ${total}`;
}

/* --- Step 3: save --------------------------------------------------------- */

el('save-btn').addEventListener('click', saveTest);

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
    const parts = {};
    ['a', 'b'].forEach((part) => {
      const value = key[`${question.number}${part}`];
      if (value) parts[part] = value;
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

el('close-btn').addEventListener('click', () => {
  if (tg) tg.close();
  else window.close();
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
  });
}
