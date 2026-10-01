"""O calendário de feriados fora do SQL.

A regra (quem folga, quem vira indício, o VT) é provada contra um Postgres de
verdade por `scripts/83_teste_feriado.py`. Aqui fica o que o Python decide: a
Páscoa, a ordem do reprocessamento de um dia, a janela do passo automático, o
motivo que a revogação escreve, o modo padrão do comando, e a porta de escrita —
que é só do owner.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from operax.core.tenant import SystemContext
from operax.motor import feriados, revogacao
from operax.motor.relogio import Clock
from server.routers import feriados as rota

TENANT = UUID("f8300000-0000-4000-8000-000000000001")
UNIT = UUID("f8300000-0000-4000-8000-0000000000a1")


# ---------------------------------------------------------------------------
# A carga nacional
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("ano", "pascoa"),
    [
        (2000, date(2000, 4, 23)),
        (2019, date(2019, 4, 21)),
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
    ],
)
def test_a_pascoa_e_a_do_calendario_gregoriano(ano: int, pascoa: date) -> None:
    assert feriados.easter(ano) == pascoa


def test_a_sexta_feira_da_paixao_entra_na_carga_nacional() -> None:
    """Decisão do dono (28/09/2026): Páscoa − 2."""
    dias = dict(feriados.national_holidays(2026))
    assert dias[date(2026, 4, 3)] == "Sexta-feira da Paixão"
    assert dict(feriados.national_holidays(2027))[date(2027, 3, 26)] == "Sexta-feira da Paixão"


def test_a_carga_tem_os_dez_dias_e_nao_tem_ponto_facultativo() -> None:
    """Carnaval e Corpus Christi são ponto facultativo federal: o owner os cadastra."""
    dias = feriados.national_holidays(2026)
    assert len(dias) == 10
    assert [d for d, _ in dias] == sorted(d for d, _ in dias)
    assert date(2026, 9, 7) in dict(dias)
    assert date(2026, 2, 17) not in dict(dias)  # terça de Carnaval
    assert date(2026, 6, 4) not in dict(dias)  # Corpus Christi


def test_a_carga_e_idempotente_e_respeita_o_nacional_desativado() -> None:
    """O alvo do `on conflict` é o unique parcial do nacional, SEM `active`: uma
    linha desativada continua ocupando a vaga, e a carga não a traz de volta."""
    assert (
        "on conflict (tenant_id, reference_date) where unit_id is null do nothing"
        in feriados._LOAD_SQL
    )
    assert "active" not in feriados._LOAD_SQL


# ---------------------------------------------------------------------------
# O reprocessamento de um dia
# ---------------------------------------------------------------------------
def _contexto() -> SystemContext:
    return SystemContext(tenant_id=TENANT, task="teste")


def test_reprocessar_faz_jornada_deteccao_e_revogacao_nessa_ordem_e_num_dia_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[tuple[str, Any, Any, dict[str, Any]]] = []

    def grava(nome: str):
        async def passo(ctx: Any, inicio: date, fim: date, **kw: Any) -> str:
            chamadas.append((nome, inicio, fim, kw))
            return nome

        return passo

    monkeypatch.setattr(feriados.jornada, "materialize", grava("jornada"))
    monkeypatch.setattr(feriados.deteccao, "detect", grava("deteccao"))
    monkeypatch.setattr(feriados.revogacao, "reconcile", grava("revogacao"))

    dia = date(2026, 9, 7)
    agora = datetime(2026, 9, 28, 10, 0)
    asyncio.run(feriados.reprocess(_contexto(), dia, mode="shadow", now=agora))

    assert [c[0] for c in chamadas] == ["jornada", "deteccao", "revogacao"]
    assert all((c[1], c[2]) == (dia, dia) for c in chamadas)
    # Dia velho é retroativo, mesmo com janela de um dia: rotulado `incremental`
    # ele esconderia um cron incremental morto em `fn_detection_health`.
    assert chamadas[1][3] == {"mode": "shadow", "now": agora, "run_scope": "backfill"}
    assert chamadas[2][3] == {"mode": "shadow", "now": agora}


class _Scope:
    def __init__(self, linhas: list[dict[str, Any]]) -> None:
        self.linhas = linhas
        self.params: list[Any] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        self.params.append(params)

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.linhas


class _Ctx:
    def __init__(self, scope: _Scope) -> None:
        self.scope = scope

    async def __aenter__(self) -> _Scope:
        return self.scope

    async def __aexit__(self, *exc: object) -> None:
        return None


def _passo_automatico(
    monkeypatch: pytest.MonkeyPatch, *, jornada_days: int, detection_days: int
) -> tuple[_Scope, list[date]]:
    hoje = datetime(2026, 9, 28, 5, 20)
    scope = _Scope([{"reference_date": date(2026, 9, 7)}])
    refeitos: list[date] = []

    async def tenants(_task: str) -> list[SystemContext]:
        return [_contexto()]

    async def relogio(_ctx: Any) -> Clock:
        return Clock(timezone="America/Sao_Paulo", now=hoje)

    async def reprocess(_ctx: Any, dia: date, **_kw: Any) -> date:
        refeitos.append(dia)
        return dia

    monkeypatch.setattr(feriados, "active_tenants", tenants)
    monkeypatch.setattr(feriados, "tenant_clock", relogio)
    monkeypatch.setattr(feriados, "tenant_scope", lambda _c: _Ctx(scope))
    monkeypatch.setattr(feriados, "reprocess", reprocess)
    asyncio.run(
        feriados.run_late(jornada_days=jornada_days, detection_days=detection_days, mode="shadow")
    )
    return scope, refeitos


def test_o_passo_automatico_cobre_o_que_a_jornada_ve_e_a_deteccao_nao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retro de 28/09 (jornada 90, detecção 7): de 01/07 a 21/09 — 21/09 é o
    primeiro dia que a semana da detecção já não alcança. O 07/09/2026 está
    dentro. E só o feriado escrito desde 26/09 05:20 no relógio do tenant: dois
    dias, como instante (`updated_at` é timestamptz)."""
    scope, refeitos = _passo_automatico(monkeypatch, jornada_days=90, detection_days=7)
    assert scope.params == [
        {
            "start": date(2026, 7, 1),
            "end": date(2026, 9, 21),
            "since": datetime(2026, 9, 26, 5, 20, tzinfo=ZoneInfo("America/Sao_Paulo")),
        }
    ]
    assert refeitos == [date(2026, 9, 7)]


