/* mtb — веб-интерфейс. Без зависимостей и сборки. */
'use strict';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const TYPE_LABEL = { scheduled: 'По расписанию', manual: 'Ручной', current: 'Текущий' };
const MODE_LABEL = { snapshot: 'снимки', git: 'git-история', plain: 'только текущее' };
const TRANSPORT_LABEL = { sftp: 'API + SFTP', api: 'только API', ssh: 'только SSH' };
const ICON = {
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4M10 13H8M16 17H8M16 13h-2"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  restore: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  trash: '<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  drive: '<path d="M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11zM6 16h.01M10 16h.01"/>',
  loader: '<path d="M21 12a9 9 0 1 1-6.22-8.56"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  play: '<path d="m6 3 14 9-14 9V3z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
};
const icon = (name, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24">${ICON[name]}</svg>`;

const state = {
  me: null, page: null, backups: [], types: [], loading: true,
  filters: { search: '', device: '', type: '', from: '', to: '' },
  selected: new Set(), confirm: null,
};

/* ================================================================== API */

class HttpError extends Error { constructor(msg, status) { super(msg); this.status = status; } }

async function api(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-Requested-With'] = 'mtb';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { method, headers, credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body) });
  let data = null;
  try { data = await res.json(); } catch { /* пустой ответ */ }
  if (res.status === 401 && !path.startsWith('/api/auth/')) { showAuth(); throw new HttpError('Требуется вход', 401); }
  if (!res.ok) throw new HttpError((data && data.error) || `HTTP ${res.status}`, res.status);
  return data;
}

/* ================================================================== утилиты */

const fmtDate = (v, withYear = true) => {
  if (v === null || v === undefined) return '—';
  const d = typeof v === 'number' ? new Date(v * 1000) : new Date(v);
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', ...(withYear ? { year: 'numeric' } : {}),
    hour: '2-digit', minute: '2-digit', ...(state.me?.timezone ? { timeZone: state.me.timezone } : {}) });
};
const fmtBytes = (n) => !n ? '—' : n >= 1048576 ? `${(n / 1048576).toFixed(1)} МБ` : n >= 1024 ? `${(n / 1024).toFixed(1)} КБ` : `${n} Б`;
const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? few : many;
};
const isAdmin = () => state.me?.role === 'admin';

let toastTimer;
function toast(text, error = false) {
  const t = $('toast'); t.textContent = text; t.classList.remove('hidden'); t.classList.toggle('toast-error', error);
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add('hidden'), error ? 8000 : 4500);
}

function genPassword(len = 16) {
  const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789-_';
  const buf = new Uint32Array(len); crypto.getRandomValues(buf);
  return Array.from(buf, (x) => abc[x % abc.length]).join('');
}

function formValues(root) {
  const o = {};
  root.querySelectorAll('[name]').forEach((el) => {
    if (el.type === 'radio') { if (el.checked) o[el.name] = el.value; }
    else if (el.type === 'checkbox') o[el.name] = el.checked;
    else if (el.type === 'number') o[el.name] = el.value === '' ? null : Number(el.value);
    else o[el.name] = el.value;
  });
  return o;
}

async function withBusy(btn, label, fn) {
  const html = btn.innerHTML; btn.disabled = true; btn.innerHTML = `${icon('loader', 'i-sm spin')} ${esc(label)}`;
  try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = html; }
}

/* ================================================================== модальное окно */

function openModal({ title, actions = '', body, narrow = false, wide = false }) {
  $('modal-title').innerHTML = title;
  $('modal-actions').innerHTML = actions;
  $('modal-body').innerHTML = body;
  const m = $('modal').querySelector('.modal');
  m.classList.toggle('narrow', narrow); m.classList.toggle('medium', !narrow && !wide);
  $('modal').classList.remove('hidden');
  state.modalHandler = null;
}
function closeModal() { $('modal').classList.add('hidden'); $('modal-body').innerHTML = ''; state.modalHandler = null; }
const loadingBody = `<div class="loading">${icon('loader', 'spin')} Загрузка…</div>`;
const errorBody = (msg) => `<div class="alert alert-error">${esc(msg)}</div>`;

/* ================================================================== вход */

const authState = { mode: 'login', username: '', needCurrent: false };

async function showAuth() {
  $('shell').classList.add('hidden'); $('auth').classList.remove('hidden'); closeModal();
  let st = { first_run: false };
  try { st = await api('/api/auth/state'); } catch { /* сервер недоступен */ }
  if (st.authenticated) return start();
  if (st.first_run) setAuthMode('setup', st.first_user, false, true);
  else setAuthMode('login');
}

function setAuthMode(mode, username = '', needCurrent = false, firstRun = false) {
  Object.assign(authState, { mode, username, needCurrent });
  const setup = mode === 'setup';
  $('f-pass-wrap').classList.toggle('hidden', setup);
  $('f-current-wrap').classList.toggle('hidden', !(setup && needCurrent));
  $('f-new-wrap').classList.toggle('hidden', !setup);
  $('f-confirm-wrap').classList.toggle('hidden', !setup);
  $('pw-rules').classList.toggle('hidden', !setup);
  $('auth-back').classList.toggle('hidden', !setup || firstRun);
  $('auth-user').readOnly = setup;
  if (username) $('auth-user').value = username;
  $('auth-submit').textContent = setup ? 'Сохранить пароль и войти' : 'Войти';
  $('auth-error').classList.add('hidden');
  $('auth-hint').textContent = !setup ? '' : firstRun
    ? 'Первый запуск. Придумайте пароль администратора — он понадобится для входа.'
    : needCurrent ? 'Администратор выдал временный пароль. Введите его и придумайте свой.'
      : 'Пароль ещё не задан. Придумайте пароль для входа.';
  for (const id of ['auth-pass', 'auth-current', 'auth-new', 'auth-confirm']) $(id).value = '';
  updateRules();
  (setup ? (needCurrent ? $('auth-current') : $('auth-new')) : ($('auth-user').value ? $('auth-pass') : $('auth-user'))).focus();
}

function updateRules() {
  const pw = $('auth-new').value, cf = $('auth-confirm').value, user = $('auth-user').value;
  const rules = { len: pw.length >= 10, match: pw !== '' && pw === cf, user: pw !== '' && pw.toLowerCase() !== user.toLowerCase() };
  for (const li of $('pw-rules').children) {
    const ok = rules[li.dataset.rule];
    li.classList.toggle('ok', ok); li.classList.toggle('bad', !ok && pw !== '' && (li.dataset.rule !== 'match' || cf !== ''));
  }
  return Object.values(rules).every(Boolean);
}

async function submitAuth(e) {
  e.preventDefault();
  const err = $('auth-error'); err.classList.add('hidden');
  const btn = $('auth-submit');
  try {
    if (authState.mode === 'login') {
      const r = await withBusy(btn, 'Вход…', () => api('/api/auth/login', { method: 'POST',
        body: { username: $('auth-user').value.trim(), password: $('auth-pass').value } }));
      if (r.setup) return setAuthMode('setup', r.username, r.need_current);
    } else {
      if (!updateRules()) throw new Error('Пароль не соответствует требованиям');
      await withBusy(btn, 'Сохранение…', () => api('/api/auth/setup', { method: 'POST', body: {
        username: authState.username, current: $('auth-current').value,
        password: $('auth-new').value, confirm: $('auth-confirm').value } }));
    }
    start();
  } catch (ex) { err.textContent = ex.message; err.classList.remove('hidden'); }
}

async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* всё равно выходим */ }
  state.me = null; showAuth();
}

