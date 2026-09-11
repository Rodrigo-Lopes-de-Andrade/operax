"""O "hoje" do motor é o do tenant, não o do container.

Medido em 11/09/2026: o Railway roda em UTC, e às 21:00 de São Paulo o
`date.today()` virou amanhã. O incremental passou três horas detectando um dia
que ninguém tinha começado — 56 `no_punches` para o dia seguinte — e ignorando
o que ainda estava terminando. Estes testes fixam o instante e provam que o
relógio responde no fuso certo.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from operax.motor.relogio import Clock


def test_as_22h_de_sao_paulo_ainda_e_hoje() -> None:
    # 01:00 UTC de 11/09 = 22:00 de 10/09 em São Paulo.
    instante = datetime(2026, 9, 11, 1, 0, tzinfo=UTC)

    clock = Clock.at("America/Sao_Paulo", instante)

    assert clock.today == date(2026, 9, 10)
    assert clock.now == datetime(2026, 9, 10, 22, 0)


def test_o_now_e_naive_para_comparar_com_a_jornada() -> None:
    """`expected_exit_at` é naive local; um lado aware e outro naive estoura."""
    clock = Clock.at("America/Sao_Paulo", datetime(2026, 9, 11, 15, 30, tzinfo=UTC))

    assert clock.now.tzinfo is None
    assert clock.now == datetime(2026, 9, 11, 12, 30)


def test_em_utc_o_dia_e_o_do_container() -> None:
    """O fallback de tenant sem unidade é o comportamento antigo, explícito."""
    instante = datetime(2026, 9, 11, 1, 0, tzinfo=UTC)

    assert Clock.at("UTC", instante).today == date(2026, 9, 11)
