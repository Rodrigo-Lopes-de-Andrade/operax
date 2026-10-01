"""`python -m operax.motor` — o que o `make motor` chama.

O pacote tem cinco passos e eles rodam em ordem: `jornada` materializa o que era
esperado e `deteccao` compara as batidas contra isso. Detectar contra uma tabela
vazia não dá zero desvio, dá zero informação — então o entrypoint faz os dois, e
`--so-deteccao` existe para quem já rodou a jornada e está iterando na regra.
"""

from __future__ import annotations

import argparse
import sys

from operax.core.db import run_cli
from operax.motor import cadastro, deteccao, feriados, jornada, revogacao


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Motor do OperaX: jornada esperada + detecção.")
    parser.add_argument("--modo", default="sombra", help="sombra (padrão) ou producao")
    parser.add_argument(
        "--dias",
        type=int,
        default=deteccao.BACKFILL_DAYS,
        help=f"janela da detecção (padrão {deteccao.BACKFILL_DAYS})",
    )
    parser.add_argument(
        "--dias-jornada",
        type=int,
        default=jornada.DEFAULT_WINDOW_DAYS,
        help=f"janela da jornada esperada (padrão {jornada.DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--so-deteccao", action="store_true", help="pula a promoção do cadastro e a jornada"
    )
    parser.add_argument(
        "--sem-revogacao", action="store_true", help="pula a reconciliação retroativa"
    )
    args = parser.parse_args(argv)

    mode = deteccao.MODES.get(args.modo)
    if mode is None:
        print(f"erro: modo {args.modo!r} — use sombra ou producao", file=sys.stderr)
        return 2

    if not args.so_deteccao:
        # Passo zero: sem quadro no domínio, a jornada materializa zero linha e a
        # detecção acha zero desvio — que não é "está tudo certo", é "não há o
        # que comparar". Foi o estado de produção até 24/08/2026.
        print(cadastro.relatorio(run_cli(cadastro.run())))
        print()
        print(jornada.relatorio(run_cli(jornada.run(days=args.dias_jornada))))
        print()
    print(deteccao.relatorio(run_cli(deteccao.run(days=args.dias, mode=mode))))

    # A reconciliação vem depois e na mesma passada porque é a mesma janela: o
    # detector já reescreveu o que ninguém viu, e o que sobra é o que ele não tem
    # como fazer — apagar não existe, então some quem deixou de ser detectado.
    if not args.sem_revogacao:
        print()
        print(revogacao.relatorio(run_cli(revogacao.run(days=args.dias, mode=mode))))

    # O feriado cadastrado com atraso: a jornada acima já o materializou (ela
    # olha 90 dias no retro), mas a detecção e a revogação olham só a semana.
    # Sem este passo o `no_punches` que o feriado explica ficaria ativo para
    # sempre — foi o 07/09/2026. Só o feriado escrito nos últimos dois dias
    # (`feriados.RECENT_WRITE`), e só onde a jornada rodou.
    if not args.so_deteccao and not args.sem_revogacao:
        print()
        print(
            feriados.relatorio(
                run_cli(
                    feriados.run_late(
                        jornada_days=args.dias_jornada, detection_days=args.dias, mode=mode
                    )
                )
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
