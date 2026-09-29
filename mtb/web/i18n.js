/* mtb — язык и тема. Загружается в <head> без defer, чтобы тема и язык
   применились до отрисовки (без мигания светлой темы).
   Строки интерфейса пишутся по-русски и оборачиваются в t('…'); здесь —
   английские переводы. Отсутствующий перевод показывается по-русски. */
'use strict';

const EN = {
  // ---- общее
  'Загрузка…': 'Loading…', 'Сохранить': 'Save', 'Отмена': 'Cancel', 'Удалить': 'Delete', 'Удалить?': 'Delete?',
  'Изменить': 'Edit', 'Добавить': 'Add', 'Создать': 'Create', 'Скачать': 'Download', 'Просмотр': 'View',
  'удалить': 'delete', 'Сбросить': 'Reset', 'Закрыть (Esc)': 'Close (Esc)', 'МБ': 'MB', 'КБ': 'KB', 'Б': 'B', 'с': 's',
  'Требуется вход': 'Login required', 'Проверка': 'Check', 'Проверка…': 'Checking…', 'Ошибка:': 'Error:',
  'Сохранение…': 'Saving…', 'Создание…': 'Creating…', 'Удаление…': 'Deleting…', 'Отправка…': 'Sending…', 'Запрос…': 'Requesting…',
  'Язык / Language': 'Language / Язык', 'Тема': 'Theme',
  'Тема: светлая': 'Theme: light', 'Тема: тёмная': 'Theme: dark', 'Тема: как в системе': 'Theme: system',

  // ---- навигация и меню
  'Бэкапы': 'Backups', 'Устройства': 'Devices', 'Журнал': 'Runs', 'Настройки': 'Settings',
  'Пользователи': 'Users', 'Аудит': 'Audit', 'Сменить пароль': 'Change password', 'Выйти': 'Log out',
  ' · просмотр': ' · viewer',

  // ---- вход
  'Логин': 'Username', 'Пароль': 'Password', 'Войти': 'Log in', 'Вход…': 'Logging in…',
  'Текущий (временный) пароль': 'Current (temporary) password', 'Новый пароль': 'New password',
  'Подтверждение пароля': 'Confirm password', 'Подтверждение': 'Confirm',
  'не короче 10 символов': 'at least 10 characters', 'пароли совпадают': 'passwords match',
  'не совпадает с логином': 'differs from the username', '← Другой пользователь': '← Another user',
  'Сохранить пароль и войти': 'Save password and log in',
  'Первый запуск. Придумайте пароль администратора — он понадобится для входа.':
    'First start. Choose an administrator password — you will need it to log in.',
  'Администратор выдал временный пароль. Введите его и придумайте свой.':
    'An administrator issued a temporary password. Enter it and choose your own.',
  'Пароль ещё не задан. Придумайте пароль для входа.': 'No password set yet. Choose a password to log in.',
  'Пароль не соответствует требованиям': 'The password does not meet the requirements',
  'Смена пароля': 'Change password', 'Текущий пароль': 'Current password',
  'Не короче 10 символов. Остальные сессии будут завершены.': 'At least 10 characters. Your other sessions will be ended.',
  'Пароль изменён': 'Password changed',

  // ---- баннеры
  'Устройств пока нет.': 'No devices yet.', 'Добавьте первое устройство': 'Add the first device',
  'Устройств пока нет — их добавляет администратор.': 'No devices yet — an administrator adds them.',
  'Не задан пароль шифрования бэкапов — без него .backup и сертификаты не создаются.':
    'No backup encryption passphrase set — without it, .backup and certificates are not created.',
  'Настройки → Хранение': 'Settings → Storage',

  // ---- бэкапы
  'По расписанию': 'Scheduled', 'Ручной': 'Manual', 'Текущий': 'Current',
  'снимки': 'snapshots', 'git-история': 'git history', 'только текущее': 'current only',
  'Создать бэкап': 'Create backup', 'Новый бэкап': 'New backup', 'Заметка (необязательно)': 'Note (optional)',
  'Перед обновлением…': 'Before upgrade…', 'Поиск': 'Search', 'Устройство, файл или заметка…': 'Device, file or note…',
  'С': 'From', 'По': 'To', 'Все устройства': 'All devices', 'Выберите устройство…': 'Select a device…', 'Все типы': 'All types',
  'Снять выделение': 'Clear selection', 'Сравнить': 'Compare', 'Выбрано:': 'Selected:',
  'Сравнить два выбранных бэкапа': 'Compare the two selected backups', 'Выберите ровно два бэкапа': 'Select exactly two backups',
  'бэкап': 'backup', 'бэкапа': 'backups', 'бэкапов': 'backups', 'Бэкапов': 'Backups',
  'из истории git удалить нельзя': 'from git history cannot be deleted',
  'Восстановить?': 'Restore?', 'Восстановить (/import)': 'Restore (/import)', 'всего)': 'total)',
  'Нет бэкапов, подходящих под фильтры': 'No backups match these filters', 'Бэкапов пока нет': 'No backups yet',
  'Расширьте диапазон дат или сбросьте фильтр.': 'Widen the date range or clear a filter.',
  'Они появятся после первого прогона по расписанию или ручного бэкапа.': 'They will appear after the first scheduled run or a manual backup.',
  'Сбросить фильтры': 'Clear filters', 'Нажмите для просмотра': 'Click to preview', 'Выбрать': 'Select', 'Выбрать все': 'Select all',
  'Устройство': 'Device', 'Тип': 'Type', 'Размер': 'Size', 'Создан': 'Created', 'Заметка': 'Note', 'Действия': 'Actions',
  'строка': 'line', 'строки': 'lines', 'строк': 'lines', 'без изменений ⋯': 'unchanged ⋯',
  'Бэкап': 'Backup', 'Скачать config.rsc': 'Download config.rsc', 'Файл больше 2 МБ — показано начало.': 'File is larger than 2 MB — showing the beginning.',
  'Сравнение бэкапов': 'Comparing backups', 'Сравнение': 'Compare', 'Изменения': 'Changes', 'Весь файл': 'Whole file',
  'Эти два бэкапа идентичны.': 'These two backups are identical.',
  'Удаление бэкапов': 'Delete backups', 'Будет удалено': 'This will delete',
  'вместе со всеми файлами снимка. Отменить нельзя.': 'with all snapshot files. This cannot be undone.',
  'За раз — не больше': 'At most per request:', 'Удалено': 'Deleted', ', ошибок:': ', errors:', 'Удалено:': 'Deleted:',
  'Удаление': 'Delete', 'Восстановление': 'Restore', 'Загрузка и /import…': 'Uploading and running /import…',
  '/import выполнен': '/import completed', '/import завершился с ошибками': '/import finished with errors',
  '(нет вывода)': '(no output)', 'Бэкап удалён': 'Backup deleted',
  'Готово. Изменения:': 'Done. Changes:', 'Готово. Изменений с прошлого бэкапа нет.': 'Done. No changes since the previous backup.',

  // ---- устройства
  'Добавить устройство': 'Add device', 'выключено': 'disabled', 'ещё не было': 'never', 'ошибка ·': 'error ·',
  'только конфиг': 'config only', 'только API': 'API only', 'только SSH': 'SSH only',
  'Проверить доступ': 'Check access', 'Бэкап сейчас': 'Back up now', 'Имя': 'Name', 'Адрес': 'Address',
  'Транспорт': 'Transport', 'Последний бэкап': 'Last backup', 'Устройств пока нет': 'No devices yet',
  'Добавьте роутер: адрес, пользователь на RouterOS и способ подключения.': 'Add a router: address, RouterOS user and connection method.',
  'Новое устройство': 'New device', 'Основное': 'General',
  'Латиница, цифры, . _ - — это и имя папки с бэкапами': 'Latin letters, digits, . _ - — also the backup folder name',
  'Пользователь RouterOS': 'RouterOS user', 'задан — оставьте пустым, чтобы не менять': 'set — leave empty to keep',
  'Включено в расписание': 'Enabled in schedule', 'Что и как забирать': 'What to collect and how',
  'API + SFTP (по умолчанию)': 'API + SFTP (default)', 'Только API-SSL': 'API-SSL only', 'Только SSH': 'SSH only',
  'Только конфиг (без .backup и сертификатов)': 'Config only (no .backup or certificates)',
  'Бинарные файлы через API': 'Binary files via API', 'base64 (рекомендуется)': 'base64 (recommended)',
  'не забирать (без .backup)': "don't fetch (no .backup)", 'Размер куска base64': 'base64 chunk size',
  'Формат сертификатов': 'Certificate format', 'авто': 'auto', 'Какие сертификаты': 'Which certificates',
  'все с приватным ключом': 'all with a private key', 'только перечисленные': 'only the listed ones', 'не выгружать': "don't export",
  'Имена сертификатов, по одному в строке': 'Certificate names, one per line',
  'Проверка TLS-сертификата API-SSL': 'API-SSL TLS certificate verification', 'Отпечаток SHA-256': 'SHA-256 fingerprint',
  'Сертификат / CA (PEM)': 'Certificate / CA (PEM)', 'Не проверять (небезопасно)': "Don't verify (insecure)",
  'Отпечаток': 'Fingerprint', 'Получить с устройства': 'Fetch from device',
  'Сверьте с /certificate print detail на роутере.': 'Compare with /certificate print detail on the router.',
  'Разрешить слабые ключи (1024 бит)': 'Allow weak keys (1024-bit)', 'Подключение': 'Connection',
  'Порт API-SSL': 'API-SSL port', 'Порт SSH': 'SSH port', 'Таймаут, с': 'Timeout, s', 'Кодировка': 'Encoding',
  'cp1251 — если имена и комментарии набирались в Winbox по-русски': 'cp1251 — if names and comments were typed in Cyrillic via Winbox',
  'Проверить транспорты': 'Check transports',
  'Команды по API-SSL (8729), файлы по SFTP (22). Надёжно для всего.': 'Commands over API-SSL (8729), files over SFTP (22). Reliable for everything.',
  'Только порт 8729, RouterOS 7.13+. Бинарные файлы — обходным путём.': 'Port 8729 only, RouterOS 7.13+. Binary files via a workaround.',
  'Только порт 22. Конфиг читается из вывода /export — без файлов на роутере.': 'Port 22 only. The config is read from /export output — no files on the router.',
  ', действует до': ', valid until', ', ключ': ', key', 'бит. Сверьте отпечаток с роутером!': 'bits. Verify the fingerprint on the router!',
  'Группа:': 'Group:', 'Не хватает политик:': 'Missing policies:', 'Не хватает политик: ': 'Missing policies: ',
  'Права группы: достаточно': 'Group permissions: sufficient', 'Проверка… (до минуты)': 'Checking… (up to a minute)',
  'Устройство сохранено': 'Device saved', 'Устройство добавлено': 'Device added',
  'Доступ есть, прав достаточно': 'Access works, permissions are sufficient',
  'изменения — ': 'changes — ', 'без изменений': 'no changes',
  'Устройство пропадёт из расписания. Уже сделанные бэкапы останутся в папке и в списке бэкапов.':
    'The device will be removed from the schedule. Existing backups stay in the folder and in the backup list.',
  'Устройство удалено': 'Device deleted',

  // ---- журнал
  'идёт…': 'running…', 'идёт': 'running', 'ошибок:': 'errors:', 'предупреждения': 'warnings', 'успешно': 'success',
  'Журнал запусков': 'Run history', 'Прогон идёт…': 'Run in progress…', 'Запустить сейчас': 'Run now',
  'Начало': 'Started', 'Статус': 'Status', 'Успешно': 'Succeeded', 'С изменениями': 'Changed', 'Длительность': 'Duration',
  'Запусков ещё не было': 'No runs yet', 'Прогон запущен по всем включённым устройствам': 'Run started for all enabled devices',

  // ---- настройки
  '● задан': '● set', '○ не задан': '○ not set', 'оставьте пустым, чтобы не менять': 'leave empty to keep',
  'Расписание': 'Schedule', 'Cron-выражение': 'Cron expression',
  'мин час день месяц день_недели. «0 3 * * *» — каждый день в 03:00': 'min hour day month weekday. "0 3 * * *" — every day at 03:00',
  'Часовой пояс': 'Time zone', 'Например, Europe/Moscow': 'For example, Europe/Moscow',
  'Устройств параллельно': 'Devices in parallel', 'Следующий запуск:': 'Next run:',
  'Хранение и шифрование': 'Storage and encryption', 'Пароль шифрования .backup и сертификатов': 'Passphrase for .backup and certificates',
  'Храните его отдельно: без него бэкапы не восстановить': 'Keep it separately: without it backups cannot be restored',
  'Режим хранения': 'Storage mode', 'git — текущее состояние + история': 'git — current state + history',
  'снимки — папка с датой на каждый прогон': 'snapshots — a dated folder per run',
  'Вести историю изменений в git': 'Keep change history in git', 'Хранить снимки, дней': 'Keep snapshots, days',
  '0 — хранить все': '0 — keep all', 'Всегда оставлять последних': 'Always keep the newest',
  'Создавать снимок только при изменениях': 'Create a snapshot only when something changed',
  '— необязательно': '— optional', 'URL репозитория': 'Repository URL', 'Пусто — push выключен': 'Empty — push disabled',
  'Пользователь': 'User', 'Токен доступа': 'Access token', 'Право write:repository': 'Scope write:repository',
  'Ветка': 'Branch', 'Автор коммитов': 'Commit author', 'E-mail автора': 'Author e-mail',
  'CA Gitea (PEM), если самоподписанный': 'Gitea CA (PEM), if self-signed',
  'Не проверять TLS Gitea (небезопасно)': "Don't verify Gitea TLS (insecure)",
  'Уведомления в Telegram': 'Telegram notifications', 'Токен бота': 'Bot token',
  'Отправить тестовое сообщение': 'Send a test message',
  'Сначала сохраните настройки. Уведомления приходят при ошибках и изменениях.': 'Save the settings first. Notifications are sent on errors and changes.',
  'Язык уведомлений': 'Notification language',
  'Веб-интерфейс': 'Web interface', 'Разрешить восстановление (/import по SSH) из списка бэкапов': 'Allow restore (/import over SSH) from the backup list',
  'Cookie сессии': 'Session cookie', 'с флагом Secure (HTTPS)': 'has the Secure flag (HTTPS)',
  'без флага Secure — для работы через HTTPS за прокси задайте WEB_COOKIE_SECURE=true': 'has no Secure flag — behind an HTTPS proxy, set WEB_COOKIE_SECURE=true',
  'Отменить изменения': 'Discard changes', 'Есть несохранённые изменения': 'Unsaved changes',
  'Сообщение отправлено': 'Message sent', 'Нет изменений': 'No changes', 'Сохранено:': 'Saved:',

  // ---- пользователи
  'пароль не задан': 'no password', 'временный пароль': 'temporary password', 'активен': 'active', '(вы)': '(you)',
  'администратор': 'administrator', 'просмотр': 'viewer', 'Выдать временный пароль': 'Issue a temporary password',
  'Добавить пользователя': 'Add user', 'Роль': 'Role', 'Последний вход': 'Last login',
  'Администратор управляет устройствами, настройками и пользователями, создаёт, удаляет и восстанавливает бэкапы. Просмотр — только список, просмотр и скачивание бэкапов.':
    'An administrator manages devices, settings and users, and creates, deletes and restores backups. A viewer can only list, preview and download backups.',
  'Роль изменена': 'Role changed', 'Временный пароль': 'Temporary password', 'Другой': 'Regenerate',
  'Передайте пользователю. При первом входе он придумает свой пароль.': 'Give it to the user. On first login they will choose their own password.',
  'Новый пользователь': 'New user', 'Пользователь создан': 'User created', 'Временный пароль для': 'Temporary password for',
  'Текущие сессии пользователя будут завершены.': "The user's current sessions will be ended.",
  'Выдать': 'Issue', 'Временный пароль выдан': 'Temporary password issued', 'Пользователь удалён': 'User deleted',

  // ---- аудит
  'вход': 'login', 'неудачный вход': 'failed login', 'пароль задан': 'password set', 'смена пароля': 'password change',
  'настройки': 'settings', 'устройство добавлено': 'device added', 'устройство изменено': 'device changed',
  'устройство удалено': 'device deleted', 'пользователь создан': 'user created', 'смена роли': 'role change',
  'пользователь удалён': 'user deleted', 'ручной бэкап': 'manual backup', 'бэкап удалён': 'backup deleted',
  'удаление бэкапов': 'bulk delete', 'восстановление': 'restore', 'скачивание': 'download', 'запуск всех': 'run all',
'последние 300 событий': 'last 300 events',
  'Время': 'Time', 'Действие': 'Action', 'Подробности': 'Details',
};

