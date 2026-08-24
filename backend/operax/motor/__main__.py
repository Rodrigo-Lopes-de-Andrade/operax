"""`python -m operax.motor` — o que o `make motor` chama.

O pacote tem três passos e eles rodam em ordem: `jornada` materializa o que era
esperado e `deteccao` compara as batidas contra isso. Detectar contra uma tabela
vazia não dá zero desvio, dá zero informação — então o entrypoint faz os dois, e
`--so-deteccao` existe para quem já rodou a jornada e está iterando na regra.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from operax.motor import deteccao, jornada, revogacao


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
        "--so-deteccao", action="store_true", help="pula a materialização da jornada"
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
        print(jornada.relatorio(asyncio.run(jornada.run(days=args.dias_jornada))))
        print()
    print(deteccao.relatorio(asyncio.run(deteccao.run(days=args.dias, mode=mode))))

    # A reconciliação vem depois e na mesma passada porque é a mesma janela: o
    # detector já reescreveu o que ninguém viu, e o que sobra é o que ele não tem
    # como fazer — apagar não existe, então some quem deixou de ser detectado.
    if not args.sem_revogacao:
        print()
        print(revogacao.relatorio(asyncio.run(revogacao.run(days=args.dias, mode=mode))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
