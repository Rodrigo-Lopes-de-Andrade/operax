"""O que o motor decide fora do SQL — e a guarda de que o SQL é um só.

O algoritmo mora em `operax/motor/regras.py` e é provado contra um Postgres de
verdade por `scripts/94_teste_deteccao.py`, no `make db-test`. O que sobra para
cá é o que o Python decide: como o modo chega da linha de comando, o que o
relatório diz ao operador, e — o mais importante — que os três statements
continuam sendo o MESMO cálculo.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from operax.motor import deteccao, revogacao
from operax.motor.regras import DETECT_SQL, EVENTS_SQL, SUPERSEDED_SQL, VANISHED_SQL

TENANT = UUID("dddddddd-0000-0000-0000-000000000001")
RUN = UUID("dddddddd-0000-0000-0000-0000000000f0")


# ---------------------------------------------------------------------------
# Um cálculo só
# ---------------------------------------------------------------------------
def test_os_tres_statements_partem_do_mesmo_calculo():
    """Se um deles deixar de derivar de `EVENTS_SQL`, o motor se contradiz.

    O detector escreve a partir de uma definição de "o que é desvio neste dia" e
    a revogação pergunta duas vezes contra ela. Uma cópia divergiria na primeira
    mudança de tolerância — e a cópia que diverge nunca é a que alguém está
    lendo.
    """
    for statement in (DETECT_SQL, VANISHED_SQL, SUPERSEDED_SQL):
        assert statement.startswith(EVENTS_SQL)


def test_todo_statement_liga_o_tenant_e_a_janela():
    """A guarda do `bind_tenant` é sintática: o SQL tem de dar o que ela procura."""
    for statement in (DETECT_SQL, VANISHED_SQL, SUPERSEDED_SQL):
        assert "%(tenant_id)s" in statement
        assert "tenant_id" in statement.replace("%(tenant_id)s", "")
        assert "%(start)s" in statement and "%(end)s" in statement
        assert "%(mode)s" in statement


def test_o_detector_nao_reescreve_indicio_que_ja_saiu_em_relatorio():
    """A cláusula que separa "corrigir" de "reescrever o que o gestor recebeu"."""
    depois_do_conflito = DETECT_SQL[DETECT_SQL.index("on conflict") :]

    assert "report_cycle_id is null" in depois_do_conflito
    # E a unidade do fato não se reescreve: o `do update` a copia de si mesma.
    assert "unit_id       = app.deviation_event.unit_id" in depois_do_conflito


def test_o_conflito_cobre_o_modo():
    """Sem `mode` no alvo, reprocessar a sombra duplicaria (migration 18)."""
    assert (
        "on conflict (employee_id, reference_date, type, mode) where status = 'active'"
        in DETECT_SQL
    )


def test_o_evento_de_falta_exige_carga_declarada():
    """A guarda que impede a enxurrada de falso positivo em escala 12x36.

    Sem ela, todo dia de descanso de quem está numa rotação não espelhada vira um
    turno perdido — e a taxa de falso positivo que decide o gate G4 seria medida
    contra o próprio buraco da fonte.
    """
    bloco = DETECT_SQL[DETECT_SQL.index("'no_punches'") :]
    bloco = bloco[: bloco.index("union all")]

    assert "workload_minutes is not null" in bloco


def test_nenhuma_regra_le_bandeira_de_dia_do_espelho():
    """A expectativa vem de `app.expected_workday` e só dela.

    Duas fontes para "este dia era de trabalho" é uma a mais, e escolher entre
    elas é decisão de produto. As bandeiras estão nomeadas no docstring do módulo
    como as primeiras suspeitas de divergência na sombra — não no `where`.
    """
    for bandeira in ('"Folga"', '"Neutro"', '"Compensado"', '"Abono2"'):
        assert bandeira not in EVENTS_SQL


# ---------------------------------------------------------------------------
# A linha de comando e o relatório
# ---------------------------------------------------------------------------
def test_o_modo_aceita_o_vocabulario_do_operador_e_o_do_schema():
    assert deteccao.MODES["sombra"] == "shadow"
    assert deteccao.MODES["producao"] == "production"
    assert deteccao.MODES["shadow"] == "shadow"
    assert deteccao.MODES["production"] == "production"


def test_modo_desconhecido_para_a_execucao_em_vez_de_virar_producao(capsys):
    assert deteccao.main(["--modo", "teste"]) == 2
    assert "sombra ou producao" in capsys.readouterr().out


def _resultado(**kwargs) -> deteccao.RunResult:
    base = dict(
        tenant_id=TENANT,
        run_id=RUN,
        mode="shadow",
        start=date(2026, 8, 10),
        end=date(2026, 8, 10),
        events=3,
        employees=2,
        surplus=1,
        shortfall=2,
        deviation_minutes=90,
        blind_days=0,
        blind_employees=0,
        by_type=(deteccao.TypeTotal("late_entry", 2, 50),),
    )
    return deteccao.RunResult(**{**base, **kwargs})


def test_o_relatorio_traz_os_dias_cegos_junto_do_total():
    """Uma taxa de falso positivo sem esse denominador parece melhor do que é."""
    texto = deteccao.relatorio([_resultado(blind_days=91, blind_employees=13)])

    assert "13 colaborador(es) sem escala derivável" in texto
    assert "91 dia-pessoa" in texto
    assert "não entram na conta de falso positivo" in texto


def test_sem_dia_cego_o_relatorio_nao_inventa_ressalva():
    assert "sem escala derivável" not in deteccao.relatorio([_resultado()])


def test_o_relatorio_separa_excedente_de_faltante():
    texto = deteccao.relatorio([_resultado()])

    assert "90 min de desvio" in texto
    assert "(1 excedente / 2 faltante)" in texto


def test_sem_tenant_ativo_o_relatorio_diz_isso_em_vez_de_ficar_vazio():
    assert deteccao.relatorio([]) == "nenhum tenant ativo"


# ---------------------------------------------------------------------------
# Revogação
# ---------------------------------------------------------------------------
def _mudanca(**kwargs) -> revogacao.Change:
    base = dict(
        event_id=RUN,
        employee_id=TENANT,
        reference_date=date(2026, 8, 10),
        type="late_entry",
        minutes_before=-26,
        minutes_now=None,
    )
    return revogacao.Change(**{**base, **kwargs})


def _revogacao(**kwargs) -> revogacao.RevocationResult:
    base = dict(
        tenant_id=TENANT,
        run_id=RUN,
        mode="production",
        start=date(2026, 8, 4),
        end=date(2026, 8, 10),
        revoked=(),
        superseded=(),
    )
    return revogacao.RevocationResult(**{**base, **kwargs})


def test_dia_sem_correcao_diz_que_nada_mudou():
    """Silêncio não é resultado: um relatório vazio parece execução que não rodou."""
    assert "nada mudou na origem" in revogacao.relatorio([_revogacao()])


def test_o_relatorio_da_revogacao_mostra_o_antes_e_o_depois():
    texto = revogacao.relatorio(
        [
            _revogacao(
                revoked=(_mudanca(),),
                superseded=(_mudanca(type="late_exit", minutes_before=23, minutes_now=45),),
            )
        ]
    )

    assert "1 revogado(s) · 1 substituído(s)" in texto
    assert "revogado   2026-08-10 late_entry (-26 min)" in texto
    assert "substituído 2026-08-10 late_exit (23 -> 45 min)" in texto


def test_a_revogacao_passa_pela_funcao_do_banco_e_nunca_por_delete():
    """Regra 6 do projeto, conferida no texto do statement."""
    fonte = revogacao._REVOKE_SQL

    assert "app.revoke_deviation" in fonte
    assert "delete" not in revogacao.__doc__.lower().replace("**never a delete**", "")


def test_a_supersessao_preserva_empresa_e_unidade_do_fato():
    """Substituir não é uma chance de reescrever onde o fato aconteceu."""
    assert "d.company_id, d.unit_id" in revogacao._SUPERSEDE_SQL
    assert "d.id" in revogacao._SUPERSEDE_SQL.split("supersede_id")[1]