const LANGS = { en: EN };

function readPref(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writePref(key, value) {
  try { localStorage.setItem(key, value); } catch { /* приватный режим */ }
}

const LANG = (() => {
  const saved = readPref('mtb-lang');
  if (saved === 'ru' || saved === 'en') return saved;
  return (navigator.language || 'ru').toLowerCase().startsWith('ru') ? 'ru' : 'en';
})();
const LOCALE = LANG === 'en' ? 'en-GB' : 'ru-RU';
document.documentElement.lang = LANG;

function t(text) {
  const dict = LANGS[LANG];
  return (dict && Object.prototype.hasOwnProperty.call(dict, text)) ? dict[text] : text;
}

function setLang(lang) {
  writePref('mtb-lang', lang);
  location.reload();            // проще и надёжнее, чем перерисовывать всё на лету
}

/* Статический текст index.html: текстовые узлы и placeholder/title/aria-label */
function translateStatic(root = document.body) {
  if (LANG === 'ru') return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const raw = n.nodeValue, key = raw.trim();
    if (key && /[А-Яа-яЁё]/.test(key)) n.nodeValue = raw.replace(key, t(key));
  }
  for (const el of root.querySelectorAll('[placeholder],[title],[aria-label]')) {
    for (const a of ['placeholder', 'title', 'aria-label']) {
      const v = el.getAttribute(a);
      if (v && /[А-Яа-яЁё]/.test(v)) el.setAttribute(a, t(v.trim()));
    }
  }
}

