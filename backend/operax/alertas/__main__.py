"""`python -m operax.alertas` — monta o ciclo e enfileira, sem enviar nada.

Os dois passos andam juntos porque um ciclo montado e não enfileirado é o pior
estado possível: os desvios já estão reservados nele, então não entram no próximo
— e ninguém recebeu nada. Enviar é do `sender`, que roda em outra cadência e tem
o gate G4 na frente.
"""

from __future__ import annotations

import argparse
import asyncio

from operax.alertas import ciclo, outbox
from operax.core.config import get_settings


async def _montar_e_enfileirar(base_url: str) -> str:
    linhas: list[str] = []
    for context, ciclos in await ciclo.run():
        linhas.append(ciclo.relatorio([(context, ciclos)]))
        if not ciclos:
            continue
        enfileiradas = await outbox.enqueue(context, ciclos, base_url=base_url)
        linhas.append(f"  {len(enfileiradas)} mensagem(ns) na fila")
        for q in enfileiradas:
            linhas.append(f"    {q.rule_name} · {q.channel} · {q.destination}")
    return "\n".join(linhas) or "nenhum tenant ativo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monta o ciclo de relatório e enfileira.")
    parser.add_argument(
        "--url", default=None, help="origem do painel para o link profundo (padrão: CORS_ORIGINS)"
    )
    args = parser.parse_args(argv)
    base_url = args.url or get_settings().dashboard_url
    print(asyncio.run(_montar_e_enfileirar(base_url)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
