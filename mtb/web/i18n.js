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
  'Уведомления': 'Notifications', 'Добавить канал': 'Add channel', 'Проверить': 'Test',
  'Форматы URL': 'URL formats', 'токен скрыт': 'token hidden', 'Введите URL': 'Enter a URL',
  'Каналов нет — уведомления не отправляются.': 'No channels — notifications are not sent.',
  'Отчёт о прогоне в мессенджер, на почту или в webhook. Каждый канал — одна строка URL.':
    'A run report to a messenger, e-mail or a webhook. Each channel is a single URL.',
  'Общие параметры: title= — заголовок, disabletls=yes — http вместо https, insecure=yes — не проверять сертификат. Спецсимволы в токенах и паролях кодируйте как в URL (@ → %40).':
    'Common parameters: title= sets the title, disabletls=yes uses http instead of https, insecure=yes skips certificate checks. Encode special characters in tokens and passwords as in a URL (@ → %40).',
  'Отправить тестовое сообщение': 'Send a test message',
  'Сначала сохраните настройки. Уведомления приходят при ошибках и изменениях.': 'Save the settings first. Notifications are sent on errors and changes.',
  'Язык уведомлений': 'Notification language',
  'Веб-интерфейс': 'Web interface', 'Разрешить восстановление (/import по SSH) из списка бэкапов': 'Allow restore (/import over SSH) from the backup list',
  'Cookie сессии': 'Session cookie', 'с флагом Secure (HTTPS)': 'has the Secure flag (HTTPS)',
  'без флага Secure — для работы через HTTPS за прокси задайте WEB_COOKIE_SECURE=true': 'has no Secure flag — behind an HTTPS proxy, set WEB_COOKIE_SECURE=true',
  'Отменить изменения': 'Discard changes', 'Есть несохранённые изменения': 'Unsaved changes',
  'Сообщение отправлено': 'Message sent', 'Нет изменений': 'No changes', 'Сохранено:': 'Saved:',

  // ---- версия и обновления
  'Обновления': 'Updates', 'Проверять новые версии на GitHub (раз в 6 часов)': 'Check GitHub for new versions (every 6 hours)',
  'Канал': 'Channel', 'авто: пре-релизы, если установлен пре-релиз': 'auto: pre-releases if a pre-release is installed',
  'только стабильные': 'stable only', 'включая пре-релизы': 'including pre-releases',
  'Проверить сейчас': 'Check now', 'Подробнее': 'Details', 'Доступна версия': 'Version available',
  'Установлена последняя версия': 'You are on the latest version', 'Установлена последняя версия.': 'You are on the latest version.',
  'Примечания к этой версии': 'Release notes for this version', 'ещё не проверялось': 'not checked yet',
  'Установлена': 'Installed', 'проверено:': 'checked:', 'доступна': 'available', 'обновлений нет': 'up to date',
  'бинарник (install.sh)': 'binary (install.sh)', 'из исходников': 'from source',
  'Обновление': 'Update', 'Доступна': 'Available', 'Последняя': 'Latest', 'пре-релиз': 'pre-release',
  'Бинарник будет скачан с GitHub, проверен по SHA256 и заменён. Сервис перезапустится сам; если идёт бэкап — после его окончания. Предыдущая версия сохранится как':
    'The binary will be downloaded from GitHub, verified with SHA256 and replaced. The service restarts by itself — after the current backup, if one is running. The previous version is kept as',
  'Позже': 'Later', 'Обновить до': 'Update to', 'Обновляет администратор.': 'An administrator performs updates.',
  'Способ установки:': 'Installation method:', 'Обновление выполняется командой на сервере:': 'Update by running this on the server:',
  'Репозиторий:': 'Repository:', 'Что нового': "What's new", 'на GitHub': 'on GitHub', '(описание не заполнено)': '(no description)',
  'Скачивание и проверка…': 'Downloading and verifying…', 'Обновление до': 'Updating to',
  'Новая версия установлена. Ждём окончания текущего бэкапа, затем перезапуск…': 'New version installed. Waiting for the current backup to finish, then restarting…',
  'Новая версия установлена. Перезапуск…': 'New version installed. Restarting…', 'Обновлено до': 'Updated to',
  'Сервис не вернулся с новой версией. Проверьте journalctl -u mtb.': 'The service did not come back with the new version. Check journalctl -u mtb.',
  'обновление': 'update', 'ошибка обновления': 'update failed',

  // ---- удаление git-бэкапов, переименование
  'Коммит останется в истории git и в Gitea': 'The commit stays in git history and in Gitea',
  'Убрать из списка?': 'Remove from list?', 'Убрать из списка (коммит останется в истории git)': 'Remove from list (the commit stays in git history)',
  'бэкапы из истории git будут убраны из списка, коммиты останутся': 'backups from git history will be removed from the list; the commits remain',
  'Будет убрано из списка': 'This will remove from the list',
  'Коммиты останутся в истории git и в Gitea: git не удаляет историю.': 'The commits stay in git history and in Gitea: git does not delete history.',
  'Бэкап убран из списка': 'Backup removed from the list', 'бэкап убран из списка': 'backup removed from list',
  'устройство переименовано': 'device renamed', 'ошибка переименования': 'rename failed',

  'Прежние имена': 'Former names',
  'Бэкапы и журнал под этими именами показываются у этого устройства. При переименовании старое имя добавляется сюда само.':
    "Backups and run history under these names are shown for this device. On rename, the old name is added here automatically.",
  'прежние имена': 'former names',

  // ---- форма устройства (двухстрочные подписи)
  'Только конфиг': 'Config only', '(без .backup и сертификатов)': '(no .backup or certificates)',
  'Разрешить слабые ключи': 'Allow weak keys', '(ключ сертификата 1024 бит)': '(1024-bit certificate key)',
  // ---- настройки: описания секций
  'Когда запускать бэкап всех включённых устройств.': 'When to back up all enabled devices.',
  'Где лежат бэкапы и чем шифруются .backup и сертификаты.': 'Where backups are kept and how .backup files and certificates are encrypted.',
  'Push истории бэкапов в репозиторий после каждого прогона.': 'Push the backup history to a repository after every run.',
  'Отчёт о прогоне в чат или канал. Текст сообщения настраивается.': 'A run report to a chat or channel. The message text is customizable.',
  'Новые версии mtb на GitHub.': 'New mtb versions on GitHub.',
  'Не проверять TLS Gitea': "Don't verify Gitea TLS", 'небезопасно: только для отладки': 'insecure: for debugging only',
  'Разрешить восстановление из списка бэкапов': 'Allow restore from the backup list',
  '/import по SSH поверх текущей конфигурации': '/import over SSH on top of the current configuration',
  // ---- шаблоны Telegram
  'Когда отправлять': 'When to send', 'при ошибках и изменениях': 'on errors and changes',
  'только при ошибках': 'on errors only', 'после каждого прогона': 'after every run',
  'Шаблон': 'Template', 'Подробный': 'Detailed', 'Краткий': 'Short', 'Только ошибки': 'Errors only', 'Свой': 'Custom',
  'Текст сообщения': 'Message text',
  'Строки, в которых переменные оказались пустыми (нет изменений, нет ошибок), не отправляются.':
    'Lines whose variables turn out empty (no changes, no errors) are not sent.',
  'Переменные — нажмите, чтобы вставить:': 'Variables — click to insert:',
  'Предпросмотр на примере данных:': 'Preview with sample data:',
  'Отправляется сохранённый шаблон — сначала сохраните настройки.': 'The saved template is sent — save the settings first.',
  '(пустое сообщение)': '(empty message)', 'Неизвестные переменные:': 'Unknown variables:',
  'значок: ✅ успешно, ⚠️ есть ошибки, ❌ всё неудачно': 'icon: ✅ success, ⚠️ some errors, ❌ all failed',
  'mtb или «ручной бэкап»': 'mtb or "manual backup"', 'по расписанию / ручной': 'scheduled / manual',
  'дата прогона': 'run date', 'время прогона': 'run time', 'успешных устройств': 'devices succeeded',
  'всего устройств': 'devices total', 'устройств с ошибкой': 'devices failed', 'устройств с изменениями': 'devices changed',
  'список устройств': 'device list', 'строка «Изменения: …» или пусто': 'a "Changes: …" line, or empty',
  'ошибки по устройствам, по строке на каждую': 'per-device errors, one line each',
  'предупреждения (например, push в Gitea)': 'warnings (for example, Gitea push)', 'версия mtb': 'mtb version',

  'Фиксировать каждый прогон': 'Record every run',
  'В списке бэкапов появляется строка с датой каждого прогона, даже если ничего не изменилось (пустой коммит). Без этого строка появляется только при изменениях.':
    'Every run appears in the backup list with its date, even if nothing changed (an empty commit). Without it, a row appears only when something changed.',
  'Конфигурация такая же, как в предыдущем бэкапе': 'Same configuration as in the previous backup',

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

// Язык: cookie mtb_lang (ставит сервер по профилю пользователя) → localStorage → английский.
function readCookie(name) {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : null;
}
const LANG = (() => {
  for (const v of [readCookie('mtb_lang'), readPref('mtb-lang')]) if (v === 'ru' || v === 'en') return v;
  return 'en';
})();
const LOCALE = LANG === 'en' ? 'en-GB' : 'ru-RU';
document.documentElement.lang = LANG;

function t(text) {
  const dict = LANGS[LANG];
  return (dict && Object.prototype.hasOwnProperty.call(dict, text)) ? dict[text] : text;
}

function setLang(lang) {
  writePref('mtb-lang', lang);
  document.cookie = `mtb_lang=${lang}; Path=/; Max-Age=31536000; SameSite=Strict`;
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