def test_o_incremental_nao_reprocessa_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Jornada 3, detecção 1: o que a jornada vê a mais está dentro da semana que o
    retro refaz de qualquer jeito — refazer a cada 15 minutos seria só ruído."""
    scope, refeitos = _passo_automatico(monkeypatch, jornada_days=3, detection_days=1)
    assert scope.params == []
    assert refeitos == []


def test_o_passo_automatico_le_o_feriado_desativado_tambem() -> None:
    """Desativar um feriado tem de corrigir o dia do mesmo jeito que cadastrá-lo."""
    assert "active" not in feriados._DATES_SQL
    assert "%(tenant_id)s" in feriados._DATES_SQL


def test_o_passo_automatico_so_refaz_o_feriado_escrito_recentemente() -> None:
    """Feriado que ninguém tocou já foi refeito no dia em que foi escrito.

    O filtro é o SQL; o que ele devolve contra um banco de verdade — o antigo
    inalterado fica de fora, o desativado ontem entra — é provado pelo
    `scripts/83_teste_feriado.py`, que executa este mesmo `_DATES_SQL`.
    """
    assert "h.updated_at >= %(since)s" in feriados._DATES_SQL
    assert feriados.RECENT_WRITE == timedelta(days=2)


def test_o_modo_padrao_do_comando_e_sombra(monkeypatch: pytest.MonkeyPatch) -> None:
    """⚠️ O `--modo` padrão de `revogacao` é produção; o motor roda em sombra. O
    reprocessamento pontual do 07/09 não pode herdar o padrão errado."""
    pedido: dict[str, Any] = {}

    async def run_dates(dias: list[date], *, mode: str) -> list[Any]:
        pedido.update(dias=dias, mode=mode)
        return []

    monkeypatch.setattr(feriados, "run_dates", run_dates)
    monkeypatch.setattr(feriados, "run_cli", asyncio.run)
    assert feriados.main(["reprocessar", "--data", "2026-09-07"]) == 0
    assert pedido == {"dias": [date(2026, 9, 7)], "mode": "shadow"}


def test_modo_desconhecido_para_em_vez_de_virar_producao(capsys: pytest.CaptureFixture) -> None:
    assert feriados.main(["reprocessar", "--data", "2026-09-07", "--modo", "prod"]) == 2
    assert "sombra ou producao" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# O motivo da revogação
# ---------------------------------------------------------------------------
def test_o_indicio_que_o_feriado_explica_e_revogado_pelo_feriado() -> None:
    assert revogacao.vanished_reason("holiday", "no_punches") == revogacao.REASON_HOLIDAY


def test_fora_do_feriado_o_motivo_continua_sendo_a_batida() -> None:
    assert revogacao.vanished_reason("work", "no_punches") == revogacao.REASON_VANISHED
    assert revogacao.vanished_reason(None, "late_entry") == revogacao.REASON_VANISHED


def test_batida_em_feriado_que_some_com_o_feriado_de_pe_foi_a_batida_que_sumiu() -> None:
    assert revogacao.vanished_reason("holiday", "punch_on_holiday") == revogacao.REASON_VANISHED


@pytest.mark.parametrize("dia", ["work", "day_off", None])
def test_batida_em_feriado_que_some_porque_o_feriado_saiu(dia: str | None) -> None:
    """O dia deixou de ser `holiday`: quem mudou foi o calendário, não a batida."""
    assert revogacao.vanished_reason(dia, "punch_on_holiday") == revogacao.REASON_HOLIDAY_REMOVED


def test_batida_na_folga_que_virou_feriado() -> None:
    """A folga semanal virou feriado: a mesma batida volta como `punch_on_holiday`,
    e dizer que "o dia deixou de ter jornada" mentiria — ele nunca teve."""
    assert (
        revogacao.vanished_reason("holiday", "punch_on_day_off")
        == revogacao.REASON_DAY_OFF_TO_HOLIDAY
    )


def test_o_motivo_nunca_fala_em_hora_extra() -> None:
    for motivo in (
        revogacao.REASON_HOLIDAY,
        revogacao.REASON_VANISHED,
        revogacao.REASON_HOLIDAY_REMOVED,
        revogacao.REASON_DAY_OFF_TO_HOLIDAY,
    ):
        assert "hora extra" not in motivo.lower()


# ---------------------------------------------------------------------------
# A porta de escrita: só owner
# ---------------------------------------------------------------------------
class StubScope:
    """Responde pelo assunto do statement, não pela ordem das chamadas."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.statements: list[str] = []
        self.params: list[Any] = []
        self._current: Any = None

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)
        self._current = next(
            (value for marker, value in self._answers.items() if marker in statement), None
        )

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._current or []

    async def fetchone(self) -> dict[str, Any] | None:
        return self._current


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope

    async def __aenter__(self) -> StubScope:
        return self._scope

    async def __aexit__(self, *exc: object) -> None:
        return None


