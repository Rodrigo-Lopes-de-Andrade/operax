#!/usr/bin/env bash
# PostToolUse (Edit|Write|MultiEdit) — gate de lint para .ts/.tsx.
# Arquivo fora desse conjunto sai silenciosamente com 0.
# Nunca instala dependencia: sem eslint local instalado, sai 0.
set -uo pipefail

FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$FILE" ] || exit 0

case "$FILE" in
  *.ts|*.tsx) ;;
  *) exit 0 ;;
esac

[ -f "$FILE" ] || exit 0

# Sobe do diretorio do arquivo procurando o eslint instalado localmente
# (frontend/ usa npm, conforme CLAUDE.md). Sem binario local, nao faz nada:
# `npx eslint` baixaria o pacote, e o hook nao instala dependencia.
DIR=$(cd "$(dirname "$FILE")" && pwd)
ESLINT=""
while [ "$DIR" != "/" ]; do
  if [ -x "$DIR/node_modules/.bin/eslint" ]; then
    ESLINT="$DIR/node_modules/.bin/eslint"
    ROOT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done
[ -n "$ESLINT" ] || exit 0

if ! OUTPUT=$(cd "$ROOT" && "$ESLINT" "$FILE" 2>&1); then
  printf '%s\n' "$OUTPUT" >&2
  exit 2
fi

exit 0
