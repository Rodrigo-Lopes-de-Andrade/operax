#!/usr/bin/env python3
"""Conversor de carga inicial de RH — atalho para o módulo que vive no backend.

O caminho está aqui porque é em `scripts/` que se procura ferramenta de
implantação. O código está em `backend/operax/rh/carga_inicial.py` porque lê
.xlsx (openpyxl) e reusa o mapa de templates — e porque assim ele é testado pelo
pytest junto do resto, em vez de ser um script que ninguém roda até o dia da
carga.

    python3 scripts/rh_carga_inicial.py \\
        --planilha ~/implantacao/planilha-rh.xlsx \\
        --modelos  ~/implantacao/modelos \\
        --saida    ~/implantacao/saida
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def main() -> int:
    if not BACKEND.is_dir():
        print(f"erro: backend não encontrado em {BACKEND}", file=sys.stderr)
        return 2
    os.chdir(BACKEND)
    try:
        os.execvp("uv", ["uv", "run", "python", "-m", "operax.rh.carga_inicial", *sys.argv[1:]])
    except FileNotFoundError:
        print(
            "erro: `uv` não está no PATH. O conversor roda no ambiente do backend "
            "(`cd backend && uv sync`).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
