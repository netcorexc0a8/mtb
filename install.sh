#!/bin/sh
# Установка mtb из релиза GitHub. Всё приложение — в одном каталоге:
#
#   /opt/mtb/bin/mtb       бинарник (mtb.prev — предыдущая версия после обновления из веба)
#   /opt/mtb/mtb.env       необязательные переменные запуска
#   /opt/mtb/mtb.service   unit systemd (подключён ссылкой)
#   /opt/mtb/data/         база, ключ шифрования секретов, known_hosts
#   /opt/mtb/backups/      бэкапы
#
# Снаружи — только ссылки: /usr/local/bin/mtb и unit в /etc/systemd/system.
#
#   curl -fsSL https://github.com/netcorexc0a8/mtb/releases/latest/download/install.sh | sh
#   sh install.sh v0.2.2          конкретная версия
#   sh install.sh --uninstall     остановить и отключить сервис (данные остаются)
#
# Переменные: MTB_DIR (каталог, по умолчанию /opt/mtb), MTB_REPO, MTB_BASE_URL (зеркало релизов).
set -eu

REPO="${MTB_REPO:-netcorexc0a8/mtb}"
DIR="${MTB_DIR:-/opt/mtb}"
LINK=/usr/local/bin/mtb
UNIT_NAME=mtb.service
ACTION=install
VERSION=latest
for arg in "$@"; do
  case "$arg" in
    --uninstall) ACTION=uninstall ;;
    -h|--help) sed -n '2,19p' "$0" 2>/dev/null || true; exit 0 ;;
    v*|[0-9]*) VERSION="v${arg#v}" ;;
    *) echo "Неизвестный аргумент: $arg"; exit 1 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "Запустите от root"; exit 1; }
[ "$(uname -s)" = Linux ] || { echo "Поддерживается только Linux"; exit 1; }
HAS_SYSTEMD=0
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then HAS_SYSTEMD=1; fi

# ---------------------------------------------------------------- удаление
if [ "$ACTION" = uninstall ]; then
  if [ "$HAS_SYSTEMD" = 1 ]; then
    systemctl disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/$UNIT_NAME"
    systemctl daemon-reload
  fi
  [ -L "$LINK" ] && rm -f "$LINK"
  echo "Сервис остановлен и отключён. Данные и бэкапы остались в $DIR."
  echo "Удалить полностью:  rm -rf $DIR && userdel mtb"
  exit 0
fi

# ---------------------------------------------------------------- установка
case "$(uname -m)" in
  x86_64|amd64)  ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "Архитектура $(uname -m) не поддерживается (нужна x86_64 или aarch64)"; exit 1 ;;
esac

if [ -n "${MTB_BASE_URL:-}" ]; then
  BASE="${MTB_BASE_URL%/}"
elif [ "$VERSION" = latest ]; then
  BASE="https://github.com/$REPO/releases/latest/download"
else
  BASE="https://github.com/$REPO/releases/download/$VERSION"
fi

fetch() {  # fetch URL FILE
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then wget -qO "$2" "$1"
  else echo "Нужен curl или wget"; exit 1; fi
}

# Старая раскладка (до одного каталога): не трогаем, подсказываем перенос
if [ -d /var/lib/mtb/data ] && [ ! -d "$DIR/data" ]; then
  cat <<MSG
!! Найдена установка в старой раскладке (/var/lib/mtb, /etc/mtb).
   Перенесите данные в $DIR и запустите установку снова:
     systemctl disable --now mtb; rm -f /etc/systemd/system/mtb.service
     mkdir -p $DIR && mv /var/lib/mtb/data /var/lib/mtb/backups $DIR/
     [ -f /etc/mtb/mtb.env ] && mv /etc/mtb/mtb.env $DIR/
     rm -rf /var/lib/mtb /etc/mtb /opt/mtb/mtb /opt/mtb/mtb.prev
MSG
  exit 1
