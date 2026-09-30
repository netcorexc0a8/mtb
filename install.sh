#!/bin/sh
# Установка mtb из релиза GitHub как systemd-сервиса.
#   curl -fsSL https://github.com/netcorexc0a8/mtb/releases/latest/download/install.sh | sudo sh
#   sudo sh install.sh v1.2.0        # конкретная версия
set -eu

REPO="${MTB_REPO:-netcorexc0a8/mtb}"
VERSION="${1:-latest}"
OPT=/opt/mtb
BIN=$OPT/mtb
LINK=/usr/local/bin/mtb
ETC=/etc/mtb
VAR=/var/lib/mtb
UNIT=/etc/systemd/system/mtb.service

[ "$(id -u)" -eq 0 ] || { echo "Запустите от root (sudo)"; exit 1; }

case "$(uname -m)" in
  x86_64|amd64)  ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "Архитектура $(uname -m) не поддерживается"; exit 1 ;;
esac

if [ "$VERSION" = latest ]; then
  BASE="https://github.com/$REPO/releases/latest/download"
else
  BASE="https://github.com/$REPO/releases/download/$VERSION"
fi

fetch() {  # fetch URL FILE
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then wget -qO "$2" "$1"
  else echo "Нужен curl или wget"; exit 1; fi
}

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
ASSET="mtb-linux-$ARCH"
echo ">> Загрузка $ASSET ($VERSION)"
fetch "$BASE/$ASSET" "$TMP/$ASSET"
fetch "$BASE/SHA256SUMS" "$TMP/SHA256SUMS"
(cd "$TMP" && grep " $ASSET\$" SHA256SUMS | sha256sum -c -) || { echo "Контрольная сумма не совпала"; exit 1; }
if ! id mtb >/dev/null 2>&1; then
  useradd --system --home-dir "$VAR" --shell /usr/sbin/nologin mtb
fi
# Бинарник принадлежит пользователю сервиса — так его можно обновить из веб-интерфейса.
# Команда mtb в PATH — ссылка на него.
install -d -m 0755 -o mtb -g mtb "$OPT"
install -m 0755 -o mtb -g mtb "$TMP/$ASSET" "$BIN"
ln -sfn "$BIN" "$LINK"
echo ">> Установлено: $("$BIN" --version)"
install -d -m 0750 -o root -g mtb "$ETC"
install -d -m 0700 -o mtb -g mtb "$VAR" "$VAR/backups" "$VAR/data"

if [ ! -f "$ETC/mtb.env" ]; then
  fetch "$BASE/mtb.env.example" "$ETC/mtb.env"
  chown root:mtb "$ETC/mtb.env"; chmod 0640 "$ETC/mtb.env"
fi

if command -v systemctl >/dev/null 2>&1; then
  fetch "$BASE/mtb.service" "$UNIT"
  systemctl daemon-reload
  systemctl enable mtb >/dev/null 2>&1
  systemctl restart mtb          # при повторном запуске — перезапуск на новой версии
  sleep 2
  systemctl is-active --quiet mtb && echo ">> Сервис запущен" || echo "!! Сервис не запустился: journalctl -u mtb -e"
fi

command -v git >/dev/null 2>&1 || echo "!! git не найден: установите его (apt install git) — нужен для хранения git и push в Gitea"

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<MSG

Готово. Откройте веб-интерфейс: http://${IP:-<адрес-сервера>}:8080
  Логин admin — пароль вы зададите при первом входе.
  Сделайте это сразу: пока пароль не задан, его может задать любой, кто откроет страницу.

Дальше всё настраивается в интерфейсе: устройства, расписание, хранение, Gitea, Telegram.
  Логи:                 journalctl -u mtb -f
  Забыли пароль admin:  sudo -u mtb env DATA_DIR=$VAR/data mtb reset-password admin
MSG
