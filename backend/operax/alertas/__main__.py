"""`python -m operax.alertas` — monta o ciclo e enfileira, sem enviar nada.

Os dois passos andam juntos porque um ciclo montado e não enfileirado é o pior
estado possível: os desvios já estão reservados nele, então não entram no próximo
— e ninguém recebeu nada. Enviar é do `sender`, que roda em outra cadência e tem
o gate G4 na frente.

"Andam juntos" era intenção e virou mecanismo (C7): o escopo é aberto AQUI, uma
vez por tenant, e os dois passos correm dentro dele. Reserva e fila commitam
juntas ou nenhuma commita, e o ciclo que terminou sem mensagem nenhuma é
desfeito antes do commit — o `on delete set null` do FK devolve os desvios ao
turno seguinte, sem que desvio algum seja apagado (regra 6).
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from operax.alertas import ciclo, outbox
from operax.core.config import get_settings
from operax.core.db import run_cli
from operax.core.tenant import SystemContext, active_tenants, tenant_scope

logger = logging.getLogger(__name__)


async def _por_tenant(context: SystemContext, ate: date, base_url: str) -> list[str]:
    """Um tenant, uma transação: montar, enfileirar e desfazer o ciclo mudo."""
    async with tenant_scope(context) as scope:
        ciclos = await ciclo.assemble(scope, ate)
        resultado = await outbox.enqueue(scope, ciclos, base_url=base_url)
        mudos = await ciclo.drop_silent(scope, ciclos)

    # O relatório do ciclo é montado depois do `drop_silent`, e só com os que
    # sobraram: contá-los antes faria o turno imprimir "1 ciclo(s)" e, duas
    # linhas abaixo, "ciclo desfeito" — quem faz `grep` no log contaria errado.
    de_pe = [c for c in ciclos if c not in mudos]
    linhas = [ciclo.relatorio([(context, de_pe)])]
    if not ciclos:
        return linhas
    # Por canal, sem destino: o de uma linha `telegram` é o chat_id. As linhas
    # seguintes nomeiam quem ficou de fora — a regra e o porquê.
    linhas += [f"  {linha}" for linha in outbox.relatorio(resultado).splitlines()]
    linhas += [
        f"  ciclo de {c.unit_name} desfeito: nenhuma mensagem — {c.total_events} "
        f"ocorrência(s) voltam ao próximo turno"
        for c in mudos
    ]
    return linhas


async def _montar_e_enfileirar(base_url: str, ate: date) -> str:
    """Cada tenant no seu try: o turno de um não leva o turno dos outros.

    A mesma dívida que o `run()` do `sender` fechou em `a8f589c`. Aqui ela é
    pior de um jeito e melhor de outro: um gatilho do banco pode recusar de
    dentro do `insert` — `util.validate_alert_template` tem um motivo que o
    Python não consegue perguntar antes —, e aí não há o que pular. Mas a
    transação é uma só, então o que falha não deixa rastro: nada commitado,
    desvios livres, e o turno seguinte tenta de novo.
    """
    linhas: list[str] = []
    for context in await active_tenants(ciclo.TASK):
        try:
            linhas += await _por_tenant(context, ate, base_url)
        except Exception as exc:
            logger.exception("alertas: o turno do tenant %s morreu", context.tenant_id)
            linhas.append(
                f"tenant {context.tenant_id}: ✗ o turno morreu ({type(exc).__name__}) — "
                f"nada foi montado nem enfileirado neste cliente; os outros seguiram, "
                f"e os desvios continuam livres para o próximo turno."
            )
    return "\n".join(linhas) or "nenhum tenant ativo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monta o ciclo de relatório e enfileira.")
    parser.add_argument(
        "--url", default=None, help="origem do painel para o link profundo (padrão: CORS_ORIGINS)"
    )
    args = parser.parse_args(argv)
    base_url = args.url or get_settings().dashboard_url
    print(run_cli(_montar_e_enfileirar(base_url, date.today())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