fi

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
ASSET="mtb-linux-$ARCH"
echo ">> Загрузка $ASSET ($VERSION)"
fetch "$BASE/$ASSET" "$TMP/$ASSET" || {
  echo "!! Не удалось скачать $BASE/$ASSET"
  [ "$VERSION" = latest ] && echo "   Если опубликованы только пре-релизы, укажите версию явно: sh install.sh v0.2.2-rc.1"
  exit 1; }
fetch "$BASE/SHA256SUMS" "$TMP/SHA256SUMS"
(cd "$TMP" && grep " $ASSET\$" SHA256SUMS | sha256sum -c - >/dev/null) || { echo "!! Контрольная сумма не совпала"; exit 1; }
chmod 0755 "$TMP/$ASSET"
"$TMP/$ASSET" --version >/dev/null || { echo "!! Бинарник не запускается на этой системе"; exit 1; }

if ! id mtb >/dev/null 2>&1; then
  useradd --system --home-dir "$DIR" --no-create-home --shell /usr/sbin/nologin mtb
fi

# Каталоги: корень и служебные файлы — root; bin/ data/ backups/ — пользователь сервиса
# (bin/ — чтобы сервис мог обновить себя из веб-интерфейса).
install -d -m 0755 -o root -g root "$DIR"
install -d -m 0755 -o mtb -g mtb "$DIR/bin"
install -d -m 0700 -o mtb -g mtb "$DIR/data" "$DIR/backups"

WAS_ACTIVE=0
[ "$HAS_SYSTEMD" = 1 ] && systemctl is-active --quiet "$UNIT_NAME" && WAS_ACTIVE=1
install -m 0755 -o mtb -g mtb "$TMP/$ASSET" "$DIR/bin/mtb.new"
mv -f "$DIR/bin/mtb.new" "$DIR/bin/mtb"
ln -sfn "$DIR/bin/mtb" "$LINK"
echo ">> Установлено: $("$DIR/bin/mtb" --version) → $DIR"

if [ ! -f "$DIR/mtb.env" ]; then
  fetch "$BASE/mtb.env.example" "$DIR/mtb.env" 2>/dev/null || : > "$DIR/mtb.env"
  chown root:mtb "$DIR/mtb.env"; chmod 0640 "$DIR/mtb.env"
fi

if [ "$HAS_SYSTEMD" = 1 ]; then
  fetch "$BASE/mtb.service" "$TMP/mtb.service"
  [ "$DIR" = /opt/mtb ] || sed -i "s#/opt/mtb#$DIR#g" "$TMP/mtb.service"
  install -m 0644 -o root -g root "$TMP/mtb.service" "$DIR/mtb.service"
  rm -f "/etc/systemd/system/$UNIT_NAME"
  systemctl link "$DIR/mtb.service" >/dev/null
  systemctl daemon-reload
  systemctl enable "$UNIT_NAME" >/dev/null 2>&1
  systemctl restart "$UNIT_NAME"
  sleep 2
  if systemctl is-active --quiet "$UNIT_NAME"; then
    [ "$WAS_ACTIVE" = 1 ] && echo ">> Сервис перезапущен на новой версии" || echo ">> Сервис запущен"
  else
    echo "!! Сервис не запустился: journalctl -u mtb -e"
  fi
else
  echo "!! systemd не найден — запустите вручную: runuser -u mtb -- $DIR/bin/mtb serve"
fi

command -v git >/dev/null 2>&1 || echo "!! git не найден: установите его (apt install git) — нужен для хранения git и push в Gitea"

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<MSG

Готово. Откройте веб-интерфейс: http://${IP:-<адрес-сервера>}:8080
  Логин admin — пароль вы зададите при первом входе.
  Сделайте это сразу: пока пароль не задан, его может задать любой, кто откроет страницу.

Всё лежит в $DIR. Команды работают без настроек путей:
  mtb check                    проверить доступ к устройствам
  mtb reset-password admin     сбросить пароль администратора
  journalctl -u mtb -f         логи
Удаление:  sh install.sh --uninstall   (данные останутся в $DIR)
MSG
