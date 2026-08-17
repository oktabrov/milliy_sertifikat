import {
  tg,
  api,
  bootstrap,
  configureMathKeyboard,
  degradeMathFields,
  mathLiveReady,
  readAnswerField,
} from '/app/static/tg.js';

const OPEN_HINT =
  '(iloji boricha qisqa javob yozing. "ta, nafar, m, litr, so‘m, a=, h=, jami, gradus" ' +
  'kabi so‘zlarni ishlatmang.)';

const state = {
  test: null,
  // Multiple choice only. Open answers are read straight out of the DOM by
  // collectAnswers(), so a MathLive build that does not emit `input` events
  // cannot silently drop a student's work.
  choices: new Map(),
};

/* The single source of truth for what gets submitted. */
function collectAnswers() {
  const answers = {};
  state.choices.forEach((value, key) => {
    answers[key] = value;
  });
  document.querySelectorAll('math-field, input.plain-field').forEach((element) => {
    const key = element.dataset.key;
    if (!key) return;
    const value = readAnswerField(element).trim();
    if (value) answers[key] = value;
  });
  return answers;
}

const el = (id) => document.getElementById(id);

bootstrap();

/* --- Step 1: test code ---------------------------------------------------- */

el('code-submit').addEventListener('click', loadTest);
el('code-input').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') loadTest();
});

async function loadTest() {
  const code = el('code-input').value.trim();
  const error = el('code-error');
  error.textContent = '';

  if (!code) {
    error.textContent = 'Test kodini kiriting.';
    return;
  }

  const button = el('code-submit');
  button.disabled = true;
  try {
    const test = await api(`/api/test/${encodeURIComponent(code)}`);
    if (test.status !== 'open') {
      error.textContent = 'Bu test yopilgan.';
      return;
    }
    if (test.already_submitted) {
      error.textContent = 'Siz bu testga allaqachon javob bergansiz.';
      return;
    }
    state.test = test;
    renderSheet(test);
  } catch (problem) {
    error.textContent = problem.message;
  } finally {
    button.disabled = false;
  }
}

/* --- Step 2: the sheet ---------------------------------------------------- */

function renderSheet(test) {
  el('code-step').classList.add('hidden');
  el('sheet-step').classList.remove('hidden');
  el('progress-bar').classList.remove('hidden');

  el('sheet-title').textContent = `▮ Test №${test.code} – ${test.question_count} ta savol`;

  const subjectRow = el('subject-row');
  const select = el('subject-select');
  if (test.subjects && test.subjects.length) {
    select.innerHTML = test.subjects
      .map((subject) => `<option value="${escapeHtml(subject)}">${escapeHtml(subject)}</option>`)
      .join('');
  } else {
    subjectRow.classList.add('hidden');
  }

  const container = el('questions');
  container.innerHTML = '';
  test.questions.forEach((question) => {
    container.appendChild(
      question.type === 'open' ? buildOpenQuestion(question) : buildChoiceQuestion(question)
    );
  });

  if (!mathLiveReady()) {
    // Give the deferred CDN bundle a moment, then fall back to text inputs.
    setTimeout(() => {
      if (!mathLiveReady()) degradeMathFields(container);
    }, 2500);
  }
  configureMathKeyboard();

  updateProgress();
}

function buildChoiceQuestion(question) {
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
        const key = String(question.number);
        const selected = state.choices.get(key) === letter;

        options.querySelectorAll('.opt').forEach((other) =>
          other.setAttribute('aria-pressed', 'false')
        );

        if (selected) {
          // Tapping the chosen option again clears it.
          state.choices.delete(key);
        } else {
          state.choices.set(key, letter);
          button.setAttribute('aria-pressed', 'true');
        }
        if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
        updateProgress();
      });
      options.appendChild(button);
    });

  card.appendChild(options);
  return card;
}

function buildOpenQuestion(question) {
  const card = document.createElement('div');
  card.className = 'q';

  const label = document.createElement('div');
  label.className = 'q-label';
  label.innerHTML = `${question.number}-savol: <span class="q-hint">${escapeHtml(OPEN_HINT)}</span>`;
  card.appendChild(label);

  const parts = question.parts && question.parts.length ? question.parts : ['a', 'b'];
  parts.forEach((part) => {
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
    // Only to refresh the counter; the value itself is read at submit time.
    field.addEventListener('input', updateProgress);
    field.addEventListener('blur', updateProgress);

    wrapper.appendChild(field);
    row.appendChild(wrapper);
    card.appendChild(row);
  });

  return card;
}

function totalItems(test) {
  return test.questions.reduce(
    (sum, question) =>
      sum + (question.type === 'open' ? (question.parts.length || 2) : 1),
    0
  );
}

function updateProgress() {
  if (!state.test) return;
  const answered = Object.keys(collectAnswers()).length;
  el('progress-count').textContent = `Belgilandi: ${answered} / ${totalItems(state.test)}`;
}

/* --- Step 3: submit ------------------------------------------------------- */

el('submit-btn').addEventListener('click', submitAnswers);

async function submitAnswers() {
  const error = el('submit-error');
  error.textContent = '';

  updateProgress();
  const answers = collectAnswers();
  const answeredCount = Object.keys(answers).length;

  if (answeredCount === 0) {
    error.textContent = 'Kamida bitta javob belgilang.';
    return;
  }

  const unanswered = totalItems(state.test) - answeredCount;
  if (unanswered > 0) {
    const proceed = window.confirm(
      `${unanswered} ta javob belgilanmagan. Baribir yuborilsinmi?`
    );
    if (!proceed) return;
  }

  const button = el('submit-btn');
  button.disabled = true;
  try {
    const payload = {
      code: state.test.code,
      subject: el('subject-select').value || null,
      answers,
    };
    const result = await api('/api/attempt', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    showDone(result);
  } catch (problem) {
    error.textContent = problem.message;
    button.disabled = false;
  }
}

function showDone(result) {
  el('sheet-step').classList.add('hidden');
  el('progress-bar').classList.add('hidden');
  el('done-step').classList.remove('hidden');

  if (result && result.scenarios && result.scenarios.length) {
    const rows = result.scenarios
      .map(
        (scenario) => `
          <tr>
            <td>${escapeHtml(scenario.label_uz)}</td>
            <td>${scenario.ball}</td>
            <td>${scenario.percentile}%</td>
            <td class="grade">${escapeHtml(scenario.grade)}</td>
          </tr>`
      )
      .join('');

    el('result-summary').innerHTML = `
      <p style="margin:0 0 6px">To‘g‘ri javoblar: <b>${result.raw_correct}/${result.total_items}</b></p>
      <table class="result-table">
        <thead><tr><th>Stsenariy</th><th>Ball</th><th>Foiz</th><th>Daraja</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

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
