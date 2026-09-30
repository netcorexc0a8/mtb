#!/bin/sh
# Выпуск релиза: версия в mtb/_version.py = git-тег = версия в веб-интерфейсе.
#   scripts/release.sh 0.2.0        стабильный релиз (получит latest, увидят все)
#   scripts/release.sh 0.2.0-rc.1   пре-релиз (увидят установки с каналом «пре-релизы» / dev-версией)
set -eu

V="${1:?Использование: scripts/release.sh X.Y.Z[-pre]}"
V="${V#v}"
echo "$V" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$' \
  || { echo "Версия должна быть в формате semver: X.Y.Z или X.Y.Z-pre (например 0.2.0-rc.1)"; exit 1; }

cd "$(git rev-parse --show-toplevel)"
[ -z "$(git status --porcelain)" ] || { echo "Есть незакоммиченные изменения"; exit 1; }
BRANCH=$(git rev-parse --abbrev-ref HEAD)
[ "$BRANCH" = main ] || { echo "Релиз выпускается из main (сейчас: $BRANCH)"; exit 1; }
git fetch -q --tags origin
if git rev-parse -q --verify "refs/tags/v$V" >/dev/null; then echo "Тег v$V уже существует"; exit 1; fi
[ "$(git rev-parse HEAD)" = "$(git rev-parse '@{u}')" ] || { echo "main не совпадает с origin/main — сначала git pull / git push"; exit 1; }

printf '__version__ = "%s"\n' "$V" > mtb/_version.py
git add mtb/_version.py
git commit -qm "release: v$V"
git tag -a "v$V" -m "v$V"
git push -q origin main "v$V"

REPO=$(git remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
echo "Готово: v$V"
echo "Сборка:  https://github.com/$REPO/actions"
echo "Релиз:   https://github.com/$REPO/releases/tag/v$V"