def _linha(**over: Any) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "reference_date": date(2026, 11, 20),
        "jurisdiction": "municipal",
        "unit_id": UNIT,
        "name": "Consciência Negra",
        "active": True,
    } | over


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch):
    def install(
        *,
        owner: bool = True,
        unit: dict[str, Any] | None = None,
        gravado: dict[str, Any] | None = None,
        lista: list[dict[str, Any]] | None = None,
    ) -> tuple[StubScope, StubScope]:
        scope = StubScope({"util.roles_in_tenant": {"owner": owner}})
        bound = StubScope(
            {
                "from app.unit u where u.id": unit if unit is not None else {"name": "Aeroporto"},
                "insert into app.holiday": gravado,
                "update app.holiday": gravado,
                "from app.holiday h": lista or [],
                "insert into app.audit_log": None,
            }
        )
        monkeypatch.setattr(rota, "user_scope", lambda _c: StubScopeContext(scope))
        monkeypatch.setattr(rota, "tenant_scope", lambda _c: StubScopeContext(bound))
        return scope, bound

    return install


def _post(client: TestClient, token: str, body: dict[str, Any]):
    return client.post("/feriados", json=body, headers={"Authorization": f"Bearer {token}"})


_MUNICIPAL = {"reference_date": "2026-11-20", "jurisdiction": "municipal", "name": "Consciência"}


