# mtb

**English** | [Русский](README.ru.md)

> 📖 **The primary, most detailed documentation is in Russian: [README.ru.md](README.ru.md).** This English version covers the same content. The web interface is in Russian.

A service for daily backups of MikroTik RouterOS 7 devices, with a web interface. Each run collects:

- a text configuration export **including passwords and keys**;
- an encrypted binary backup;
- certificates with their private keys.

Everything is configured in the browser: devices, schedule, storage, Gitea, Telegram and users. Settings live in SQLite, with device passwords and tokens encrypted. Backups are stored in a folder, either as current state with git history or as dated snapshots, and pushing to a self-hosted Gitea is optional.

It ships as a single binary on GitHub Releases (Linux amd64/arm64, Windows) and as a Docker image. No Python, no external database and no CDN are needed, so it also works in air-gapped networks.

![Backups](docs/web-backups.png)

## Features

- **Export** via `/export show-sensitive terse`: every line is a complete command, which keeps diffs readable.
- **Binary** `/system backup save` with a password, for a one-to-one restore.
- **Certificates** with a private key are exported as `.p12` or PEM, plus an index of all certificates.
- **Three transports**, chosen per device: API-SSL + SFTP, API-SSL only, or SSH only. In SSH mode the config is read from `/export` output, so no files are created on the router.
- **Storage:** current state with git history, or a dated snapshot folder per run with rotation. Pushing to Gitea is optional.
- **Web interface:**
  - backups: filters, preview, comparing two copies, manual backup, delete, restore;
  - devices, with access and transport checks;
  - run history, settings, users with roles, audit log.
- **First login:** an `admin` user is created, and you choose its password on the first login.
- **Telegram notifications** on errors and changes.

## Contents

- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [What is stored](#what-is-stored)
- [Preparing MikroTik](#preparing-mikrotik)
- [Installation](#installation)
- [Web interface](#web-interface)
- [Device settings](#device-settings)
- [General settings](#general-settings)
- [Environment variables](#environment-variables)
- [Transport modes](#transport-modes)
- [Storage and Gitea](#storage-and-gitea)
- [Commands](#commands)
- [Migrating from 1.x](#migrating-from-1x)
- [Restore](#restore)
- [Security](#security)
- [Backing up mtb itself](#backing-up-mtb-itself)
- [Upgrading](#upgrading)
- [Troubleshooting](#troubleshooting)
- [Development and build](#development-and-build)

## Quick start

**Docker Compose:**

```bash
mkdir -p mtb/{data,backups} && cd mtb
curl -fsSLO https://raw.githubusercontent.com/netcorexc0a8/mtb/main/docker-compose.yml
PUID=$(id -u) PGID=$(id -g) docker compose up -d
```

**Linux binary (systemd):**

```bash
curl -fsSL https://github.com/netcorexc0a8/mtb/releases/latest/download/install.sh | sudo sh
```

Then:

1. Open `http://<server>:8080`. The first-login form appears right away: the login is `admin`; choose a password and confirm it.
2. **Устройства → Добавить устройство** (Devices → Add device): enter the address, RouterOS user, password and transport. For API-SSL, click "Получить с устройства" (Fetch from device) to fill in the certificate fingerprint.
3. **Настройки → Хранение** (Settings → Storage): set the backup encryption passphrase.
4. **Журнал → Запустить сейчас** (Runs → Run now), or wait for the schedule (daily at 03:00 by default).

![First login](docs/web-first-run.png)

> ⚠️ Until the `admin` password is set, whoever opens the page first can set it. Do it immediately after installing. If the service is reachable from outside, do the first login through an SSH tunnel: `ssh -L 8080:127.0.0.1:8080 server`.

## How it works

On schedule, for each device:

1. Connect over **API-SSL** (8729) with TLS certificate verification, or over **SSH** (22), depending on the transport.
2. Export the configuration (`/export show-sensitive terse`), run `system backup save` with a password, and export certificates that have a private key.
3. Fetch the files over SFTP or via the API `/file/read`. In SSH mode, the config is taken directly from `/export` output.
4. Delete the temporary `mtbk-*` files from the router, including when the run fails.
5. Write the result to the backup folder as a git commit or a snapshot, and push to Gitea if configured.
6. Record the outcome in the run history, and send a Telegram message if something changed or failed.

Settings are re-read from the database before every run. Changes made in the UI, including the schedule, take effect without a restart.

## What is stored

With **git** storage (default), each device folder holds the current state, and git holds the history:

```
backups/
├── core-rtr1/
│   ├── config.rsc          # export with secrets; date header line removed
│   ├── system.backup       # encrypted with the backup passphrase
│   ├── meta.json           # identity and RouterOS version
│   └── certs/
│       ├── index.json      # all certificates: name, CN, fingerprint, expiry
│       └── vpn-server.p12  # or .crt + .key (PEM format)
└── branch-rtr2/…
```

When files are rewritten:

- `config.rsc` is rewritten only when the configuration changes; the date header line is removed.
- `system.backup` is updated together with the config.
- Certificates are updated only when their index changes.

RouterOS uses a fresh salt for `.backup` and `.p12` on every export, so rewriting them daily would bloat the history without any real change.

With **snapshots** storage, every run creates a `<device>/<YYYY-MM-DD_HHMMSS>/` folder with all files, and old snapshots are rotated out.

With "config only", there is no `system.backup` and no `certs/` in either mode.

> ⚠️ RouterOS never includes `/user` passwords in `export`, not even with `show-sensitive`. They exist only in `system.backup`.

## Preparing MikroTik

In the examples, `10.10.10.5` is the mtb server.

**1. API-SSL certificate.** Not needed with the "SSH only" transport. The key must be at least 2048 bits.

```routeros
/certificate add name=api-ssl common-name=core-rtr1 days-valid=3650 key-size=2048 \
    key-usage=digital-signature,key-encipherment,tls-server
/certificate sign api-ssl
/ip service set api-ssl certificate=api-ssl address=10.10.10.5/32 disabled=no
```

**2. SSH.** Not needed with the "API only" transport.

```routeros
/ip service set ssh address=10.10.10.5/32,<your management addresses>
```

**3. Group and user.**

```routeros
/user group add name=backup policy=read,write,policy,test,sensitive,api,ssh,ftp
/user add name=backup group=backup address=10.10.10.5/32 password="<password>"
```

The minimal set of policies depends on the mode, and the device's "Проверить доступ" (Check access) button shows what is missing. For example, "SSH only" + "config only" needs just `read,sensitive,ssh`.

| Policy | Why it is needed |
|---|---|
| `read`, `sensitive` | Export including passwords and keys. |
| `write`, `ftp` | Creating, reading and deleting temporary files. |
| `policy`, `test` | `system backup save` and certificates. |
| `api` / `ssh` | Connecting with the chosen transport. |

**4. Certificate fingerprint.** The "Получить с устройства" button in the device form fills it in. Compare it with `/certificate print detail` on the router to rule out interception.

## Installation

### Linux binary (systemd)

The binary is self-contained and runs on glibc 2.28 or newer: Debian 10+, Ubuntu 20.04+, Astra Linux 1.7+, RHEL/Alma 8+. The host needs `git` for git storage and Gitea push.

```bash
curl -fsSL https://github.com/netcorexc0a8/mtb/releases/latest/download/install.sh | sudo sh
# a specific version:
curl -fsSLO https://github.com/netcorexc0a8/mtb/releases/latest/download/install.sh && sudo sh install.sh v2.0.0
```

What the script does:

- verifies the binary against `SHA256SUMS` and installs it to `/usr/local/bin/mtb`;
- creates the `mtb` system user and `/var/lib/mtb/{data,backups}` with mode 0700;
- installs and starts `mtb.service`.

Optional startup variables go in `/etc/mtb/mtb.env`. Logs: `journalctl -u mtb -f`.

**Manually, in any folder:**

```bash
curl -fsSLo mtb https://github.com/netcorexc0a8/mtb/releases/latest/download/mtb-linux-amd64
chmod +x mtb && ./mtb
```

The database and backups are created in `./data` and `./backups`.

### Windows

1. Download `mtb-windows-amd64.exe` from [Releases](https://github.com/netcorexc0a8/mtb/releases) and put it in `C:\mtb\`.
2. For git storage, install [Git for Windows](https://git-scm.com/download/win), or choose snapshots storage in the settings.
3. Run `mtb-windows-amd64.exe serve` from `C:\mtb` and open `http://localhost:8080`.
4. To keep it running, set it up as a service, for example with NSSM, using `C:\mtb` as the working directory.

### Docker Compose

The `ghcr.io/netcorexc0a8/mtb` image is built for linux/amd64 and linux/arm64.

```bash
mkdir -p mtb/{data,backups} && cd mtb
curl -fsSLO https://raw.githubusercontent.com/netcorexc0a8/mtb/main/docker-compose.yml
echo "PUID=$(id -u)" > .env && echo "PGID=$(id -g)" >> .env
docker compose up -d && docker compose logs -f
```

| Host path | In container | Purpose |
|---|---|---|
| `./data` | `/data` | SQLite, secret encryption key, `known_hosts`. |
| `./backups` | `/backups` | Backups. |

The port is published on `127.0.0.1:8080`. Expose it only through a reverse proxy with TLS, and set `WEB_COOKIE_SECURE=true`. The image HEALTHCHECK polls `/healthz`.

Without Compose:

```bash
docker run -d --name mtb --restart unless-stopped --init --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:8080:8080 -v "$PWD/data:/data" -v "$PWD/backups:/backups" \
  ghcr.io/netcorexc0a8/mtb:latest
```

## Web interface

The UI is in Russian; English section names are given in parentheses.

| Section | Contents | Who can use it |
|---|---|---|
| **Бэкапы** (Backups) | Filtered list, preview, comparing two copies, downloading any file of a backup, manual backup, delete, restore. | Everyone: view and download. Admins: everything else. |
| **Устройства** (Devices) | List with the last backup status. Add and edit, check access, check transports (`probe`), back up now. | Everyone: list. Admins: changes. |
| **Журнал** (Runs) | Run history: successes, changes, per-device errors. "Run now" button. | Everyone. |
| **Настройки** (Settings) | Schedule, storage and encryption, Gitea, Telegram, restore from the UI. | Admins. |
| **Пользователи** (Users) | Admin and view-only roles, temporary passwords. | Admins. |
| **Аудит** (Audit) | Logins, settings and device changes, downloads, deletions, restores. | Admins. |

![Devices](docs/web-devices.png)

**Comparing backups.** Select exactly two and click "Сравнить" (Compare). The diff always reads from older to newer. By default only changes with context are shown; "Весь файл" (Whole file) expands the rest.

![Compare](docs/web-diff.png)

**Users and passwords:**

- On first start, `admin` is created without a password. The password (at least 10 characters) is chosen and confirmed on the first login.
- For new users, an admin issues a temporary password. On first login the user enters it and chooses their own.
- The "issue a temporary password" button resets a forgotten password and ends that user's sessions.
- You can change your own password from the user menu; this ends your other sessions.
- If the only admin's password is lost, run `mtb reset-password admin` on the server. On the next login you will be asked to set a new one.

## Device settings

Set in the form under **Устройства → Добавить / Изменить** (Devices → Add / Edit).

| Field | Default | Description |
|---|---|---|
| Name | — | Unique: Latin letters, digits, `. _ -`. Also the name of the backup folder. |
| Address, user, password | — | RouterOS access. The password is stored encrypted and never returned to the UI. |
| Enabled in schedule | yes | Disabled devices are skipped by the schedule but can still be backed up manually. |
| Transport | API + SFTP | API + SFTP, API-SSL only, or SSH only. See [Transport modes](#transport-modes). |
| Config only | no | No `system.backup` and no certificates. |
| Binary files via API | base64 | For "API only": `base64`, `raw` or "don't fetch". |
| Certificate format | auto | PKCS#12 or PEM. |
| Which certificates | all with a key | All, only the listed ones, or none. |
| TLS verification | fingerprint | SHA-256 fingerprint, your own certificate or CA in PEM, or "don't verify". Not needed for "SSH only". |
| Weak keys | no | Allow API-SSL certificates with 1024-bit keys. |
| Ports, timeout | 8729, 22, 30 s | |
| Encoding | UTF-8 | Windows-1251 if names and comments were typed in Cyrillic via Winbox. |

## General settings

The **Настройки** (Settings) section, admins only.

| Group | Parameters |
|---|---|
| Schedule | Cron expression (default `0 3 * * *`), time zone, how many devices to poll in parallel. Shows the next run time. |
| Storage and encryption | Passphrase for `.backup` and certificates. Mode: git or snapshots. For git: whether to keep history. For snapshots: retention, minimum kept, "only on changes". |
| Gitea | Repository URL, user, token, branch, commit author, CA in PEM, disabling TLS verification. |
| Telegram | Bot token, `chat_id`, "send a test message" button. |
| Web interface | Allow restore (`/import`) from the backup list. Off by default. |

Secrets (the passphrase and tokens) are never sent back to the UI; you only see "set" or "not set". Leaving the field empty on save keeps the current value, and the "delete" checkbox clears it.

## Environment variables

These are only needed to start the service. Everything else is configured in the UI.

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `data` (Docker: `/data`) | The `mtb.db` database, `secret.key`, `known_hosts`. |
| `BACKUP_DIR` | `backups` (Docker: `/backups`) | Backup folder. |
| `WEB_LISTEN` | `0.0.0.0:8080` | Web UI address. |
| `WEB_TLS_CERT` / `WEB_TLS_KEY` | — | HTTPS without a reverse proxy. |
| `WEB_COOKIE_SECURE` | `auto` | The Secure flag on the session cookie. `auto` turns it on when `WEB_TLS_CERT` is set. Use `true` behind an HTTPS proxy. |
| `LOG_LEVEL` | `INFO` | Log level. |

They can be set in the environment, in `.env` in the working directory, or in a file passed with `-e`.

## Transport modes

| | API + SFTP (default) | API only | SSH only |
|---|---|---|---|
| Commands | API-SSL | API-SSL | SSH exec |
| Config | file → SFTP | file → `/file/read` | `/export` output, no file |
| `.backup`, certificates | SFTP | via `api_binary` | SFTP in the same session |
| Ports | 8729 + 22 | 8729 only | 22 only |
| Host verification | TLS + SSH (TOFU) | TLS | SSH (TOFU) |
| RouterOS | any 7.x | 7.13+ | any 7.x |

In "API only" mode, binary files need a workaround because the API works with strings:

- **`base64`**: the router encodes file chunks itself;
- **`raw`**: raw bytes over a `latin-1` connection;
- **"don't fetch"**: no `.backup`, and certificates are exported as PEM.

The **"Проверить транспорты"** (Check transports) button in the device form, the same as `mtb probe`, shows what works on a given router. It creates temporary files, reads them with every method, compares against an SFTP reference and suggests settings.

The simplest mode is "SSH only" + "config only": one SSH command per device, nothing created on the router, and only `read,sensitive,ssh` policies needed.

## Storage and Gitea

**Git** (default). The folder holds the current state and the local git repository holds the history, so `git log -p` and `git diff` work directly in `backups/`. Turning off "keep history" leaves only the latest files.

**Snapshots.** Every run creates a dated folder with a full copy of everything collected.

- Snapshots older than the retention period are deleted, but the minimum number of newest snapshots is always kept, even if a router has been unreachable for a long time.
- "Only on changes" creates a snapshot only when the config, the RouterOS version or the certificates changed.
- Deleting backups from the UI is available only in this mode: git commits are never deleted.

**Gitea** (git storage only):

1. Create a private repository and a user with write access.
2. Create a token for that user under *Settings → Applications → Access Tokens* with the `write:repository` scope.
3. Enter the URL, user and token under **Настройки → Gitea**.

How push works:

- The token is passed to git through environment variables and never lands in `.git/config`.
- Push runs on every run and catches up on failed earlier pushes.
- A failed push does not count as a failed backup; the run history marks it as a warning.

## Commands

```
mtb [--data-dir DIR] [-e ENV_FILE] [--log-level LEVEL] [COMMAND]

  serve                   schedule + web UI (default; alias: daemon)
  scheduler               schedule only, no web UI
  run [-d NAME ...]       single run, then exit; without -d, all enabled devices
  check [-d NAME ...]     check access and permissions without exporting
  probe [-d NAME ...] [--no-sftp]
                          test which file transport works
  fingerprint HOST[:PORT] fingerprint, expiry and PEM of the API-SSL certificate
  import-config -c devices.yaml [--replace]
                          migrate a 1.x configuration
  reset-password [USER]   reset a password (admin by default)
  -V, --version
```

Commands use the same database as the service, so pass the same `DATA_DIR`. Under systemd:

```bash
sudo -u mtb env DATA_DIR=/var/lib/mtb/data mtb check
```

In Docker: `docker compose exec mtb mtb check`.

## Migrating from 1.x

Version 1.x was configured with `devices.yaml` and `.env`. To import them into the database:

```bash
# binary / systemd
sudo -u mtb env DATA_DIR=/var/lib/mtb/data \
  mtb -e /old/.env import-config -c /old/config/devices.yaml

# Docker: put the old files into ./data/old/ and run
docker compose exec mtb mtb -e /data/old/.env import-config -c /data/old/devices.yaml
```

What gets imported:

- **Devices.** Passwords come from `MT_PASSWORD` and `password_env`, and `tls_ca` is read as the contents of the PEM file.
- **General settings** from the variables (`SCHEDULE`, `BACKUP_PASSPHRASE`, `STORAGE`, `GITEA_*`, `TELEGRAM_*`, and so on).

Existing devices are skipped unless you pass `--replace`. The backup folder stays as is: git history and snapshots are picked up unchanged. The old `WEB_USER` and `WEB_PASSWORD` are no longer used — log in as `admin` and set a password.

## Restore

All files are encrypted with the backup passphrase. Upload a file to the router via Winbox (*Files*) or SFTP.

```routeros
# binary backup — same device or model; the router reboots
/system backup load name=system.backup password="<passphrase>"

# certificates
/certificate import file-name=vpn-server.p12 passphrase="<passphrase>"
/certificate import file-name=vpn-server.crt
/certificate import file-name=vpn-server.key passphrase="<passphrase>"
```

**Text export** onto a reset or different device:

1. Run `/system reset-configuration no-defaults=yes skip-backup=yes`.
2. Connect via Winbox using the MAC address.
3. Upload the certificate files and `config.rsc`.
4. Import the certificates first, because `ip service`, IPsec and other sections reference them.
5. Run `/import file-name=config.rsc`.
6. Set the `/user` passwords again.

If restore is enabled in the settings, the "Восстановить" (Restore) button in the backup list uploads the `.rsc` over SSH and runs `/import`, showing the output in a dialog. `/import` applies the script on top of the current config, so this button is meant for a reset device or partial scripts.

## Security

- **Backups contain passwords, PSKs and private keys in plain text.** The backup folder is created with mode 0700, and the Gitea repository must be private.
- **Secrets in the database** (device passwords, the passphrase, tokens) are encrypted with `DATA_DIR/secret.key` (Fernet: AES + HMAC). The key is created on first start with mode 0600. Without it, the secrets in the database cannot be read.
- **User passwords** are stored as scrypt hashes.
- **Sessions** use an `HttpOnly` + `SameSite=Strict` cookie that lasts 12 hours and is extended while you are active.
- **CSRF:** mutating requests require an `X-Requested-With` header.
- **Brute force:** at most 10 failed logins per 15 minutes from one address.
- **Roles:** view-only users see no settings, users or audit log, and cannot change anything.
- Strict CSP, with no external scripts.
- Device passwords and tokens are never returned by the API, only a "set" flag.
- **The audit log** records logins, failed attempts, changes, downloads, deletions and restores.
- **Expose the UI only over HTTPS:** a reverse proxy with `WEB_COOKIE_SECURE=true`, or `WEB_TLS_CERT` / `WEB_TLS_KEY`.
- **The router `backup` user:** restrict it by source address, and restrict services with `address=`. Do not disable TLS verification: this account has the `sensitive` and `write` policies.
- **The router's SSH host key** is remembered on first connection. If the key changes later, the connection is refused.

## Backing up mtb itself

Save the whole `DATA_DIR`: `mtb.db` and `secret.key` **together**. Keep the backup passphrase separately, for example in a password manager: without it, `.backup` and certificates cannot be restored.

For a live copy, use `sqlite3 mtb.db ".backup copy.db"`, or stop the service first.

## Upgrading

| Method | How |
|---|---|
| systemd | `curl -fsSL …/install.sh \| sudo sh` — the configuration and database are left alone. |
| Docker Compose | `docker compose pull && docker compose up -d` |

The database schema is migrated automatically on start.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Lost the `admin` password | `mtb reset-password admin` with the same `DATA_DIR`. On the next login you will be asked to set a new one. |
| The login form reappears right after logging in | The UI is opened over HTTP while `WEB_COOKIE_SECURE=true`. Use HTTPS or remove the variable. |
| "Слишком много попыток" (too many attempts) | 10 failed logins in 15 minutes. Wait, or restart the service. |
| `не удалось расшифровать секрет` (cannot decrypt secret) | The database was copied without its `secret.key`. Restore the key or re-enter the passwords. |
| `FingerprintMismatch` | The API-SSL certificate was reissued. Click "Получить с устройства" and verify the fingerprint. |
| `DH_KEY_TOO_SMALL`, `handshake failure` | The API-SSL key is shorter than 2048 bits. Reissue it, or enable "weak keys". |
| Missing policies | "Проверить доступ" (Check access) shows which ones. |
| `BadHostKeyException` | The router's SSH key changed. If that was expected, delete its line from `DATA_DIR/known_hosts`. |
| `Не задан пароль шифрования` (no passphrase set) | Settings → Storage and encryption. |
| `UnicodeDecodeError` | Set the device encoding to Windows-1251. |
| `Permission denied` in `./data` or `./backups` (Docker) | Set `PUID`/`PGID` to the owner of the folders. |
| Push rejected | Someone committed to the repository manually. The service tries `pull --rebase`; if that hits a conflict, resolve it in `backups/`. |

For a detailed log, use `LOG_LEVEL=DEBUG`.

## Development and build

```bash
git clone https://github.com/netcorexc0a8/mtb.git && cd mtb
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m mtb serve          # http://localhost:8080, data in ./data and ./backups
```

**Binary:**

```bash
pip install pyinstaller && pyinstaller --clean --noconfirm mtb.spec
```

For compatibility with older glibc, build inside `python:3.11-slim-buster`, as CI does.

**Release:** `git tag v2.0.0 && git push origin v2.0.0`. The workflow builds the binaries (linux-amd64, linux-arm64, windows-amd64), publishes the image to GHCR, and creates a GitHub Release with `install.sh`, the systemd unit and `SHA256SUMS`.

### Project layout

```
mtb/
├── mtb/
│   ├── main.py          # CLI and service (schedule + web)
│   ├── config.py        # startup from environment; settings and devices from SQLite
│   ├── db.py            # SQLite: schema and migrations
│   ├── secretbox.py     # encryption of secrets in the database
│   ├── auth.py          # users, scrypt, sessions, brute-force protection
│   ├── web.py           # web server and API
│   ├── web/             # index.html, app.js, app.css
│   ├── runner.py        # a single backup run + run history
│   ├── mikrotik.py      # API-SSL, SSH, SFTP, /file/read, export, restore
│   ├── probe.py         # transport checks
│   ├── storage.py       # git / snapshots storage, Gitea push
│   ├── catalog.py       # backup index for the web UI
│   ├── importer.py      # migrating 1.x devices.yaml and .env
│   └── notify.py        # Telegram
├── packaging/           # PyInstaller entry point, systemd unit
├── docs/                # screenshots
├── install.sh, mtb.spec, Dockerfile, docker-compose.yml, .env.example
├── README.md            # English
├── README.ru.md         # Russian (primary)
└── .github/workflows/release.yml
```