function changePassword() {
  openModal({ title: '<h3>Смена пароля</h3>', narrow: true, body: `
    <form class="stack" id="pw-form">
      <label>Текущий пароль <input class="input" type="password" name="current" autocomplete="current-password" required></label>
      <label>Новый пароль <input class="input" type="password" name="password" autocomplete="new-password" minlength="10" required></label>
      <label>Подтверждение <input class="input" type="password" name="confirm" autocomplete="new-password" required></label>
      <p class="hint">Не короче 10 символов. Остальные сессии будут завершены.</p>
      <div class="alert alert-error hidden" id="pw-error"></div>
      <div class="row gap dialog-actions"><button type="button" class="btn" data-act="modal-close">Отмена</button>
      <button class="btn btn-primary">Сохранить</button></div>
    </form>` });
  $('pw-form').onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api('/api/me/password', { method: 'POST', body: formValues(e.target) });
      closeModal(); toast('Пароль изменён');
    } catch (ex) { $('pw-error').textContent = ex.message; $('pw-error').classList.remove('hidden'); }
  };
}

/* ================================================================== оболочка */

async function start() {
  try { state.me = await api('/api/me'); } catch { return; }
  const me = state.me;
  $('auth').classList.add('hidden'); $('shell').classList.remove('hidden');
  document.body.classList.toggle('is-admin', isAdmin());
  $('version').textContent = me.version;
  $('user-btn').textContent = `${me.user}${isAdmin() ? '' : ' · просмотр'} ▾`;
  renderBanners();
  route();
}

function renderBanners() {
  const me = state.me, out = [];
  if (!me.configured.length) out.push(isAdmin()
    ? 'Устройств пока нет. <a href="#/devices">Добавьте первое устройство</a>.'
    : 'Устройств пока нет — их добавляет администратор.');
  if (isAdmin() && !me.passphrase_set) out.push('Не задан пароль шифрования бэкапов — без него .backup и сертификаты не создаются. <a href="#/settings">Настройки → Хранение</a>.');
  $('banners').innerHTML = out.map((t) => `<div class="banner">${t}</div>`).join('');
}

const PAGES = { backups: loadBackups, devices: loadDevices, runs: loadRuns, settings: loadSettings, users: loadUsers, audit: loadAudit };
const ADMIN_PAGES = new Set(['settings', 'users', 'audit']);