def test_quem_nao_e_owner_nao_chega_na_transacao_de_escrita(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    """`hr` e `personnel` são `is_admin` e NÃO são owner: 403, antes do service_role."""
    _, bound = answer(owner=False)
    resposta = _post(client, issue_token(), {**_MUNICIPAL, "unit_id": str(UNIT)})
    assert resposta.status_code == 403
    assert bound.statements == []


def test_a_permissao_e_perguntada_a_mesma_funcao_da_policy(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    """A policy `holiday_owner` chama `util.roles_in_tenant`; perguntar a
    `util.is_admin` aqui deixaria o RH passar pela porta que o banco fecha."""
    scope, _ = answer(owner=False)
    _post(client, issue_token(), {**_MUNICIPAL, "unit_id": str(UNIT)})
    assert "'owner' = any(util.roles_in_tenant(" in scope.statements[0]
    assert "is_admin" not in scope.statements[0]


def test_owner_grava_e_a_auditoria_sai_na_mesma_transacao(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    linha = _linha()
    _, bound = answer(gravado=linha)
    resposta = _post(client, issue_token(), {**_MUNICIPAL, "unit_id": str(UNIT)})
    assert resposta.status_code == 201
    assert resposta.json()["unit_name"] == "Aeroporto"
    assert any("insert into app.holiday" in s for s in bound.statements)
    assert "insert into app.audit_log" in bound.statements[-1]


def test_unidade_de_outro_cliente_nao_grava(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    _, bound = answer(unit={})
    bound._answers["from app.unit u where u.id"] = None
    resposta = _post(client, issue_token(), {**_MUNICIPAL, "unit_id": str(UNIT)})
    assert resposta.status_code == 422
    assert not any("insert into app.holiday" in s for s in bound.statements)


@pytest.mark.parametrize(
    "corpo",
    [
        {"reference_date": "2026-09-07", "jurisdiction": "national", "name": "X", "unit_id": None},
        {"reference_date": "2026-09-07", "jurisdiction": "municipal", "name": "X"},
    ],
    ids=["nacional sem unidade vale", "municipal sem unidade"],
)
def test_nacional_nao_tem_unidade_e_local_tem(
    client: TestClient, issue_token: Any, answer: Any, corpo: dict[str, Any]
) -> None:
    answer(gravado=_linha(jurisdiction="national", unit_id=None))
    esperado = 201 if corpo["jurisdiction"] == "national" else 422
    assert _post(client, issue_token(), corpo).status_code == esperado


def test_nacional_com_unidade_e_recusado(client: TestClient, issue_token: Any, answer: Any) -> None:
    answer()
    corpo = {
        "reference_date": "2026-09-07",
        "jurisdiction": "national",
        "name": "X",
        "unit_id": str(UNIT),
    }
    assert _post(client, issue_token(), corpo).status_code == 422


def test_feriado_repetido_e_conflito(client: TestClient, issue_token: Any, answer: Any) -> None:
    _, bound = answer(gravado=None)
    resposta = _post(client, issue_token(), {**_MUNICIPAL, "unit_id": str(UNIT)})
    assert resposta.status_code == 409
    assert not any("insert into app.audit_log" in s for s in bound.statements)


def test_quem_nao_e_owner_nao_le_o_calendario_pela_api(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    """A tela é do owner: a leitura pela API também para no 403, antes do
    `service_role` abrir."""
    _, bound = answer(owner=False, lista=[_linha(unit_name="Aeroporto")])
    resposta = client.get(
        "/feriados?ano=2026", headers={"Authorization": f"Bearer {issue_token()}"}
    )
    assert resposta.status_code == 403
    assert bound.statements == []


def test_owner_le_o_calendario_do_ano(client: TestClient, issue_token: Any, answer: Any) -> None:
    _, bound = answer(lista=[_linha(unit_name="Aeroporto")])
    resposta = client.get(
        "/feriados?ano=2026", headers={"Authorization": f"Bearer {issue_token()}"}
    )
    assert resposta.status_code == 200
    assert resposta.json()[0]["unit_name"] == "Aeroporto"
    assert bound.params[0] == {"start": date(2026, 1, 1), "end": date(2026, 12, 31)}


@pytest.mark.parametrize("ano", ["1999", "2101"])
def test_ano_fora_da_faixa_e_recusado(
    client: TestClient, issue_token: Any, answer: Any, ano: str
) -> None:
    _, bound = answer()
    resposta = client.get(
        f"/feriados?ano={ano}", headers={"Authorization": f"Bearer {issue_token()}"}
    )
    assert resposta.status_code == 422
    assert bound.statements == []


def test_o_nome_e_gravado_sem_espaco_nas_pontas(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    _, bound = answer(gravado=_linha())
    _post(client, issue_token(), {**_MUNICIPAL, "unit_id": str(UNIT), "name": "  Finados  "})
    gravacao = next(
        p
        for s, p in zip(bound.statements, bound.params, strict=True)
        if "insert into app.holiday" in s
    )
    assert gravacao["name"] == "Finados"


def test_nome_so_de_espaco_e_recusado(client: TestClient, issue_token: Any, answer: Any) -> None:
    answer(gravado=_linha())
    corpo = {**_MUNICIPAL, "unit_id": str(UNIT), "name": "   "}
    assert _post(client, issue_token(), corpo).status_code == 422


def test_desativar_e_update_e_nunca_delete(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    linha = _linha(active=False, unit_name="Aeroporto", active_before=True)
    _, bound = answer(gravado=linha)
    resposta = client.patch(
        f"/feriados/{linha['id']}",
        json={"active": False},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["active"] is False
    assert not any("delete" in s.lower() for s in bound.statements)
    assert "insert into app.audit_log" in bound.statements[-1]
    # A auditoria guarda o antes e o depois, não só o depois.
    auditoria = bound.params[-1]
    assert auditoria["antes"].obj == {"active": True}
    assert auditoria["depois"].obj == {"active": False}
    assert "active_before" not in resposta.json()


def test_o_corpo_recusa_campo_que_ninguem_desenhou(
    client: TestClient, issue_token: Any, answer: Any
) -> None:
    """`tenant_id` no corpo é o cliente acreditando que recorta a escrita."""
    answer(gravado=_linha())
    corpo = {**_MUNICIPAL, "unit_id": str(UNIT), "tenant_id": str(TENANT)}
    assert _post(client, issue_token(), corpo).status_code == 422
