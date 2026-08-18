#!/usr/bin/env bash
# PostToolUse (Edit|Write|MultiEdit) — autofix nao-bloqueante + gate de lint.
# Arquivo nao-Python sai silenciosamente com 0.
set -uo pipefail

FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$FILE" ] || exit 0

case "$FILE" in
  *.py) ;;
  *) exit 0 ;;
esac

[ -f "$FILE" ] || exit 0

# Ruff do PATH quando existir (le a config do pyproject.toml mais proximo
# de qualquer forma); uv so como fallback. Nesta ordem o hook nao trava
# enquanto backend/pyproject.toml ainda nao declara o ruff como dependencia.
if command -v ruff >/dev/null 2>&1; then
  RUFF=(ruff)
elif [ -f "backend/pyproject.toml" ] && command -v uv >/dev/null 2>&1; then
  RUFF=(uv run --project backend --quiet ruff)
else
  exit 0
fi

"${RUFF[@]}" check --fix "$FILE" >/dev/null 2>&1 || true

if ! OUTPUT=$("${RUFF[@]}" check "$FILE" 2>&1); then
  printf '%s\n' "$OUTPUT" >&2
  exit 2
fi

exit 0