function route() {
  let page = (location.hash.match(/^#\/(\w+)/) || [])[1] || 'backups';
  if (!PAGES[page] || (ADMIN_PAGES.has(page) && !isAdmin())) page = 'backups';
  state.page = page;
  for (const a of $('nav').children) a.classList.toggle('on', a.dataset.page === page);
  for (const v of document.querySelectorAll('.view')) v.classList.toggle('on', v.id === `page-${page}`);
  clearTimeout(state.runsTimer);
  PAGES[page]();
}

/* ================================================================== бэкапы */

async function loadBackups() {
  const me = state.me;
  $('f-device').innerHTML = '<option value="">Все устройства</option>' +
    me.devices.map((d) => `<option value="${esc(d)}"${d === state.filters.device ? ' selected' : ''}>${esc(d)}</option>`).join('');
  $('create-device').innerHTML = '<option value="">Выберите устройство…</option>' +
    me.configured.map((d) => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
  const q = new URLSearchParams(Object.entries(state.filters).filter(([, v]) => v));
  try {
    const [list, types] = await Promise.all([api(`/api/backups?${q}`), api('/api/backups/types')]);
    state.backups = list; state.types = types; state.loading = false;
    const ids = new Set(list.map((b) => b.id));
    for (const id of [...state.selected]) if (!ids.has(id)) state.selected.delete(id);
  } catch (e) { state.loading = false; if (e.status !== 401) toast(e.message, true); }
  renderBackups();
}

function renderBackups() {
  const typeSel = $('f-type'), cur = state.filters.type;
  typeSel.innerHTML = '<option value="">Все типы</option>' + state.types.map((t) =>
    `<option value="${esc(t.type)}"${t.type === cur ? ' selected' : ''}>${esc(TYPE_LABEL[t.type] || t.type)} (${t.count})</option>`).join('');
  $('f-clear').classList.toggle('hidden', !Object.values(state.filters).some(Boolean));
  renderSelbar(); renderList();
}

function comparePair() {
  if (state.selected.size !== 2) return null;
  const [a, b] = [...state.selected].map((id) => state.backups.find((x) => x.id === id));
  if (!a || !b) return null;
  return new Date(a.created_at) <= new Date(b.created_at) ? [a.id, b.id] : [b.id, a.id];
}

function renderSelbar() {
  const n = state.selected.size;
  $('selbar').classList.toggle('hidden', n === 0);
  $('sel-count').textContent = `Выбрано: ${n}`;
  const pair = comparePair();
  $('sel-compare').disabled = !pair;
  $('sel-compare').title = pair ? 'Сравнить два выбранных бэкапа' : 'Выберите ровно два бэкапа';
  const chosen = state.backups.filter((b) => state.selected.has(b.id));
  const deletable = chosen.filter((b) => b.deletable).length, protectedN = chosen.length - deletable;
  $('sel-delete').classList.toggle('hidden', !(isAdmin() && deletable));
  $('sel-delete').querySelector('span').textContent = `Удалить ${deletable}`;
  $('sel-hint').classList.toggle('hidden', !(isAdmin() && protectedN));
  $('sel-hint').textContent = protectedN ? `${protectedN} ${plural(protectedN, 'бэкап', 'бэкапа', 'бэкапов')} из истории git удалить нельзя` : '';
}

function actionCell(b) {
  const c = state.confirm;
  let html = `<button class="icon-btn" data-act="view" title="Просмотр">${icon('file', 'i-sm')}</button>`;
  html += `<a class="icon-btn" href="/api/backups/${b.id}/download" title="Скачать" download>${icon('download', 'i-sm')}</a>`;
  if (isAdmin() && state.me.restore) {
    html += c && c.id === b.id && c.action === 'restore'
      ? `<span class="confirm"><button class="yes warn" data-act="restore-yes">Восстановить?</button><button class="link" data-act="cancel">✕</button></span>`
      : `<button class="icon-btn warn" data-act="restore" title="Восстановить (/import)">${icon('restore', 'i-sm')}</button>`;
  }
  if (isAdmin() && b.deletable) {
    html += c && c.id === b.id && c.action === 'delete'
      ? `<span class="confirm"><button class="yes" data-act="delete-yes">Удалить?</button><button class="link" data-act="cancel">✕</button></span>`
      : `<button class="icon-btn danger" data-act="delete" title="Удалить">${icon('trash', 'i-sm')}</button>`;
  }
  return `<div class="row gap-sm">${html}</div>`;
}

function renderList() {
  const list = $('list');
  $('total').textContent = state.backups.length ? `(${state.backups.length} всего)` : '';
  if (state.loading) { list.innerHTML = '<div class="card loading">Загрузка…</div>'; return; }
  if (!state.backups.length) {
    const filtered = Object.values(state.filters).some(Boolean);
    list.innerHTML = `<div class="card empty">${icon('drive')}
      <strong>${filtered ? 'Нет бэкапов, подходящих под фильтры' : 'Бэкапов пока нет'}</strong>
      <span class="muted small">${filtered ? 'Расширьте диапазон дат или сбросьте фильтр.' : 'Они появятся после первого прогона по расписанию или ручного бэкапа.'}</span>
      ${filtered ? '<button class="btn btn-sm" data-act="clear-filters">Сбросить фильтры</button>' : ''}</div>`;
    return;
  }
  const allSel = state.backups.every((b) => state.selected.has(b.id));
  const rows = state.backups.map((b) => `
    <tr data-id="${esc(b.id)}" class="${state.selected.has(b.id) ? 'sel' : ''}" title="Нажмите для просмотра">
      <td class="chk" data-stop><input type="checkbox" data-act="toggle" ${state.selected.has(b.id) ? 'checked' : ''} aria-label="Выбрать"></td>
      <td class="dev">${esc(b.device)}</td>
      <td><span class="badge ${esc(b.type)}">${esc(TYPE_LABEL[b.type] || b.type)}</span></td>
      <td class="num">${fmtBytes(b.size)}</td>
      <td class="date">${fmtDate(b.created_at)}</td>
      <td class="notes">${esc(b.notes)}</td>
      <td data-stop>${actionCell(b)}</td>
    </tr>`).join('');
  list.innerHTML = `<div class="card table-wrap"><table>
    <thead><tr><th class="chk"><input type="checkbox" data-act="toggle-all" ${allSel ? 'checked' : ''} aria-label="Выбрать все"></th>
      <th>Устройство</th><th>Тип</th><th>Размер</th><th>Создан</th><th>Заметка</th><th class="col-actions">Действия</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

/* ---- дифф (Myers) */

function diffLines(oldText, newText) {
  const a = oldText.split('\n'), b = newText.split('\n');
  let pre = 0;
  while (pre < a.length && pre < b.length && a[pre] === b[pre]) pre++;
  let ea = a.length, eb = b.length;
  while (ea > pre && eb > pre && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
  const mid = myers(a.slice(pre, ea), b.slice(pre, eb));
  const rows = [];
  for (let i = 0; i < pre; i++) rows.push({ t: 'ctx', s: a[i] });
  rows.push(...mid);
  for (let i = ea; i < a.length; i++) rows.push({ t: 'ctx', s: a[i] });
  return rows;
}

function myers(a, b) {
  const n = a.length, m = b.length, max = n + m, off = max + 1;
  if (!n) return b.map((s) => ({ t: 'add', s }));
  if (!m) return a.map((s) => ({ t: 'del', s }));
  const LIMIT = 4000;
  const v = new Int32Array(2 * max + 3);
  const trace = [];
  for (let d = 0; d <= Math.min(max, LIMIT); d++) {
    trace.push(d === 0 ? null : v.slice(off - (d - 1), off + d));
    for (let k = -d; k <= d; k += 2) {
      let x = (k === -d || (k !== d && v[off + k - 1] < v[off + k + 1])) ? v[off + k + 1] : v[off + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) { x++; y++; }
      v[off + k] = x;
      if (x >= n && y >= m) return backtrack(trace, a, b);
    }
  }
  return [...a.map((s) => ({ t: 'del', s })), ...b.map((s) => ({ t: 'add', s }))];
}

function backtrack(trace, a, b) {
  const rows = [];
  let x = a.length, y = b.length;
  const get = (d, k) => (d === 0 ? 0 : trace[d][k + d - 1]);
  for (let d = trace.length - 1; d >= 0; d--) {
    const k = x - y;
    const prevK = (k === -d || (k !== d && get(d, k - 1) < get(d, k + 1))) ? k + 1 : k - 1;
    const prevX = get(d, prevK), prevY = prevX - prevK;
    while (x > prevX && y > prevY) { rows.push({ t: 'ctx', s: a[x - 1] }); x--; y--; }
    if (d > 0) {
      if (x === prevX) { rows.push({ t: 'add', s: b[y - 1] }); y--; }
      else { rows.push({ t: 'del', s: a[x - 1] }); x--; }
    }
  }
  return rows.reverse();
}

function renderDiff(rows, full) {
  const CTX = 3, keep = new Uint8Array(rows.length);
  if (full) keep.fill(1);
  else rows.forEach((r, i) => { if (r.t !== 'ctx') for (let j = Math.max(0, i - CTX); j <= Math.min(rows.length - 1, i + CTX); j++) keep[j] = 1; });
  const out = []; let hidden = 0;
  const flush = () => { if (hidden) { out.push(`<div class="gap" data-act="diff-full">⋯ ${hidden} ${plural(hidden, 'строка', 'строки', 'строк')} без изменений ⋯</div>`); hidden = 0; } };
  rows.forEach((r, i) => {
    if (!keep[i]) { hidden++; return; }
    flush();
    out.push(`<div class="${r.t}">${r.t === 'add' ? '+' : r.t === 'del' ? '−' : ' '} ${esc(r.s)}</div>`);
  });
  flush();
  return `<pre class="code diff">${out.join('')}</pre>`;
}

async function viewBackup(id) {
  openModal({ title: '<h3>Бэкап</h3>', body: loadingBody, wide: true });
  try {
    const d = await api(`/api/backups/${id}/content`);
    const other = d.files.filter((f) => f.path !== 'config.rsc');
    openModal({ wide: true,
      title: `<h3>${esc(d.device)}</h3><div class="small mono muted break">${esc(d.filename)}</div>
        <div class="small muted">${fmtDate(d.created_at)} · ${esc(TYPE_LABEL[d.type] || d.type)}${d.notes ? ' · ' + esc(d.notes) : ''}</div>`,
      actions: `<a class="icon-btn" href="/api/backups/${d.id}/download" download title="Скачать config.rsc">${icon('download')}</a>`,
      body: (other.length ? `<div class="files">${other.map((f) =>
        `<a class="file-chip" href="/api/backups/${d.id}/download?file=${encodeURIComponent(f.path)}" download>${icon('download', 'i-sm')}${esc(f.path)} <span class="muted">${fmtBytes(f.size)}</span></a>`).join('')}</div>` : '')
        + (d.truncated ? '<div class="alert alert-error">Файл больше 2 МБ — показано начало.</div>' : '')
        + `<pre class="code">${esc(d.content)}</pre>`,
    });
  } catch (e) { openModal({ title: '<h3>Бэкап</h3>', body: errorBody(e.message) }); }
}

async function compareBackups([a, b]) {
  openModal({ title: '<h3>Сравнение бэкапов</h3>', body: loadingBody, wide: true });
  try {
    const d = await api(`/api/backups/${a}/diff/${b}`);
    const rows = diffLines(d.from.text, d.to.text);
    const added = rows.filter((r) => r.t === 'add').length, removed = rows.filter((r) => r.t === 'del').length;
    const draw = (full) => {
      openModal({ wide: true,
        title: `<h3>Сравнение бэкапов</h3><div class="small mono muted break">${esc(d.from.filename)} → ${esc(d.to.filename)}</div>
          <div class="small"><span class="plus">+${added}</span> <span class="minus">−${removed}</span>
          <span class="muted"> · ${fmtDate(d.from.created_at, false)} → ${fmtDate(d.to.created_at, false)}</span></div>`,
        actions: added + removed ? `<div class="seg"><button data-act="diff-changes" class="${full ? '' : 'on'}">Изменения</button><button data-act="diff-full" class="${full ? 'on' : ''}">Весь файл</button></div>` : '',
        body: added + removed === 0 ? '<p class="muted identical">Эти два бэкапа идентичны.</p>' : renderDiff(rows, full),
      });
      state.modalHandler = (act) => { if (act === 'diff-full') draw(true); if (act === 'diff-changes') draw(false); };
    };
    draw(false);
  } catch (e) { openModal({ title: '<h3>Сравнение</h3>', body: errorBody(e.message) }); }
}

async function bulkDelete() {
  const ids = state.backups.filter((b) => state.selected.has(b.id) && b.deletable).map((b) => b.id);
  openModal({ title: '<h3>Удаление бэкапов</h3>', body: loadingBody, narrow: true });
  try {
    const p = await api('/api/backups/bulk-delete/preview', { method: 'POST', body: { ids } });
    openModal({ title: '<h3>Удаление бэкапов</h3>', narrow: true,
      body: `<p>Будет удалено <strong>${p.total}</strong> ${plural(p.total, 'бэкап', 'бэкапа', 'бэкапов')} вместе со всеми файлами снимка. Отменить нельзя.</p>
        <table class="plain-table"><thead><tr><th>Устройство</th><th>Бэкапов</th></tr></thead><tbody class="static">
        ${p.devices.filter((r) => r.deletable).map((r) => `<tr><td>${esc(r.device)}</td><td class="num">${r.deletable}</td></tr>`).join('')}</tbody></table>
        ${p.over_limit ? `<p class="alert alert-error">За раз — не больше ${p.limit}.</p>` : ''}
        <div class="row gap dialog-actions"><button class="btn" data-act="modal-close">Отмена</button>
        <button class="btn btn-danger" data-act="bulk-yes" ${p.over_limit || !p.total ? 'disabled' : ''}>Удалить ${p.total}</button></div>` });
    state.modalHandler = async (act, el) => {
      if (act !== 'bulk-yes') return;
      await withBusy(el, 'Удаление…', async () => {
        const r = await api('/api/backups/bulk-delete', { method: 'POST', body: { ids } });
        closeModal(); state.selected.clear();
        toast(r.failures.length ? `Удалено ${r.deleted}, ошибок: ${r.failures.length}` : `Удалено: ${r.deleted}`, !!r.failures.length);
        loadBackups();
      });
    };
  } catch (e) { openModal({ title: '<h3>Удаление</h3>', body: errorBody(e.message), narrow: true }); }
}

async function restoreBackup(id) {
  state.confirm = null; renderList();
  const b = state.backups.find((x) => x.id === id);
  openModal({ title: `<h3>Восстановление ${esc(b.device)}</h3>`, body: `<div class="loading">${icon('loader', 'spin')} Загрузка и /import…</div>`, narrow: true });
  try {
    const r = await api(`/api/backups/${id}/restore`, { method: 'POST' });
    openModal({ title: `<h3>Восстановление ${esc(b.device)}</h3><div class="small mono muted">${esc(b.filename)}</div>`,
      body: `<div class="alert ${r.ok ? 'alert-ok' : 'alert-error'}">${r.ok ? '/import выполнен' : '/import завершился с ошибками'}</div>
        <pre class="code mt">${esc(r.output || '(нет вывода)')}</pre>` });
  } catch (e) { openModal({ title: '<h3>Восстановление</h3>', body: errorBody(e.message), narrow: true }); }
}

async function deleteOne(id) {
  state.confirm = null;
  try { await api(`/api/backups/${id}`, { method: 'DELETE' }); state.selected.delete(id); toast('Бэкап удалён'); loadBackups(); }
  catch (e) { toast(e.message, true); renderList(); }
}

function bindBackups() {
  let timer;
  $('f-search').addEventListener('input', (e) => {
    clearTimeout(timer); timer = setTimeout(() => { state.filters.search = e.target.value.trim(); loadBackups(); }, 250);
  });
  for (const [id, key] of [['f-device', 'device'], ['f-type', 'type'], ['f-from', 'from'], ['f-to', 'to']]) {
    $(id).addEventListener('change', (e) => { state.filters[key] = e.target.value; loadBackups(); });
  }
  const clear = () => {
    state.filters = { search: '', device: '', type: '', from: '', to: '' };
    for (const id of ['f-search', 'f-device', 'f-from', 'f-to']) $(id).value = '';
    loadBackups();
  };
  $('f-clear').onclick = clear;
  $('sel-clear').onclick = () => { state.selected.clear(); renderBackups(); };
  $('sel-compare').onclick = () => { const p = comparePair(); if (p) compareBackups(p); };
  $('sel-delete').onclick = bulkDelete;

  const dev = $('create-device'), btn = $('create-submit');
  dev.onchange = () => { btn.disabled = !dev.value; };
  $('create-open').onclick = () => { $('create-card').classList.remove('hidden'); dev.focus(); };
  $('create-cancel').onclick = () => { $('create-card').classList.add('hidden'); $('create-error').classList.add('hidden'); };
  btn.onclick = async () => {
    $('create-error').classList.add('hidden');
    try {
      const r = await withBusy(btn, 'Создание…', () => api('/api/backups', { method: 'POST', body: { device: dev.value, notes: $('create-notes').value } }));
      $('create-card').classList.add('hidden'); $('create-notes').value = '';
      toast(r.changed.length ? `Готово. Изменения: ${r.changed.join(', ')}` : 'Готово. Изменений с прошлого бэкапа нет.');
      loadBackups();
    } catch (e) { $('create-error').textContent = e.message; $('create-error').classList.remove('hidden'); }
    btn.disabled = !dev.value;
  };

  $('list').addEventListener('click', (e) => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'clear-filters') return clear();
    const tr = e.target.closest('tr[data-id]');
    if (!tr) {
      if (act === 'toggle-all') {
        const all = state.backups.every((b) => state.selected.has(b.id));
        state.selected = new Set(all ? [] : state.backups.map((b) => b.id));
        renderBackups();
      }
      return;
    }
    const id = tr.dataset.id;
    switch (act) {
      case 'toggle': state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id); renderBackups(); return;
      case 'view': return viewBackup(id);
      case 'delete': case 'restore': state.confirm = { id, action: act }; renderList(); return;
      case 'cancel': state.confirm = null; renderList(); return;
      case 'delete-yes': return deleteOne(id);
      case 'restore-yes': return restoreBackup(id);
    }
    if (!e.target.closest('[data-stop]')) viewBackup(id);
  });
}

/* ================================================================== устройства */

async function loadDevices() {
  const el = $('page-devices');
  el.innerHTML = `<div class="page-head"><h1>Устройства</h1>
    <button class="btn btn-primary admin-only" data-act="add">${icon('plus')} Добавить устройство</button></div>
    <div class="card loading">Загрузка…</div>`;
  let list;
  try { list = await api('/api/devices'); } catch (e) { el.lastElementChild.outerHTML = errorBody(e.message); return; }
  state.devices = list;
  const rows = list.map((d) => {
    const last = d.last;
    const status = !d.enabled ? '<span class="status"><span class="dot off"></span>выключено</span>'
      : !last ? '<span class="status"><span class="dot"></span>ещё не было</span>'
        : last.ok ? `<span class="status"><span class="dot ok"></span>${fmtDate(last.at, false)}</span>`
          : `<span class="status" title="${esc(last.error)}"><span class="dot bad"></span>ошибка · ${fmtDate(last.at, false)}</span>`;
    return `<tr data-id="${d.id}">
      <td class="dev">${esc(d.name)}${d.notes ? `<div class="hint">${esc(d.notes)}</div>` : ''}</td>
      <td class="mono small">${esc(d.host)}</td>
      <td><span class="badge">${esc(TRANSPORT_LABEL[d.transport])}</span>${d.config_only ? ' <span class="badge">только конфиг</span>' : ''}</td>
      <td>${status}</td>
      <td class="actions admin-only">
        <button class="icon-btn" data-act="edit" title="Изменить">${icon('edit', 'i-sm')}</button>
        <button class="icon-btn" data-act="check" title="Проверить доступ">${icon('check', 'i-sm')}</button>
        <button class="icon-btn" data-act="backup" title="Бэкап сейчас">${icon('play', 'i-sm')}</button>
        <button class="icon-btn danger" data-act="delete" title="Удалить">${icon('trash', 'i-sm')}</button>
      </td></tr>`;
  }).join('');
  el.lastElementChild.outerHTML = list.length
    ? `<div class="card table-wrap"><table><thead><tr><th>Имя</th><th>Адрес</th><th>Транспорт</th><th>Последний бэкап</th><th class="admin-only col-actions">Действия</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`
    : `<div class="card empty">${icon('drive')}<strong>Устройств пока нет</strong>
      <span class="muted small">Добавьте роутер: адрес, пользователь на RouterOS и способ подключения.</span></div>`;
  el.onclick = (e) => {
    const act = e.target.closest('[data-act]')?.dataset.act, tr = e.target.closest('tr[data-id]');
    const dev = tr && state.devices.find((d) => d.id === Number(tr.dataset.id));
    if (act === 'add') return deviceForm(null);
    if (!dev) return;
    if (act === 'edit' || (!act && isAdmin())) return deviceForm(dev);
    if (act === 'check') return deviceCheck(dev);
    if (act === 'backup') return deviceBackup(dev, e.target.closest('button'));
    if (act === 'delete') return deviceDelete(dev);
  };
}

const DEVICE_DEFAULTS = { enabled: true, notes: '', host: '', username: 'backup', api_port: 8729, ssh_port: 22, timeout: 30,
  encoding: 'utf-8', transport: 'sftp', config_only: false, api_binary: 'base64', api_b64_chunk: 12288, cert_format: null,
  certs: 'all', tls_fingerprint: null, tls_ca: null, tls_insecure: false, tls_legacy: false, password_set: false };

function deviceForm(dev) {
  const d = { ...DEVICE_DEFAULTS, ...(dev || {}) };
  const tlsMode = d.tls_insecure ? 'insecure' : d.tls_ca ? 'ca' : 'fingerprint';
  const certsMode = Array.isArray(d.certs) ? 'list' : d.certs;
  const opt = (v, cur, label) => `<option value="${v}"${String(cur) === String(v) ? ' selected' : ''}>${label}</option>`;
  openModal({ title: `<h3>${dev ? esc(dev.name) : 'Новое устройство'}</h3>`, body: `
  <form id="dev-form" autocomplete="off">
    <fieldset><legend>Основное</legend><div class="form-grid">
      <label>Имя <input class="input" name="name" value="${esc(d.name || '')}" required pattern="[A-Za-z0-9._\\-]+" placeholder="core-rtr1">
        <span class="hint">Латиница, цифры, . _ - — это и имя папки с бэкапами</span></label>
      <label>Адрес <input class="input" name="host" value="${esc(d.host)}" required placeholder="10.0.0.1"></label>
      <label>Пользователь RouterOS <input class="input" name="username" value="${esc(d.username)}" required></label>
      <label>Пароль <input class="input" type="password" name="password" autocomplete="new-password"
        placeholder="${d.password_set ? 'задан — оставьте пустым, чтобы не менять' : ''}" ${d.password_set ? '' : 'required'}></label>
      <label class="wide">Заметка <input class="input" name="notes" value="${esc(d.notes)}"></label>
      <label class="check"><input type="checkbox" name="enabled" ${d.enabled ? 'checked' : ''}> Включено в расписание</label>
    </div></fieldset>
    <fieldset><legend>Что и как забирать</legend><div class="form-grid">
      <label>Транспорт <select class="input" name="transport">
        ${opt('sftp', d.transport, 'API + SFTP (по умолчанию)')}${opt('api', d.transport, 'Только API-SSL')}${opt('ssh', d.transport, 'Только SSH')}</select>
        <span class="hint" data-hint="transport"></span></label>
      <label class="check"><input type="checkbox" name="config_only" ${d.config_only ? 'checked' : ''}> Только конфиг (без .backup и сертификатов)</label>
      <label data-show="api">Бинарные файлы через API <select class="input" name="api_binary">
        ${opt('base64', d.api_binary, 'base64 (рекомендуется)')}${opt('raw', d.api_binary, 'raw')}${opt('skip', d.api_binary, 'не забирать (без .backup)')}</select></label>
      <label data-show="b64">Размер куска base64 <input class="input" type="number" name="api_b64_chunk" min="3072" max="32768" step="1024" value="${d.api_b64_chunk}"></label>
      <label data-show="certs">Формат сертификатов <select class="input" name="cert_format">
        ${opt('', d.cert_format || '', 'авто')}${opt('p12', d.cert_format, 'PKCS#12 (.p12)')}${opt('pem', d.cert_format, 'PEM (.crt + .key)')}</select></label>
      <label data-show="certs">Какие сертификаты <select class="input" name="certs_mode">
        ${opt('all', certsMode, 'все с приватным ключом')}${opt('list', certsMode, 'только перечисленные')}${opt('none', certsMode, 'не выгружать')}</select></label>
      <label class="wide" data-show="certs-list">Имена сертификатов, по одному в строке
        <textarea class="input" name="certs_list">${esc(Array.isArray(d.certs) ? d.certs.join('\n') : '')}</textarea></label>
    </div></fieldset>
    <fieldset data-show="tls"><legend>Проверка TLS-сертификата API-SSL</legend><div class="form-grid">
      <label class="check"><input type="radio" name="tls_mode" value="fingerprint" ${tlsMode === 'fingerprint' ? 'checked' : ''}> Отпечаток SHA-256</label>
      <label class="check"><input type="radio" name="tls_mode" value="ca" ${tlsMode === 'ca' ? 'checked' : ''}> Сертификат / CA (PEM)</label>
      <label class="check"><input type="radio" name="tls_mode" value="insecure" ${tlsMode === 'insecure' ? 'checked' : ''}> Не проверять (небезопасно)</label>
      <label class="wide" data-show="tls-fp">Отпечаток
        <span class="row gap"><input class="input mono grow1" name="tls_fingerprint" value="${esc(d.tls_fingerprint || '')}" placeholder="E6:36:18:…">
        <button type="button" class="btn btn-sm" data-act="fetch-fp">${icon('key', 'i-sm')} Получить с устройства</button></span>
        <span class="hint" id="fp-info">Сверьте с /certificate print detail на роутере.</span></label>
      <label class="wide" data-show="tls-ca">PEM <textarea class="input" name="tls_ca" placeholder="-----BEGIN CERTIFICATE-----">${esc(d.tls_ca || '')}</textarea></label>
      <label class="check"><input type="checkbox" name="tls_legacy" ${d.tls_legacy ? 'checked' : ''}> Разрешить слабые ключи (1024 бит)</label>
    </div></fieldset>
    <fieldset><legend>Подключение</legend><div class="form-grid">
      <label data-show="tls">Порт API-SSL <input class="input" type="number" name="api_port" min="1" max="65535" value="${d.api_port}"></label>
      <label>Порт SSH <input class="input" type="number" name="ssh_port" min="1" max="65535" value="${d.ssh_port}"></label>
      <label>Таймаут, с <input class="input" type="number" name="timeout" min="1" max="600" value="${d.timeout}"></label>
      <label>Кодировка <select class="input" name="encoding">${opt('utf-8', d.encoding, 'UTF-8')}${opt('cp1251', d.encoding, 'Windows-1251')}</select>
        <span class="hint">cp1251 — если имена и комментарии набирались в Winbox по-русски</span></label>
    </div></fieldset>
    <div class="alert alert-error hidden" id="dev-error"></div>
    <pre class="code hidden" id="dev-result"></pre>
    <div class="row gap dialog-actions">
      ${dev ? `<button type="button" class="btn" data-act="dev-check">Проверить доступ</button>
               <button type="button" class="btn" data-act="dev-probe">Проверить транспорты</button>` : ''}
      <span class="push"></span>
      <button type="button" class="btn" data-act="modal-close">Отмена</button>
      <button class="btn btn-primary">${dev ? 'Сохранить' : 'Добавить'}</button>
    </div>
  </form>` });

  const form = $('dev-form');
  const sync = () => {
    const v = formValues(form);
    const show = {
      api: v.transport === 'api', b64: v.transport === 'api' && v.api_binary === 'base64',
      certs: !v.config_only, 'certs-list': !v.config_only && v.certs_mode === 'list',
      tls: v.transport !== 'ssh', 'tls-fp': v.tls_mode === 'fingerprint', 'tls-ca': v.tls_mode === 'ca',
    };
    form.querySelectorAll('[data-show]').forEach((el) => el.classList.toggle('hidden', !show[el.dataset.show]));
    form.querySelector('[data-hint=transport]').textContent = {
      sftp: 'Команды по API-SSL (8729), файлы по SFTP (22). Надёжно для всего.',
      api: 'Только порт 8729, RouterOS 7.13+. Бинарные файлы — обходным путём.',
      ssh: 'Только порт 22. Конфиг читается из вывода /export — без файлов на роутере.',
    }[v.transport];
  };
  form.addEventListener('change', sync); sync();

  const showResult = (text, ok) => {
    const r = $('dev-result'); r.textContent = text; r.classList.remove('hidden'); r.classList.toggle('code-bad', ok === false);
  };
  state.modalHandler = async (act, el) => {
    if (act === 'fetch-fp') {
      const v = formValues(form);
      await withBusy(el, 'Запрос…', async () => {
        try {
          const r = await api('/api/tools/fingerprint', { method: 'POST', body: { host: v.host, port: v.api_port } });
          form.querySelector('[name=tls_fingerprint]').value = r.fingerprint;
          $('fp-info').textContent = `${r.subject}, действует до ${r.not_after}, ключ ${r.key_bits} бит. Сверьте отпечаток с роутером!`;
        } catch (ex) { $('fp-info').textContent = ex.message; }
      });
    }
    if (act === 'dev-check') {
      await withBusy(el, 'Проверка…', async () => {
        const r = await api(`/api/devices/${dev.id}/check`, { method: 'POST' });
        showResult(r.error ? `Ошибка: ${r.error}` : `${r.identity}, RouterOS ${r.version}\nГруппа: ${r.group}\nТранспорт ${r.transport}: ${r.files}\n`
          + (r.missing_policies.length ? `Не хватает политик: ${r.missing_policies.join(', ')}` : 'Права группы: достаточно'), r.ok);
      });
    }
    if (act === 'dev-probe') {
      await withBusy(el, 'Проверка… (до минуты)', async () => {
        const r = await api(`/api/devices/${dev.id}/probe`, { method: 'POST', body: { sftp: true } });
        showResult(r.report, r.ok);
      });
    }
  };

  form.onsubmit = async (e) => {
    e.preventDefault();
    const v = formValues(form);
    const body = { ...v };
    body.certs = v.certs_mode === 'list' ? v.certs_list.split('\n').map((s) => s.trim()).filter(Boolean) : v.certs_mode;
    body.tls_insecure = v.tls_mode === 'insecure';
    if (v.tls_mode !== 'fingerprint') body.tls_fingerprint = '';
    if (v.tls_mode !== 'ca') body.tls_ca = '';
    for (const k of ['certs_mode', 'certs_list', 'tls_mode']) delete body[k];
    if (!body.password) delete body.password;
    try {
      await api(dev ? `/api/devices/${dev.id}` : '/api/devices', { method: dev ? 'PUT' : 'POST', body });
      closeModal(); toast(dev ? 'Устройство сохранено' : 'Устройство добавлено');
      state.me = await api('/api/me'); renderBanners(); loadDevices();
    } catch (ex) { $('dev-error').textContent = ex.message; $('dev-error').classList.remove('hidden'); }
  };
}

async function deviceCheck(dev) {
  openModal({ title: `<h3>Проверка ${esc(dev.name)}</h3>`, body: loadingBody, narrow: true });
  try {
    const r = await api(`/api/devices/${dev.id}/check`, { method: 'POST' });
    openModal({ title: `<h3>Проверка ${esc(dev.name)}</h3>`, narrow: true, body: r.error
      ? errorBody(r.error)
      : `<div class="alert ${r.ok ? 'alert-ok' : 'alert-error'}">${r.ok ? 'Доступ есть, прав достаточно' : 'Не хватает политик: ' + esc(r.missing_policies.join(', '))}</div>
         <pre class="code mt">${esc(`${r.identity}, RouterOS ${r.version}\nГруппа: ${r.group}\nТранспорт ${r.transport}: ${r.files}`)}</pre>` });
  } catch (e) { openModal({ title: '<h3>Проверка</h3>', body: errorBody(e.message), narrow: true }); }
}

async function deviceBackup(dev, btn) {
  try {
    const r = await withBusy(btn, '', () => api(`/api/devices/${dev.id}/backup`, { method: 'POST', body: {} }));
    toast(`${dev.name}: ${r.changed.length ? 'изменения — ' + r.changed.join(', ') : 'без изменений'}`);
    loadDevices();
  } catch (e) { toast(`${dev.name}: ${e.message}`, true); loadDevices(); }
}

function deviceDelete(dev) {
  openModal({ title: `<h3>Удалить ${esc(dev.name)}?</h3>`, narrow: true, body: `
    <p>Устройство пропадёт из расписания. Уже сделанные бэкапы останутся в папке и в списке бэкапов.</p>
    <div class="row gap dialog-actions"><button class="btn" data-act="modal-close">Отмена</button>
    <button class="btn btn-danger" data-act="yes">Удалить</button></div>` });
  state.modalHandler = async (act) => {
    if (act !== 'yes') return;
    try { await api(`/api/devices/${dev.id}`, { method: 'DELETE' }); closeModal(); toast('Устройство удалено');
      state.me = await api('/api/me'); renderBanners(); loadDevices(); }
    catch (e) { toast(e.message, true); }
  };
}

/* ================================================================== журнал */

async function loadRuns() {
  const el = $('page-runs');
  let data;
  try { data = await api('/api/runs?limit=100'); } catch (e) { el.innerHTML = errorBody(e.message); return; }
  const KIND = { scheduled: 'По расписанию', manual: 'Ручной' };
  const rows = data.runs.map((r) => {
    const failed = Object.keys(r.failed).length, changed = Object.keys(r.changed).length;
    const dur = r.finished_at ? `${Math.max(1, Math.round(r.finished_at - r.started_at))} с` : 'идёт…';
    const status = !r.finished_at ? '<span class="badge warn">идёт</span>'
      : failed ? `<span class="badge bad">ошибок: ${failed}</span>` : r.warnings.length ? '<span class="badge warn">предупреждения</span>' : '<span class="badge ok">успешно</span>';
    const details = [
      ...Object.entries(r.failed).map(([n, e]) => `<div class="err-text"><b>${esc(n)}</b>: ${esc(e)}</div>`),
      ...Object.entries(r.changed).map(([n, c]) => `<div><b>${esc(n)}</b>: ${esc(c.join(', '))}</div>`),
      ...r.warnings.map((w) => `<div class="err-text">⚠ ${esc(w)}</div>`),
    ].join('');
    return `<tr><td class="date">${fmtDate(r.started_at)}</td><td>${KIND[r.kind] || esc(r.kind)}${r.user ? ` <span class="muted small">· ${esc(r.user)}</span>` : ''}</td>
      <td>${status}</td><td class="num">${r.ok.length}/${r.devices.length}</td><td class="num">${changed || '—'}</td><td class="num">${dur}</td></tr>
      ${details ? `<tr class="details"><td colspan="6">${details}</td></tr>` : ''}`;
  }).join('');
  el.innerHTML = `<div class="page-head"><h1>Журнал запусков</h1>
      <button class="btn btn-primary admin-only" id="run-all" ${data.running ? 'disabled' : ''}>${icon('play')} ${data.running ? 'Прогон идёт…' : 'Запустить сейчас'}</button></div>
    ${data.runs.length ? `<div class="card table-wrap"><table><thead><tr><th>Начало</th><th>Тип</th><th>Статус</th><th>Успешно</th><th>С изменениями</th><th>Длительность</th></tr></thead>
      <tbody class="static">${rows}</tbody></table></div>` : `<div class="card empty">${icon('drive')}<strong>Запусков ещё не было</strong></div>`}`;
  const btn = $('run-all');
  if (btn) btn.onclick = async () => {
    try { await api('/api/runs', { method: 'POST' }); toast('Прогон запущен по всем включённым устройствам'); setTimeout(loadRuns, 800); }
    catch (e) { toast(e.message, true); }
  };
  if (data.running) state.runsTimer = setTimeout(() => state.page === 'runs' && loadRuns(), 3000);
}

/* ================================================================== настройки */

const SECRET_KEYS = new Set(['backup_passphrase', 'gitea_token', 'telegram_token']);

async function loadSettings() {
  const el = $('page-settings');
  el.innerHTML = '<div class="page-head"><h1>Настройки</h1></div><div class="card loading">Загрузка…</div>';
  let data;
  try { data = await api('/api/settings'); } catch (e) { el.lastElementChild.outerHTML = errorBody(e.message); return; }
  renderSettings(data);
}

function renderSettings(data) {
  const s = data.settings, el = $('page-settings');
  const secret = (key, label, hint = '') => `<label>${label}
      <span class="secret-state ${s[key].set ? 'set' : 'unset'}">${s[key].set ? '● задан' : '○ не задан'}</span>
      <input class="input" type="password" name="${key}" autocomplete="new-password" placeholder="${s[key].set ? 'оставьте пустым, чтобы не менять' : ''}">
      ${s[key].set ? `<span class="check hint"><input type="checkbox" data-clear="${key}"> удалить</span>` : ''}
      ${hint ? `<span class="hint">${hint}</span>` : ''}</label>`;
  const text = (key, label, hint = '', attrs = '') => `<label>${label}<input class="input" name="${key}" value="${esc(s[key])}" ${attrs}>${hint ? `<span class="hint">${hint}</span>` : ''}</label>`;
  const num = (key, label, min, max, hint = '') => `<label>${label}<input class="input" type="number" name="${key}" min="${min}" max="${max}" value="${s[key]}">${hint ? `<span class="hint">${hint}</span>` : ''}</label>`;
  const chk = (key, label) => `<label class="check"><input type="checkbox" name="${key}" ${s[key] ? 'checked' : ''}> ${label}</label>`;
  el.innerHTML = `<div class="page-head"><h1>Настройки</h1></div>
  <form id="settings-form" autocomplete="off"><div class="settings-grid">
    <section class="card"><h3>Расписание</h3><div class="form-grid">
      ${text('schedule', 'Cron-выражение', 'мин час день месяц день_недели. «0 3 * * *» — каждый день в 03:00', 'required')}
      ${text('timezone', 'Часовой пояс', 'Например, Europe/Moscow')}
      ${num('workers', 'Устройств параллельно', 1, 32)}
      <div class="wide hint">Следующий запуск: <b>${data.next_run ? fmtDate(data.next_run) : '—'}</b></div>
    </div></section>

    <section class="card"><h3>Хранение и шифрование</h3><div class="form-grid">
      ${secret('backup_passphrase', 'Пароль шифрования .backup и сертификатов', 'Храните его отдельно: без него бэкапы не восстановить')}
      <label>Режим хранения <select class="input" name="storage">
        <option value="git"${s.storage === 'git' ? ' selected' : ''}>git — текущее состояние + история</option>
        <option value="snapshots"${s.storage === 'snapshots' ? ' selected' : ''}>снимки — папка с датой на каждый прогон</option></select></label>
      <div data-show="git" class="wide">${chk('git_history', 'Вести историю изменений в git')}</div>
      <div data-show="snapshots">${num('snapshot_retention_days', 'Хранить снимки, дней', 0, 36500, '0 — хранить все')}</div>
      <div data-show="snapshots">${num('snapshot_keep_min', 'Всегда оставлять последних', 1, 10000)}</div>
      <div data-show="snapshots" class="wide">${chk('snapshot_on_change', 'Создавать снимок только при изменениях')}</div>
    </div></section>

    <section class="card" data-show="git"><h3>Gitea <span class="muted small">— необязательно</span></h3><div class="form-grid">
      <label class="wide">URL репозитория<input class="input" name="gitea_url" value="${esc(s.gitea_url)}" placeholder="https://gitea.local/netops/mikrotik-backups.git"><span class="hint">Пусто — push выключен</span></label>
      ${text('gitea_user', 'Пользователь')}
      ${secret('gitea_token', 'Токен доступа', 'Право write:repository')}
      ${text('gitea_branch', 'Ветка')}
      ${text('git_author_name', 'Автор коммитов')}
      ${text('git_author_email', 'E-mail автора')}
      <label class="wide">CA Gitea (PEM), если самоподписанный<textarea class="input" name="gitea_ca_pem" placeholder="-----BEGIN CERTIFICATE-----">${esc(s.gitea_ca_pem)}</textarea></label>
      ${chk('gitea_insecure', 'Не проверять TLS Gitea (небезопасно)')}
    </div></section>

    <section class="card"><h3>Уведомления в Telegram <span class="muted small">— необязательно</span></h3><div class="form-grid">
      ${secret('telegram_token', 'Токен бота')}
      ${text('telegram_chat', 'chat_id')}
      <div class="wide row gap"><button type="button" class="btn btn-sm" data-act="test-tg">Отправить тестовое сообщение</button>
        <span class="hint">Сначала сохраните настройки. Уведомления приходят при ошибках и изменениях.</span></div>
    </div></section>

    <section class="card"><h3>Веб-интерфейс</h3><div class="form-grid">
      <div class="wide">${chk('web_restore', 'Разрешить восстановление (/import по SSH) из списка бэкапов')}</div>
      <div class="wide hint">Cookie сессии ${data.cookie_secure ? 'с флагом Secure (HTTPS)' : 'без флага Secure — для работы через HTTPS за прокси задайте WEB_COOKIE_SECURE=true'}.</div>
    </div></section>
  </div>
  <div class="alert alert-error hidden mt" id="settings-error"></div>
  <div class="sticky-save mt"><span class="muted small" id="settings-dirty"></span>
    <button type="button" class="btn" data-act="reset">Отменить изменения</button>
    <button class="btn btn-primary">Сохранить</button></div>
  </form>`;

  const form = $('settings-form');
  const sync = () => {
    const v = formValues(form);
    form.querySelectorAll('[data-show]').forEach((x) => x.classList.toggle('hidden', x.dataset.show !== v.storage));
    $('settings-dirty').textContent = Object.keys(collect()).length ? 'Есть несохранённые изменения' : '';
  };
  const collect = () => {
    const v = formValues(form), out = {};
    for (const [k, val] of Object.entries(v)) {
      if (SECRET_KEYS.has(k)) { if (val) out[k] = val; continue; }
      if (String(val) !== String(s[k])) out[k] = val;
    }
    form.querySelectorAll('[data-clear]').forEach((c) => { if (c.checked) out[c.dataset.clear] = null; });
    return out;
  };
  form.addEventListener('input', sync); form.addEventListener('change', sync); sync();
  form.onclick = async (e) => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'reset') renderSettings(data);
    if (act === 'test-tg') {
      const btn = e.target.closest('button');
      await withBusy(btn, 'Отправка…', async () => {
        try { await api('/api/settings/test-telegram', { method: 'POST' }); toast('Сообщение отправлено'); }
        catch (ex) { toast(ex.message, true); }
      });
    }
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const changes = collect();
    if (!Object.keys(changes).length) return toast('Нет изменений');
    try {
      const r = await api('/api/settings', { method: 'PUT', body: changes });
      toast(`Сохранено: ${r.changed.length}`);
      state.me = await api('/api/me'); renderBanners(); renderSettings(r);
    } catch (ex) { $('settings-error').textContent = ex.message; $('settings-error').classList.remove('hidden'); }
  };
}

/* ================================================================== пользователи */

async function loadUsers() {
  const el = $('page-users');
  let list;
  try { list = await api('/api/users'); } catch (e) { el.innerHTML = errorBody(e.message); return; }
  const rows = list.map((u) => {
    const st = !u.password_set ? '<span class="badge warn">пароль не задан</span>'
      : u.must_set_password ? '<span class="badge warn">временный пароль</span>' : '<span class="badge ok">активен</span>';
    const self = u.username === state.me.user;
    return `<tr data-id="${u.id}"><td class="dev">${esc(u.username)}${self ? ' <span class="muted small">(вы)</span>' : ''}</td>
      <td><select class="input input-sm" data-act="role">
        <option value="admin"${u.role === 'admin' ? ' selected' : ''}>администратор</option>
        <option value="viewer"${u.role === 'viewer' ? ' selected' : ''}>просмотр</option></select></td>
      <td>${st}</td><td class="date">${u.last_login ? fmtDate(u.last_login) : '—'}</td>
      <td class="actions"><button class="icon-btn" data-act="reset" title="Выдать временный пароль">${icon('key', 'i-sm')}</button>
        ${self ? '' : `<button class="icon-btn danger" data-act="delete" title="Удалить">${icon('trash', 'i-sm')}</button>`}</td></tr>`;
  }).join('');
  el.innerHTML = `<div class="page-head"><h1>Пользователи</h1>
      <button class="btn btn-primary" data-act="add">${icon('plus')} Добавить пользователя</button></div>
    <div class="card table-wrap"><table><thead><tr><th>Логин</th><th>Роль</th><th>Статус</th><th>Последний вход</th><th class="col-actions">Действия</th></tr></thead>
    <tbody class="static">${rows}</tbody></table></div>
    <p class="hint">Администратор управляет устройствами, настройками и пользователями, создаёт, удаляет и восстанавливает бэкапы. Просмотр — только список, просмотр и скачивание бэкапов.</p>`;
  el.onchange = async (e) => {
    if (e.target.dataset.act !== 'role') return;
    const id = e.target.closest('tr').dataset.id;
    try { await api(`/api/users/${id}`, { method: 'PUT', body: { role: e.target.value } }); toast('Роль изменена'); }
    catch (ex) { toast(ex.message, true); loadUsers(); }
  };
  el.onclick = (e) => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    const tr = e.target.closest('tr[data-id]');
    const user = tr && list.find((u) => u.id === Number(tr.dataset.id));
    if (act === 'add') userForm();
    if (act === 'reset' && user) userReset(user);
    if (act === 'delete' && user) userDelete(user);
  };
}

function tempPasswordField() {
  return `<label>Временный пароль
    <span class="row gap"><input class="input mono grow1" name="password" value="${genPassword()}" minlength="10" required>
    <button type="button" class="btn btn-sm" data-act="gen">Другой</button></span>
    <span class="hint">Передайте пользователю. При первом входе он придумает свой пароль.</span></label>`;
}

function userForm() {
  openModal({ title: '<h3>Новый пользователь</h3>', narrow: true, body: `
    <form class="stack" id="user-form" autocomplete="off">
      <label>Логин <input class="input" name="username" required pattern="[A-Za-z0-9._@\\-]{2,64}"></label>
      <label>Роль <select class="input" name="role"><option value="viewer">просмотр</option><option value="admin">администратор</option></select></label>
      ${tempPasswordField()}
      <div class="alert alert-error hidden" id="user-error"></div>
      <div class="row gap dialog-actions"><button type="button" class="btn" data-act="modal-close">Отмена</button><button class="btn btn-primary">Создать</button></div>
    </form>` });
  state.modalHandler = (act) => { if (act === 'gen') $('user-form').password.value = genPassword(); };
  $('user-form').onsubmit = async (e) => {
    e.preventDefault();
    try { await api('/api/users', { method: 'POST', body: formValues(e.target) }); closeModal(); toast('Пользователь создан'); loadUsers(); }
    catch (ex) { $('user-error').textContent = ex.message; $('user-error').classList.remove('hidden'); }
  };
}

function userReset(user) {
  openModal({ title: `<h3>Временный пароль для ${esc(user.username)}</h3>`, narrow: true, body: `
    <form class="stack" id="reset-form">${tempPasswordField()}
      <p class="hint">Текущие сессии пользователя будут завершены.</p>
      <div class="alert alert-error hidden" id="reset-error"></div>
      <div class="row gap dialog-actions"><button type="button" class="btn" data-act="modal-close">Отмена</button><button class="btn btn-primary">Выдать</button></div>
    </form>` });
  state.modalHandler = (act) => { if (act === 'gen') $('reset-form').password.value = genPassword(); };
  $('reset-form').onsubmit = async (e) => {
    e.preventDefault();
    try { await api(`/api/users/${user.id}/reset`, { method: 'POST', body: formValues(e.target) }); closeModal(); toast('Временный пароль выдан'); loadUsers(); }
    catch (ex) { $('reset-error').textContent = ex.message; $('reset-error').classList.remove('hidden'); }
  };
}

function userDelete(user) {
  openModal({ title: `<h3>Удалить ${esc(user.username)}?</h3>`, narrow: true, body: `
    <div class="row gap dialog-actions"><button class="btn" data-act="modal-close">Отмена</button><button class="btn btn-danger" data-act="yes">Удалить</button></div>` });
  state.modalHandler = async (act) => {
    if (act !== 'yes') return;
    try { await api(`/api/users/${user.id}`, { method: 'DELETE' }); closeModal(); toast('Пользователь удалён'); loadUsers(); }
    catch (e) { toast(e.message, true); }
  };
}

/* ================================================================== аудит */

const AUDIT_LABEL = {
  login: 'вход', login_failed: 'неудачный вход', password_set: 'пароль задан', password_changed: 'смена пароля',
  settings_update: 'настройки', device_create: 'устройство добавлено', device_update: 'устройство изменено',
  device_delete: 'устройство удалено', user_create: 'пользователь создан', user_role: 'смена роли',
  user_reset_password: 'временный пароль', user_delete: 'пользователь удалён', backup_manual: 'ручной бэкап',
  backup_delete: 'бэкап удалён', backup_bulk_delete: 'удаление бэкапов', backup_restore: 'восстановление',
  backup_download: 'скачивание', run_all: 'запуск всех', import_config: 'импорт конфигурации',
};

async function loadAudit() {
  const el = $('page-audit');
  let list;
  try { list = await api('/api/audit?limit=300'); } catch (e) { el.innerHTML = errorBody(e.message); return; }
  el.innerHTML = `<div class="page-head"><h1>Аудит</h1><span class="muted small">последние 300 событий</span></div>
    <div class="card table-wrap"><table><thead><tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Подробности</th></tr></thead>
    <tbody class="static">${list.map((a) => `<tr><td class="date">${fmtDate(a.ts)}</td><td>${esc(a.user || '—')}</td>
      <td><span class="badge ${a.action.includes('failed') ? 'bad' : ''}">${esc(AUDIT_LABEL[a.action] || a.action)}</span></td>
      <td class="small">${esc(a.details)}</td></tr>`).join('')}</tbody></table></div>`;
}

/* ================================================================== события */

function bindGlobal() {
  $('auth-form').addEventListener('submit', submitAuth);
  for (const id of ['auth-new', 'auth-confirm']) $(id).addEventListener('input', updateRules);
  $('auth-back').onclick = () => setAuthMode('login');
  $('user-btn').onclick = (e) => { e.stopPropagation(); $('user-menu').classList.toggle('hidden'); };
  document.addEventListener('click', () => $('user-menu').classList.add('hidden'));
  $('user-menu').onclick = (e) => {
    const act = e.target.dataset.act;
    if (act === 'logout') logout();
    if (act === 'change-password') changePassword();
  };
  $('modal').addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]'), act = el?.dataset.act;
    if (e.target === $('modal') || act === 'modal-close') return closeModal();
    if (act && state.modalHandler) state.modalHandler(act, el);
  });
  $('modal-close').onclick = closeModal;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
  $('theme-btn').onclick = () => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    try { localStorage.setItem('mtbk-theme', dark ? 'dark' : 'light'); } catch { /* приватный режим */ }
  };
  window.addEventListener('hashchange', () => state.me && route());
}

(function initTheme() {
  let t = null;
  try { t = localStorage.getItem('mtbk-theme'); } catch { /* ignore */ }
  if (!t) t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.dataset.theme = t;
})();

document.addEventListener('DOMContentLoaded', () => {
  bindGlobal(); bindBackups();
  start();
});
