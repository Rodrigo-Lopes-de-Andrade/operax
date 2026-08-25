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

from operax.motor import cadastro, deteccao, revogacao
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


# ---------------------------------------------------------------------------
# Cadência
# ---------------------------------------------------------------------------
def test_o_escopo_da_execucao_sai_da_janela_e_nao_de_uma_flag():
    """`app.detection_run.scope` é o que `fn_detection_health` olha.

    A migration 13 separou as duas cadências — incremental no dia corrente,
    retroativa em sete dias — e a saúde do motor é medida por esse rótulo. Um
    `--dias 1` rotulado `backfill` faria a medição dizer que a passada retroativa
    rodou quando ela não rodou, que é o pior tipo de sinal verde.
    """
    assert "%(scope)s" in deteccao._OPEN_RUN_SQL
    assert "scope" in deteccao._OPEN_RUN_SQL.replace("%(scope)s", "")
    assert "%(scope)s" in revogacao._OPEN_RUN_SQL


# ---------------------------------------------------------------------------
# Promoção do espelho
# ---------------------------------------------------------------------------
def test_a_empresa_do_colaborador_nunca_vem_do_departamento():
    """Regra 5, conferida no texto do statement.

    Cerca de 26% do quadro está num departamento de outra empresa. O join que
    resolve `company_id` tem de partir de `Funcionario.empresa_id`; partir de
    `Departamento.empresa_id` põe um quarto da folha na empresa errada de forma
    consistente e invisível — e nenhuma tela mostraria isso.
    """
    sql = cadastro._EMPLOYEES_SQL

    assert 'join secullum."Empresa" e on e.id = f.empresa_id' in sql
    assert "d.empresa_id" not in sql


def test_a_promocao_nao_inventa_unidade():
    """`app.unit` é dimensão nossa; o espelho não tem esse conceito.

    A ponte é `app.unit_secullum_map`, curada com o cliente. Criar unidade aqui
    transformaria trabalho de curadoria em dado silencioso.
    """
    assert "insert into app.unit " not in cadastro._EMPLOYEES_SQL
    assert "app.unit_secullum_map" in cadastro._EMPLOYEES_SQL


def test_a_promocao_nao_desfaz_curadoria_humana():
    """Mapa removido não pode apagar a lotação de quem já estava alocado."""
    assert "coalesce(excluded.unit_id, app.employee.unit_id)" in cadastro._EMPLOYEES_SQL


def test_a_fila_de_pendencia_ignora_quem_ja_saiu():
    """Mapear departamento por causa de desligado é trabalho por nada."""
    assert "status <> 'desligado'" in cadastro._PENDING_SQL


def test_a_promocao_liga_o_tenant_em_todo_statement():
    for nome, sql in vars(cadastro).items():
        if not nome.endswith("_SQL") or not isinstance(sql, str):
            continue
        assert "%(tenant_id)s" in sql, nome
        assert "tenant_id" in sql.replace("%(tenant_id)s", ""), nome


def test_o_relatorio_mostra_a_fila_de_curadoria():
    """É o aceite do S1: ou zero ativo sem unidade, ou a fila visível."""
    texto = cadastro.relatorio(
        [
            cadastro.Promotion(
                tenant_id=TENANT,
                employees=172,
                active=160,
                without_unit=13,
                pending=(cadastro.PendingUnit("Pátio Norte", 7102, 13),),
            )
        ]
    )

    assert "160 ativo(s) · 91.9% com unidade" in texto
    assert "sem unidade: 13 em «Pátio Norte» (Departamento 7102)" in texto


def test_sem_pendencia_o_relatorio_diz_isso():
    texto = cadastro.relatorio(
        [cadastro.Promotion(tenant_id=TENANT, employees=5, active=5, without_unit=0, pending=())]
    )

    assert "nenhuma pendência: todo ativo tem unidade" in texto