/* ---------------------------------------------------------------- тема */

const THEMES = ['auto', 'light', 'dark'];
const THEME_ICON = {
  auto: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
  light: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
  dark: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
};
const THEME_TITLE = { auto: 'Тема: как в системе', light: 'Тема: светлая', dark: 'Тема: тёмная' };
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

function themeMode() {
  const m = readPref('mtb-theme');
  return THEMES.includes(m) ? m : 'auto';
}

function applyTheme() {
  const mode = themeMode();
  const dark = mode === 'dark' || (mode === 'auto' && darkQuery.matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

function updateThemeButtons() {
  const mode = themeMode();
  for (const b of document.querySelectorAll('[data-act=theme]')) {
    b.innerHTML = `<svg class="i" viewBox="0 0 24 24">${THEME_ICON[mode]}</svg>`;
    b.title = t(THEME_TITLE[mode]);
  }
  for (const b of document.querySelectorAll('[data-act=lang]')) {
    b.textContent = LANG === 'ru' ? 'EN' : 'RU';
    b.title = LANG === 'ru' ? 'English' : 'Русский';
  }
}

function cycleTheme() {
  const next = THEMES[(THEMES.indexOf(themeMode()) + 1) % THEMES.length];
  writePref('mtb-theme', next);
  applyTheme(); updateThemeButtons();
}

darkQuery.addEventListener('change', () => { if (themeMode() === 'auto') applyTheme(); });
applyTheme();
