"""Destinatários e regras de alerta (SPRINTS-CANAIS, C6): a API que a tela vai usar.

Seis portões, e os dois últimos são os que fecham o falso verde:

1. **quem escreve é admin** — todo `POST`/`PUT` é 403 sem `util.is_admin`, com
   `tenant_scope` nunca aberto; `GET /contatos` é de qualquer membro (o desenho
   das policies), `GET /regras` é do admin (a única policy de
   `app.alert_rule_target` é a de admin, e "sem destino" não pode ser mentira);
2. **404 antes de escrever** — contato, unidade e regra são lidos como o
   usuário, e o que não é do tenant não abre transação;
3. **a regra nasce desligada** — `active` no corpo do `POST` é 422 e nada é
   gravado; o `insert` leva o literal `false`, sem parâmetro;
4. **ligar é a única porta, e exige o que a entrega exige** — sem destino ativo,
   sem template (mensageria), template inexistente e template não aprovado no
   oficial são 409 nomeados que saem por exceção (rollback); com tudo, liga e
   audita. `desligar` sempre aceita;
5. **a regra 7 é do gatilho, e a frase é a dele** — em `destinos`, no `PUT` da
   regra (`content` → `individual`) e no `PUT` do contato (`type` → grupo), a
   `RaiseException` vira 409 `individual_to_group` com `message_primary`, e o
   re-toque dos destinos é a instrução que a provoca;
6. **o teste vai para quem clicou** — o contato é achado pelo e-mail do token,
   o destino é o dele (por `outbox.route`), a chave é a da casa com o sufixo
   do clique, a linha leva `rule_id` e `cycle_id` nulo, e a trilha leva o
   `test_id`.

Mais: `desativar` é `active = false` (nunca `delete`, e o módulo inteiro não
tem `delete` em contato nem em regra), 409 quando o contato é destino de regra
ligada; auditoria em toda escrita, com o `entity` certo; `blocked_reason` como
função pura sobre as duas leituras que já existem; e as duas entradas de `route`
em `_CALLER_ROUTE_SQL` textualmente iguais às de `outbox._TARGETS_SQL`.

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
Nada aqui toca banco. O gatilho de verdade recusando (e o re-toque o
provocando), o `delete` + `insert` da matriz e dos destinos, o outbox
enfileirando a partir de um desvio real e o sender contando "1 esperando" com
o gate fechado são `scripts/97_teste_canais.py`, oitava parte.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from operax.alertas import outbox
from operax.alertas.ciclo import Cycle
from server.models import AlertRuleWrite, ContactWrite
from server.routers import canais, canais_regras
from tests.conftest import TENANT_ID
from tests.test_canais_credencial import _all_text
from tests.test_canais_templates import (
    AnsweringScope,
    TimedScopeContext,
    _statements,
    _TriggerRefusal,
)

CONTACT_ID = UUID("88888888-8888-4888-8888-888888888801")
OTHER_CONTACT_ID = UUID("88888888-8888-4888-8888-888888888802")
GROUP_ID = UUID("88888888-8888-4888-8888-888888888803")
UNIT_ID = UUID("88888888-8888-4888-8888-8888888888c1")
RULE_ID = UUID("88888888-8888-4888-8888-8888888888d1")
TARGET_ID = UUID("88888888-8888-4888-8888-8888888888e1")
QUEUE_ID = UUID("88888888-8888-4888-8888-8888888888f1")
AUDIT_RULE_ID = UUID("88888888-8888-4888-8888-8888888888d2")

#: O e-mail do token de `conftest.issue_token` — é por ele que o teste acha o
#: contato do chamador.
CALLER_EMAIL = "gestor@kastropark.com.br"
CALLER_PHONE = "+5521999990001"
#: O número do PRIMEIRO contato do tenant, que NÃO é o chamador (mutação m4).
FIRST_CONTACT_PHONE = "+5511999990002"

#: A frase do gatilho `util.validate_alert_target` (migration 06). O `97` a
#: executa; aqui o stub a levanta e o teste afirma que ela chega literal.
TRIGGER_PHRASE = "Alerta de conteúdo individual não pode ter grupo como destinatário."

CONTACT_WRITE: dict[str, Any] = {
    "name": "Gestora Unidade",
    "whatsapp": "+5511999990000",
    "email": "gestora@exemplo.test",
    "type": "person",
}
RULE_WRITE: dict[str, Any] = {
    "name": "Resumo diário",
    "channel": "whatsapp",
    "content": "aggregate",
    "template_code": "deviation_summary",
}
CONTACT_CONTRACT = {"id", "name", "whatsapp", "email", "type", "active", "units"}
RULE_CONTRACT = {
    "id",
    "name",
    "deviation_type",
    "scope_unit_id",
    "scope_unit_name",
    "content",
    "channel",
    "cron_window",
    "threshold_minutes",
    "threshold_occurrences",
    "muted_until",
    "template_code",
    "active",
    "targets",
    "blocked_reason",
}


def contact_row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": CONTACT_ID,
        "name": "Gestora Unidade",
        "whatsapp": "+5511999990000",
        "email": "gestora@exemplo.test",
        "type": "person",
        "active": True,
        "units": [],
    } | overrides


def target(**overrides: Any) -> dict[str, Any]:
    return {
        "id": str(TARGET_ID),
        "contact_id": str(CONTACT_ID),
        "contact_name": "Gestora Unidade",
        "contact_active": True,
        "responsibility": None,
    } | overrides


def rule_row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": RULE_ID,
        "name": "Resumo diário",
        "deviation_type": None,
        "scope_unit_id": None,
        "scope_unit_name": None,
        "content": "aggregate",
        "channel": "whatsapp",
        "cron_window": None,
        "threshold_minutes": None,
        "threshold_occurrences": None,
        "muted_until": None,
        "template_code": "deviation_summary",
        "active": False,
        "targets": [target()],
    } | overrides


def visible_rule(**overrides: Any) -> dict[str, Any]:
    """Uma linha de `_VISIBLE_RULE_SQL`."""
    return {
        "id": RULE_ID,
        "name": "Resumo diário",
        "content": "aggregate",
        "channel": "whatsapp",
        "template_code": "deviation_summary",
        "active": False,
        "scope_unit_id": None,
    } | overrides


def readiness(provider: str = "z_api", *, ready: bool = True) -> dict[str, Any]:
    """Uma linha de `fn_channel_readiness` para a linha de WhatsApp."""
    return {
        "provider": provider,
        "official": provider == "meta_cloud",
        "templates_total": 1,
        "templates_approved": 1 if ready else 0,
        "rules_blocked": 0,
        "health_status": None,
        "health_changed_at": None,
        "ready": ready,
    }


def bot(*, ready: bool) -> dict[str, Any]:
    return readiness("telegram", ready=ready)


def blocked(
    name: str = "Resumo diário",
    code: str | None = "deviation_summary",
    status: str | None = "draft",
) -> dict[str, Any]:
    """Uma linha de `canais._BLOCKED_SQL`."""
    return {"rule_name": name, "template_code": code, "meta_status": status}


def caller_route(**overrides: Any) -> dict[str, Any]:
    """Uma linha de `_CALLER_ROUTE_SQL`: o chamador, sem Telegram."""
    return {
        "contact_id": CONTACT_ID,
        "contact_type": "person",
        "whatsapp": CALLER_PHONE,
        "email": CALLER_EMAIL,
        "telegram_external_id": None,
        "telegram_ready": False,
    } | overrides


@dataclass
class Stubs:
    user: AnsweringScope
    bound: AnsweringScope
    bound_ctx: TimedScopeContext
    timeline: list[str] = field(default_factory=list)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Stubs]:
    """Os dois escopos, com as respostas chaveadas pela INSTRUÇÃO inteira —
    o marcador é o próprio texto do SQL, então nenhuma resposta vaza para
    outra consulta por um substring em comum."""

    def install(
        *,
        admin: bool = True,
        contacts: list[dict[str, Any]] | None = None,
        visible_contact: dict[str, Any] | None | str = "default",
        visible_contacts: list[dict[str, Any]] | None = None,
        visible_units: list[dict[str, Any]] | None = None,
        rules: list[dict[str, Any]] | None = None,
        rule: dict[str, Any] | None | str = "default",
        deviation_type: dict[str, Any] | None | str = "default",
        template: dict[str, Any] | None | str = "default",
        readiness_rows: list[dict[str, Any]] | None = None,
        blocked_rows: list[dict[str, Any]] | None = None,
        caller: dict[str, Any] | None | str = "default",
        unit: dict[str, Any] | None | str = "default",
        active_targets: int = 1,
        active_rules: list[dict[str, Any]] | None = None,
        last_responsible: list[dict[str, Any]] | None = None,
        non_group: list[dict[str, Any]] | None = None,
        deactivate: dict[str, Any] | None | str = "default",
        revalidate: Any = None,
        insert_targets: Any = None,
        route: Any = "default",
        provider: dict[str, Any] | None | str = "default",
        enqueue: Any = "default",
    ) -> Stubs:
        timeline: list[str] = []
        if visible_contact == "default":
            visible_contact = {
                "id": CONTACT_ID,
                "name": "Gestora Unidade",
                "type": "person",
                "active": True,
            }
        if rule == "default":
            rule = visible_rule()
        if template == "default":
            template = {"code": "deviation_summary", "variables": ["unit", "link"]}
        if caller == "default":
            caller = {"id": CONTACT_ID, "name": "Gestora Unidade"}
        if deviation_type == "default":
            deviation_type = {"code": "late_entry"}
        if unit == "default":
            unit = {"id": UNIT_ID, "name": "Unidade Centro"}
        if deactivate == "default":
            deactivate = {"id": CONTACT_ID}
        if route == "default":
            route = caller_route()
        if provider == "default":
            provider = {"provider": "z_api"}
        if enqueue == "default":
            enqueue = {"id": QUEUE_ID}
        user = AnsweringScope(
            {
                canais._PERMISSION_SQL: {"admin": admin},
                canais_regras._CONTACTS_SQL: contacts if contacts is not None else [contact_row()],
                canais_regras._VISIBLE_CONTACT_SQL: visible_contact,
                canais_regras._VISIBLE_CONTACTS_SQL: (
                    visible_contacts
                    if visible_contacts is not None
                    else [
                        {
                            "id": CONTACT_ID,
                            "name": "Gestora Unidade",
                            "type": "person",
                            "active": True,
                        }
                    ]
                ),
                canais_regras._VISIBLE_UNITS_SQL: (
                    visible_units
                    if visible_units is not None
                    else [{"id": UNIT_ID, "name": "Unidade Centro"}]
                ),
                canais_regras._RULES_SQL: rules if rules is not None else [rule_row()],
                canais_regras._VISIBLE_RULE_SQL: rule,
                canais_regras._DEVIATION_TYPE_SQL: deviation_type,
                outbox._TEMPLATE_SQL: template,
                canais._READINESS_SQL: readiness_rows
                if readiness_rows is not None
                else [readiness()],
                canais._BLOCKED_SQL: blocked_rows if blocked_rows is not None else [],
                canais_regras._CALLER_CONTACT_SQL: caller,
                canais_regras._TEST_UNIT_SQL: unit,
            }
        )
        bound = AnsweringScope(
            {
                canais_regras._INSERT_CONTACT_SQL: {
                    "id": CONTACT_ID,
                    **CONTACT_WRITE,
                    "active": True,
                },
                canais_regras._UPDATE_CONTACT_SQL: {
                    "id": CONTACT_ID,
                    **CONTACT_WRITE,
                    "active": True,
                    "before": {"id": str(CONTACT_ID), "name": "Antes", "type": "person"},
                },
                canais_regras._DEACTIVATE_CONTACT_SQL: deactivate,
                canais_regras._CONTACT_ACTIVE_RULES_SQL: active_rules or [],
                canais_regras._LAST_RESPONSIBLE_RULES_SQL: last_responsible or [],
                canais_regras._NON_GROUP_RESPONSIBILITY_SQL: non_group or [],
                canais_regras._DELETE_UNIT_RESPONSIBLE_SQL: [
                    {"unit_id": UNIT_ID, "responsibility": "hr", "is_primary": False}
                ],
                canais_regras._INSERT_UNIT_RESPONSIBLE_SQL: lambda p: [
                    {"unit_id": u, "responsibility": r, "is_primary": pr}
                    for u, r, pr in zip(
                        p["unit_ids"], p["responsibilities"], p["primaries"], strict=True
                    )
                ],
                canais_regras._REVALIDATE_CONTACT_TARGETS_SQL: revalidate,
                canais_regras._REVALIDATE_RULE_TARGETS_SQL: revalidate,
                canais_regras._INSERT_RULE_SQL: {"id": RULE_ID},
                canais_regras._UPDATE_RULE_SQL: lambda p: {
                    "id": RULE_ID,
                    "name": p["name"],
                    "channel": p["channel"],
                    "template_code": p["template_code"],
                    "active": rule["active"] if isinstance(rule, dict) else False,
                    "before": {"id": str(RULE_ID), "name": "Antes"},
                },
                canais_regras._SET_RULE_ACTIVE_SQL: lambda p: {
                    "id": RULE_ID,
                    "active": p["active"],
                },
                canais_regras._MUTE_RULE_SQL: lambda p: {"id": RULE_ID, "muted_until": p["until"]},
                canais_regras._ACTIVE_TARGETS_SQL: {"n": active_targets},
                canais._BLOCKED_SQL: blocked_rows if blocked_rows is not None else [],
                canais_regras._DELETE_TARGETS_SQL: [
                    {"contact_id": OTHER_CONTACT_ID, "responsibility": None}
                ],
                canais_regras._INSERT_TARGETS_SQL: (
                    insert_targets
                    if insert_targets is not None
                    else (
                        lambda p: [
                            {"id": TARGET_ID, "contact_id": c, "responsibility": r}
                            for c, r in zip(p["contact_ids"], p["responsibilities"], strict=True)
                        ]
                    )
                ),
                outbox._PROVIDER_SQL: provider,
                canais_regras._CALLER_ROUTE_SQL: route,
                canais_regras._TEST_FACTS_SQL: {"total_events": 3, "deviation_minutes": 47},
                outbox._TEMPLATE_SQL: template,
                outbox._ENQUEUE_SQL: enqueue,
                canais_regras._AUDIT_SQL: None,
            }
        )
        bound_ctx = TimedScopeContext(bound, timeline, "tenant_scope")
        monkeypatch.setattr(
            canais, "user_scope", lambda _t: TimedScopeContext(user, timeline, "user_scope")
        )
        monkeypatch.setattr(
            canais_regras, "user_scope", lambda _t: TimedScopeContext(user, timeline, "user_scope")
        )
        monkeypatch.setattr(canais_regras, "tenant_scope", lambda _t: bound_ctx)
        return Stubs(user=user, bound=bound, bound_ctx=bound_ctx, timeline=timeline)

    return install


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


def _audits(stubs: Stubs) -> list[dict[str, Any]]:
    return [p for _, p in _statements(stubs.bound, "insert into app.audit_log")]


# ---------------------------------------------------------------------------
# Portão 1 — quem escreve é admin; o 403 chega antes de qualquer transação
# ---------------------------------------------------------------------------
WRITE_ROUTES: list[tuple[str, str, dict[str, Any] | None, str]] = [
    ("post", "/canais/destinatarios/contatos", CONTACT_WRITE, "Gravar destinatários"),
    ("put", f"/canais/destinatarios/contatos/{CONTACT_ID}", CONTACT_WRITE, "Gravar destinatários"),
    (
        "post",
        f"/canais/destinatarios/contatos/{CONTACT_ID}/desativar",
        None,
        "Gravar destinatários",
    ),
    (
        "put",
        f"/canais/destinatarios/contatos/{CONTACT_ID}/unidades",
        {"units": [{"unit_id": str(UNIT_ID), "responsibility": "hr", "is_primary": True}]},
        "Gravar destinatários",
    ),
    ("post", "/canais/regras", RULE_WRITE, "Gravar regras"),
    ("put", f"/canais/regras/{RULE_ID}", RULE_WRITE, "Gravar regras"),
    (
        "put",
        f"/canais/regras/{RULE_ID}/destinos",
        {"targets": [{"contact_id": str(CONTACT_ID)}]},
        "Gravar regras",
    ),
    ("post", f"/canais/regras/{RULE_ID}/ligar", None, "Gravar regras"),
    ("post", f"/canais/regras/{RULE_ID}/desligar", None, "Gravar regras"),
    (
        "post",
        f"/canais/regras/{RULE_ID}/silenciar",
        {"until": "2099-01-01T00:00:00+00:00"},
        "Gravar regras",
    ),
    ("post", f"/canais/regras/{RULE_ID}/testar", None, "Testar uma regra"),
]


@pytest.mark.parametrize(("method", "path", "body", "frase"), WRITE_ROUTES)
def test_toda_escrita_sem_admin_e_403_com_tenant_scope_nunca_aberto(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    method: str,
    path: str,
    body: dict[str, Any] | None,
    frase: str,
) -> None:
    """⛔ Mutação m3: tirar o `_require_admin` de qualquer rota de escrita deixa
    a linha dela vermelha aqui."""
    stubs = db(admin=False)

    resposta = getattr(client, method)(path, json=body, headers=cabecalho)

    assert resposta.status_code == 403, resposta.text
    assert resposta.json()["detail"].startswith(frase)
    assert stubs.bound_ctx.opened == 0
    assert stubs.bound.statements == []
    # A única coisa que rodou como o usuário foi a pergunta à policy.
    assert stubs.user.statements == [canais._PERMISSION_SQL]


def test_a_lista_de_contatos_e_de_qualquer_membro_e_roda_como_o_usuario(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`contact_read` é `has_tenant` e `unit_responsible_read` é `can_see_unit`:
    quem recorta é a policy, não a rota — nem `is_admin` é perguntado."""
    stubs = db(
        admin=False,
        contacts=[
            contact_row(
                units=[
                    {
                        "unit_id": str(UNIT_ID),
                        "unit_name": "Centro",
                        "responsibility": "unit_manager",
                        "is_primary": True,
                    }
                ]
            ),
            contact_row(id=OTHER_CONTACT_ID, active=False),
        ],
    )

    resposta = client.get("/canais/destinatarios/contatos", headers=cabecalho)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert [c["id"] for c in corpo] == [str(CONTACT_ID), str(OTHER_CONTACT_ID)]
    assert set(corpo[0]) == CONTACT_CONTRACT
    assert corpo[0]["units"] == [
        {
            "unit_id": str(UNIT_ID),
            "unit_name": "Centro",
            "responsibility": "unit_manager",
            "is_primary": True,
        }
    ]
    assert corpo[1]["active"] is False
    assert stubs.bound_ctx.opened == 0
    assert stubs.user.statements == [canais_regras._CONTACTS_SQL]
    assert stubs.user.params[0]["tenant_id"] == str(TENANT_ID)
    assert stubs.user.params[0]["contact_id"] is None


def test_a_lista_de_regras_e_do_admin_e_roda_como_o_usuario(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`regra_destino_admin` é a única policy dos destinos: um membro comum
    receberia toda regra com `targets: []` e um "nenhum destino" falso."""
    stubs = db(admin=False)
    assert client.get("/canais/regras", headers=cabecalho).status_code == 403

    stubs = db(
        rules=[
            rule_row(active=True),
            rule_row(id=AUDIT_RULE_ID, name="E-mail", channel="email", template_code=None),
        ]
    )
    resposta = client.get("/canais/regras", headers=cabecalho)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert [r["id"] for r in corpo] == [str(RULE_ID), str(AUDIT_RULE_ID)]
    assert set(corpo[0]) == RULE_CONTRACT
    assert corpo[0]["targets"] == [target()]
    assert corpo[0]["blocked_reason"] is None
    assert corpo[1]["blocked_reason"] is None  # desligada: nada a apontar
    assert stubs.bound_ctx.opened == 0
    assert stubs.user.statements == [
        canais._PERMISSION_SQL,
        canais_regras._RULES_SQL,
        canais._READINESS_SQL,
        canais._BLOCKED_SQL,
    ]


# ---------------------------------------------------------------------------
# Portão 2 — 404 antes de escrever, como o usuário
# ---------------------------------------------------------------------------
def test_contato_de_outro_tenant_e_404_antes_de_qualquer_escrita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(visible_contact=None)

    for method, path, body in (
        ("put", f"/canais/destinatarios/contatos/{OTHER_CONTACT_ID}", CONTACT_WRITE),
        ("post", f"/canais/destinatarios/contatos/{OTHER_CONTACT_ID}/desativar", None),
        ("put", f"/canais/destinatarios/contatos/{OTHER_CONTACT_ID}/unidades", {"units": []}),
    ):
        resposta = getattr(client, method)(path, json=body, headers=cabecalho)
        assert resposta.status_code == 404, resposta.text
        assert resposta.json()["detail"] == "Contato não encontrado."
    assert stubs.bound_ctx.opened == 0
    assert stubs.bound.statements == []


def test_unidade_de_outro_tenant_na_matriz_e_404_antes_de_escrever(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """O stub emula o predicado: só a unidade do tenant volta; a outra falta."""
    stubs = db(visible_units=[{"id": UNIT_ID, "name": "Centro"}])
    outra = "99999999-9999-4999-8999-999999999999"

    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/unidades",
        json={
            "units": [
                {"unit_id": str(UNIT_ID), "responsibility": "hr"},
                {"unit_id": outra, "responsibility": "hr"},
            ]
        },
        headers=cabecalho,
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Unidade não encontrada."
    assert stubs.bound_ctx.opened == 0
    [(_, params)] = _statements(stubs.user, "u.id = any(")
    assert sorted(params["unit_ids"]) == sorted([str(UNIT_ID), outra])


def test_regra_de_outro_tenant_e_404_antes_de_qualquer_escrita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(rule=None)

    for method, path, body in (
        ("put", f"/canais/regras/{RULE_ID}", RULE_WRITE),
        ("put", f"/canais/regras/{RULE_ID}/destinos", {"targets": []}),
        ("post", f"/canais/regras/{RULE_ID}/ligar", None),
        ("post", f"/canais/regras/{RULE_ID}/desligar", None),
        ("post", f"/canais/regras/{RULE_ID}/silenciar", {"until": "2099-01-01T00:00:00+00:00"}),
        ("post", f"/canais/regras/{RULE_ID}/testar", None),
    ):
        resposta = getattr(client, method)(path, json=body, headers=cabecalho)
        assert resposta.status_code == 404, resposta.text
        assert resposta.json()["detail"] == "Regra não encontrada."
    assert stubs.bound_ctx.opened == 0


def test_contato_de_outro_tenant_como_destino_e_404_antes_de_escrever(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(visible_contacts=[])

    resposta = client.put(
        f"/canais/regras/{RULE_ID}/destinos",
        json={"targets": [{"contact_id": str(OTHER_CONTACT_ID)}]},
        headers=cabecalho,
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Contato não encontrado."
    assert stubs.bound_ctx.opened == 0


@pytest.mark.parametrize(
    ("campo", "valor", "detail"),
    [
        ("deviation_type", "inventado", "Tipo de desvio não encontrado."),
        ("scope_unit_id", "99999999-9999-4999-8999-999999999999", "Unidade não encontrada."),
    ],
)
def test_referencias_da_regra_sao_conferidas_como_o_usuario_antes_de_escrever(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    campo: str,
    valor: str,
    detail: str,
) -> None:
    stubs = db(deviation_type=None, visible_units=[])

    resposta = client.post("/canais/regras", json={**RULE_WRITE, campo: valor}, headers=cabecalho)

    assert resposta.status_code == 404, resposta.text
    assert resposta.json()["detail"] == detail
    assert stubs.bound_ctx.opened == 0


def test_template_inexistente_na_criacao_e_422_nomeado_sem_escrita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(template=None)

    resposta = client.post("/canais/regras", json=RULE_WRITE, headers=cabecalho)

    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["code"] == "template_not_found"
    assert "deviation_summary" in resposta.json()["detail"]
    assert stubs.bound_ctx.opened == 0
    # A existência é perguntada com a instrução do outbox — a mesma que
    # decide, na entrega, se o template está lá.
    [(statement, params)] = _statements(stubs.user, "from app.message_template")
    assert statement == outbox._TEMPLATE_SQL
    assert params == {"tenant_id": str(TENANT_ID), "code": "deviation_summary"}


# ---------------------------------------------------------------------------
# Portão 3 — a regra nasce desligada
# ---------------------------------------------------------------------------
def test_post_regras_com_active_no_corpo_e_422_e_nada_e_gravado(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """⛔ Mutação m2: aceitar `active` no schema e honrá-lo no insert deixa
    este e o próximo vermelhos."""
    stubs = db()

    resposta = client.post("/canais/regras", json={**RULE_WRITE, "active": True}, headers=cabecalho)

    assert resposta.status_code == 422, resposta.text
    assert any(e["loc"][-1] == "active" for e in resposta.json()["detail"])
    assert stubs.bound_ctx.opened == 0
    assert "active" not in AlertRuleWrite.model_fields
    assert AlertRuleWrite.model_config.get("extra") == "forbid"


def test_o_insert_da_regra_leva_o_literal_false_e_nenhum_parametro_active(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()

    resposta = client.post("/canais/regras", json=RULE_WRITE, headers=cabecalho)

    assert resposta.status_code == 201, resposta.text
    [(statement, params)] = _statements(stubs.bound, "insert into app.alert_rule\n")
    assert statement == canais_regras._INSERT_RULE_SQL
    assert re.search(r"%\(template_code\)s,\s*false\)", statement)
    assert "%(active)s" not in statement
    assert "active" not in params
    assert stubs.bound_ctx.exited_with is None
    [audit] = _audits(stubs)
    assert audit["action"] == "insert" and audit["entity"] == "alert_rule"
    assert audit["entity_id"] == str(RULE_ID)
    assert audit["depois"].obj["active"] is False
    assert set(resposta.json()) == RULE_CONTRACT


# ---------------------------------------------------------------------------
# Portão 4 — ligar é a única porta
# ---------------------------------------------------------------------------
def _ligar(client: TestClient, cabecalho: dict[str, str]):
    return client.post(f"/canais/regras/{RULE_ID}/ligar", headers=cabecalho)


def test_ligar_sem_destino_ativo_e_409_e_a_transacao_sai_por_excecao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """⛔ Mutação m1: `ligar` sem exigir destino deixa isto vermelho."""
    stubs = db(active_targets=0)

    resposta = _ligar(client, cabecalho)

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["code"] == "rule_has_no_target"
    # O `update` rodou e foi desfeito: a saída da transação é a exceção.
    assert stubs.bound_ctx.opened == 1
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError
    assert _statements(stubs.bound, "set active = %(active)s")
    assert _audits(stubs) == []


def test_ligar_conta_so_destino_ativo_com_a_instrucao_que_filtra_c_active() -> None:
    """O outbox filtra `c.active`; um destino cujo contato foi desativado não
    é destino. A instrução diz isso, e diz por responsabilidade também."""
    sql = canais_regras._ACTIVE_TARGETS_SQL
    assert "(t.contact_id is null or c.active)" in sql
    assert "c.tenant_id = r.tenant_id" in sql


@pytest.mark.parametrize(
    ("rule", "readiness_rows", "blocked_rows", "code"),
    [
        (visible_rule(template_code=None), [readiness()], [], "template_required"),
        (visible_rule(channel="both", template_code=None), [readiness()], [], "template_required"),
        (visible_rule(), [readiness()], [blocked(status=None)], "template_not_found"),
        (
            visible_rule(),
            [readiness("meta_cloud")],
            [blocked(status="pending")],
            "template_not_approved",
        ),
    ],
)
def test_ligar_com_mensageria_exige_template_presente_ativo_e_aprovado_no_oficial(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    rule: dict[str, Any],
    readiness_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    code: str,
) -> None:
    stubs = db(rule=rule, readiness_rows=readiness_rows, blocked_rows=blocked_rows)

    resposta = _ligar(client, cabecalho)

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["code"] == code
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError
    assert _audits(stubs) == []
    if code == "template_not_approved":
        assert "pending" in resposta.json()["detail"]


def test_template_nao_aprovado_no_provedor_nao_oficial_nao_impede_ligar(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """z_api renderiza o corpo local; a aprovação da Meta é do oficial."""
    stubs = db(readiness_rows=[readiness("z_api")], blocked_rows=[blocked(status="draft")])

    assert _ligar(client, cabecalho).status_code == 200
    assert stubs.bound_ctx.exited_with is None


def test_o_juiz_do_template_em_ligar_e_a_lista_de_conexoes_lida_depois_da_escrita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`_BLOCKED_SQL` só vê regra ligada: por isso roda DEPOIS do `update` e
    ANTES do commit, na mesma transação — o predicado é o da tela, não um novo."""
    stubs = db(
        rule=visible_rule(),
        readiness_rows=[readiness("meta_cloud")],
        blocked_rows=[blocked(status="rejected")],
    )

    _ligar(client, cabecalho)

    ordem = [s for s in stubs.bound.statements]
    assert ordem.index(canais_regras._SET_RULE_ACTIVE_SQL) < ordem.index(canais._BLOCKED_SQL)
    assert stubs.bound.params[ordem.index(canais._BLOCKED_SQL)] == {}


def test_ligar_com_tudo_liga_e_audita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(rules=[rule_row(active=True)])

    resposta = _ligar(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["active"] is True
    [(statement, params)] = _statements(stubs.bound, "set active = %(active)s")
    assert statement == canais_regras._SET_RULE_ACTIVE_SQL
    assert params == {"rule_id": str(RULE_ID), "active": True}
    assert stubs.bound_ctx.exited_with is None
    [audit] = _audits(stubs)
    assert audit["action"] == "update" and audit["entity"] == "alert_rule"
    assert audit["entity_id"] == str(RULE_ID)
    assert audit["antes"].obj == {"active": False} and audit["depois"].obj == {"active": True}
    # A pergunta ao canal é a função, como o usuário, antes da transação.
    assert stubs.timeline.index("user_scope:exit") < stubs.timeline.index("tenant_scope:enter")


def test_desligar_sempre_aceita_mesmo_sem_destino_e_sem_template(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(
        rule=visible_rule(active=True, template_code=None), active_targets=0, rules=[rule_row()]
    )

    resposta = client.post(f"/canais/regras/{RULE_ID}/desligar", headers=cabecalho)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["active"] is False
    [(_, params)] = _statements(stubs.bound, "set active = %(active)s")
    assert params["active"] is False
    assert not _statements(stubs.bound, "count(*)::int as n")
    [audit] = _audits(stubs)
    assert audit["antes"].obj == {"active": True} and audit["depois"].obj == {"active": False}


def test_silenciar_no_passado_e_422_e_no_futuro_grava_e_audita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()
    passado = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    resposta = client.post(
        f"/canais/regras/{RULE_ID}/silenciar", json={"until": passado}, headers=cabecalho
    )
    assert resposta.status_code == 422
    assert resposta.json()["code"] == "mute_in_past"
    assert stubs.bound_ctx.opened == 0

    # Sem fuso não é aceito: `AwareDatetime`.
    resposta = client.post(
        f"/canais/regras/{RULE_ID}/silenciar",
        json={"until": "2099-01-01T00:00:00"},
        headers=cabecalho,
    )
    assert resposta.status_code == 422

    futuro = datetime(2099, 1, 1, tzinfo=UTC)
    resposta = client.post(
        f"/canais/regras/{RULE_ID}/silenciar", json={"until": futuro.isoformat()}, headers=cabecalho
    )
    assert resposta.status_code == 200, resposta.text
    [(statement, params)] = _statements(stubs.bound, "set muted_until")
    assert statement == canais_regras._MUTE_RULE_SQL
    assert params["until"] == futuro
    [audit] = _audits(stubs)
    assert audit["entity"] == "alert_rule" and audit["depois"].obj == {
        "muted_until": futuro.isoformat()
    }

    resposta = client.post(
        f"/canais/regras/{RULE_ID}/silenciar", json={"until": None}, headers=cabecalho
    )
    assert resposta.status_code == 200
    assert _statements(stubs.bound, "set muted_until")[-1][1]["until"] is None


# ---------------------------------------------------------------------------
# Portão 5 — a regra 7 é do gatilho, e a frase é a dele
# ---------------------------------------------------------------------------
def test_destinos_traduz_a_recusa_do_gatilho_em_409_com_a_frase_dele(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """⛔ Mutação m5: engolir a `RaiseException` e seguir deixa isto vermelho —
    o status, o código, a frase e a saída da transação."""
    stubs = db(
        rule=visible_rule(content="individual"),
        visible_contacts=[
            {"id": GROUP_ID, "name": "Grupo", "type": "whatsapp_group", "active": True}
        ],
        insert_targets=_TriggerRefusal(TRIGGER_PHRASE),
    )

    resposta = client.put(
        f"/canais/regras/{RULE_ID}/destinos",
        json={"targets": [{"contact_id": str(GROUP_ID)}]},
        headers=cabecalho,
    )

    assert resposta.status_code == 409, resposta.text
    assert resposta.json() == {"detail": TRIGGER_PHRASE, "code": "individual_to_group"}
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError
    assert _audits(stubs) == []
    # E a rota não conhece a regra: o predicado é conteúdo × tipo, e o Python
    # nunca compara `content` com "individual".
    fonte = canais_regras.__file__
    with open(fonte, encoding="utf-8") as f:
        codigo = re.sub(r'"""[\s\S]*?"""|#.*', "", f.read())
    assert not re.search(
        r'==\s*"individual"|"individual"\s*==|\bindividual\b\s*(in|not in)\b', codigo
    )


def test_destinos_substitui_apaga_e_reinsere_na_mesma_transacao_e_audita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()

    resposta = client.put(
        f"/canais/regras/{RULE_ID}/destinos",
        json={"targets": [{"contact_id": str(CONTACT_ID)}, {"responsibility": "unit_manager"}]},
        headers=cabecalho,
    )

    assert resposta.status_code == 200, resposta.text
    ordem = stubs.bound.statements
    assert ordem.index(canais_regras._DELETE_TARGETS_SQL) < ordem.index(
        canais_regras._INSERT_TARGETS_SQL
    )
    assert stubs.bound_ctx.opened == 1
    [(_, params)] = _statements(stubs.bound, "insert into app.alert_rule_target")
    assert params["contact_ids"] == [str(CONTACT_ID), None]
    assert params["responsibilities"] == [None, "unit_manager"]
    [audit] = _audits(stubs)
    assert audit["entity"] == "alert_rule_target" and audit["entity_id"] == str(RULE_ID)
    assert audit["antes"].obj == [{"contact_id": str(OTHER_CONTACT_ID), "responsibility": None}]
    assert audit["depois"].obj == [
        {"contact_id": str(CONTACT_ID), "responsibility": None},
        {"contact_id": None, "responsibility": "unit_manager"},
    ]


def test_destinos_vazios_numa_regra_ligada_e_409_e_contato_inativo_e_422(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(rule=visible_rule(active=True), active_targets=0)
    resposta = client.put(
        f"/canais/regras/{RULE_ID}/destinos", json={"targets": []}, headers=cabecalho
    )
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "rule_has_no_target"
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError

    stubs = db(
        visible_contacts=[{"id": CONTACT_ID, "name": "X", "type": "person", "active": False}]
    )
    resposta = client.put(
        f"/canais/regras/{RULE_ID}/destinos",
        json={"targets": [{"contact_id": str(CONTACT_ID)}]},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert resposta.json()["code"] == "contact_inactive"
    assert stubs.bound_ctx.opened == 0


def test_put_da_regra_re_toca_os_destinos_e_a_frase_do_gatilho_e_o_409(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`content` → `individual` com grupo já cadastrado: o gatilho não dispara
    no `update` da regra (medido), então a rota re-toca cada destino e ele
    julga de novo. Sem o re-toque, a regra 7 ficaria aberta por esta porta."""
    stubs = db(revalidate=_TriggerRefusal(TRIGGER_PHRASE))

    resposta = client.put(
        f"/canais/regras/{RULE_ID}", json={**RULE_WRITE, "content": "individual"}, headers=cabecalho
    )

    assert resposta.status_code == 409, resposta.text
    assert resposta.json() == {"detail": TRIGGER_PHRASE, "code": "individual_to_group"}
    [(statement, params)] = _statements(stubs.bound, "set rule_id = t.rule_id")
    assert statement == canais_regras._REVALIDATE_RULE_TARGETS_SQL
    assert params == {"rule_id": str(RULE_ID)}
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError
    assert _audits(stubs) == []


def test_put_do_contato_re_toca_os_destinos_dele_e_a_frase_do_gatilho_e_o_409(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`type` → `whatsapp_group` num contato que é destino de regra individual:
    a outra porta que o gatilho não vigia sozinho."""
    stubs = db(revalidate=_TriggerRefusal(TRIGGER_PHRASE))

    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}",
        json={**CONTACT_WRITE, "type": "whatsapp_group"},
        headers=cabecalho,
    )

    assert resposta.status_code == 409, resposta.text
    assert resposta.json() == {"detail": TRIGGER_PHRASE, "code": "individual_to_group"}
    [(statement, params)] = _statements(stubs.bound, "set rule_id = t.rule_id")
    assert statement == canais_regras._REVALIDATE_CONTACT_TARGETS_SQL
    assert params == {"contact_id": str(CONTACT_ID)}
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError


def test_os_dois_re_toques_sao_updates_que_disparam_o_gatilho_sem_mudar_nada() -> None:
    for sql in (
        canais_regras._REVALIDATE_RULE_TARGETS_SQL,
        canais_regras._REVALIDATE_CONTACT_TARGETS_SQL,
    ):
        assert "update app.alert_rule_target t" in sql
        assert "set rule_id = t.rule_id" in sql
        assert "r.tenant_id = %(tenant_id)s" in sql


def test_put_numa_regra_ligada_que_ficaria_sem_template_e_409_e_nada_muda(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """Decisão: recusar, não desligar — o mesmo juiz de `ligar`, e a regra
    continua como estava."""
    stubs = db(rule=visible_rule(active=True))

    resposta = client.put(
        f"/canais/regras/{RULE_ID}", json={**RULE_WRITE, "template_code": None}, headers=cabecalho
    )

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["code"] == "template_required"
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError
    assert _audits(stubs) == []


def test_put_numa_regra_desligada_nao_exige_condicao_de_entrega(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(rule=visible_rule(active=False), active_targets=0)

    resposta = client.put(
        f"/canais/regras/{RULE_ID}", json={**RULE_WRITE, "template_code": None}, headers=cabecalho
    )

    assert resposta.status_code == 200, resposta.text
    assert not _statements(stubs.bound, "count(*)::int as n")
    [audit] = _audits(stubs)
    assert audit["entity"] == "alert_rule" and audit["action"] == "update"
    assert audit["antes"].obj == {"id": str(RULE_ID), "name": "Antes"}


# ---------------------------------------------------------------------------
# Desativar — nunca delete; 409 sob regra ligada
# ---------------------------------------------------------------------------
def test_desativar_contato_sob_regra_ligada_e_409_listando_as_regras(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(active_rules=[{"id": RULE_ID, "name": "Resumo diário"}])

    resposta = client.post(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/desativar", headers=cabecalho
    )

    assert resposta.status_code == 409, resposta.text
    corpo = resposta.json()
    assert corpo["code"] == "contact_in_active_rule"
    assert corpo["rules"] == [{"id": str(RULE_ID), "name": "Resumo diário"}]
    assert not _statements(stubs.bound, "set active = false")
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError


def test_desativar_o_ultimo_responsavel_de_regra_ligada_e_409_listando_as_regras(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """O destino por responsabilidade resolve pela matriz: desativar o único
    `unit_manager` ativo da unidade deixaria a regra ligada entregando a
    ninguém — o mesmo 409 do destino direto, com outro nome e outro remédio."""
    stubs = db(last_responsible=[{"id": RULE_ID, "name": "Resumo por unidade"}])

    resposta = client.post(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/desativar", headers=cabecalho
    )

    assert resposta.status_code == 409, resposta.text
    corpo = resposta.json()
    assert corpo["code"] == "contact_last_responsible"
    assert corpo["rules"] == [{"id": str(RULE_ID), "name": "Resumo por unidade"}]
    assert "outro responsável" in corpo["detail"]
    [(_, params)] = _statements(stubs.bound, canais_regras._LAST_RESPONSIBLE_RULES_SQL)
    # Desativar não mantém responsabilidade nenhuma: `kept` vazio.
    assert params == {
        "contact_id": str(CONTACT_ID),
        "kept_unit_ids": [],
        "kept_responsibilities": [],
    }
    assert not _statements(stubs.bound, "set active = false")
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError


def test_desativar_e_active_false_com_auditoria_e_nunca_delete(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """⛔ Mutação m6: um `delete from app.contact` deixa isto vermelho — pela
    instrução que rodou e pela varredura do módulo."""
    stubs = db(contacts=[contact_row(active=False)])

    resposta = client.post(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/desativar", headers=cabecalho
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["active"] is False
    [(statement, params)] = _statements(stubs.bound, "set active = false")
    assert statement == canais_regras._DEACTIVATE_CONTACT_SQL
    assert params == {"contact_id": str(CONTACT_ID)}
    assert not any("delete" in s.lower() for s in stubs.bound.statements)
    [audit] = _audits(stubs)
    assert audit["entity"] == "contact" and audit["entity_id"] == str(CONTACT_ID)
    assert audit["antes"].obj == {"active": True} and audit["depois"].obj == {"active": False}


def test_o_modulo_nao_apaga_contato_nem_regra() -> None:
    """Os únicos `delete` do módulo são das duas linhas de ligação."""
    deletes = re.findall(
        r"delete from app\.(\w+)",
        "\n".join(sql for name, sql in vars(canais_regras).items() if name.endswith("_SQL")),
    )
    assert sorted(deletes) == ["alert_rule_target", "unit_responsible"]


def test_desativar_ja_inativo_e_idempotente_e_nao_audita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(deactivate=None, contacts=[contact_row(active=False)])

    resposta = client.post(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/desativar", headers=cabecalho
    )

    assert resposta.status_code == 200
    assert _audits(stubs) == []


# ---------------------------------------------------------------------------
# Contatos — criar, editar, a matriz
# ---------------------------------------------------------------------------
def test_criar_contato_grava_audita_e_devolve_relido_como_o_usuario(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()

    resposta = client.post("/canais/destinatarios/contatos", json=CONTACT_WRITE, headers=cabecalho)

    assert resposta.status_code == 201, resposta.text
    assert set(resposta.json()) == CONTACT_CONTRACT
    [(statement, params)] = _statements(stubs.bound, "insert into app.contact")
    assert statement == canais_regras._INSERT_CONTACT_SQL
    assert params == CONTACT_WRITE
    [audit] = _audits(stubs)
    assert audit["action"] == "insert" and audit["entity"] == "contact"
    # A trilha leva o contato sem o número inteiro (SPEC §5, destino em claro).
    assert audit["depois"].obj == {**CONTACT_WRITE, "whatsapp": "•••0000", "active": True}
    assert CONTACT_WRITE["whatsapp"] not in _all_text(audit)
    # A releitura é como o usuário, com o id do gravado, depois da transação.
    [(_, params)] = _statements(stubs.user, canais_regras._CONTACTS_SQL)
    assert params["contact_id"] == str(CONTACT_ID)
    assert stubs.timeline[-2:] == ["user_scope:enter", "user_scope:exit"]


@pytest.mark.parametrize(
    "corpo",
    [
        {"name": "Sem endereço", "type": "person"},
        {"name": "Fora do check", "whatsapp": "11 99999-0000"},
        {"name": "Tipo inventado", "whatsapp": "+5511999990000", "type": "telegram_group"},
        {"name": "Extra", "whatsapp": "+5511999990000", "active": False},
        {"name": "E-mail sem arroba", "email": "gestora"},
    ],
)
def test_a_forma_do_contato_e_422_antes_de_qualquer_escopo(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], corpo: dict[str, Any]
) -> None:
    stubs = db()

    resposta = client.post("/canais/destinatarios/contatos", json=corpo, headers=cabecalho)

    assert resposta.status_code == 422, resposta.text
    assert stubs.bound_ctx.opened == 0
    assert stubs.user.statements == []


def test_a_validacao_do_whatsapp_espelha_o_check_do_banco() -> None:
    for valido in ("+5511999990000", "5511999990000", "1234567890"):
        ContactWrite(name="x", whatsapp=valido)
    for invalido in ("+55 11 99999-0000", "123", "+" + "9" * 16):
        with pytest.raises(ValidationError):
            ContactWrite(name="x", whatsapp=invalido)


def test_editar_contato_grava_com_antes_e_relê(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()

    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}", json=CONTACT_WRITE, headers=cabecalho
    )

    assert resposta.status_code == 200, resposta.text
    [(statement, params)] = _statements(stubs.bound, "update app.contact c")
    assert statement == canais_regras._UPDATE_CONTACT_SQL
    assert params == {"contact_id": str(CONTACT_ID), **CONTACT_WRITE}
    [audit] = _audits(stubs)
    assert audit["action"] == "update" and audit["entity"] == "contact"
    assert audit["antes"].obj == {"name": "Antes", "type": "person", "whatsapp": None}
    assert audit["depois"].obj == {**CONTACT_WRITE, "whatsapp": "•••0000", "active": True}
    assert CONTACT_WRITE["whatsapp"] not in _all_text(audit)


def test_um_contato_com_responsabilidade_que_nao_e_group_nao_vira_grupo(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """A quarta porta da regra 7 pelo outro lado: `PUT /unidades` recusa grupo
    como `unit_manager`, mas pessoa → `unit_manager` → `type = whatsapp_group`
    chegava ao mesmo estado com três 2xx. A cerca é a mesma, antes do update."""
    stubs = db(non_group=[{"unit_id": UNIT_ID, "responsibility": "unit_manager"}])
    grupo = {**CONTACT_WRITE, "type": "whatsapp_group"}

    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}", json=grupo, headers=cabecalho
    )

    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["code"] == "group_responsibility"
    assert not _statements(stubs.bound, "update app.contact c")
    assert not _audits(stubs)
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError

    # O positivo, na ordem: sem responsabilidade que não seja `group`, a
    # consulta roda ANTES do update e o update acontece.
    stubs = db(non_group=[])
    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}", json=grupo, headers=cabecalho
    )
    assert resposta.status_code == 200, resposta.text
    ordem = stubs.bound.statements
    assert ordem.index(canais_regras._NON_GROUP_RESPONSIBILITY_SQL) < ordem.index(
        canais_regras._UPDATE_CONTACT_SQL
    )

    # Uma pessoa continuando pessoa não paga a consulta.
    stubs = db(non_group=[{"unit_id": UNIT_ID, "responsibility": "unit_manager"}])
    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}", json=CONTACT_WRITE, headers=cabecalho
    )
    assert resposta.status_code == 200, resposta.text
    assert canais_regras._NON_GROUP_RESPONSIBILITY_SQL not in stubs.bound.statements


def test_a_matriz_e_apagada_e_reinserida_na_mesma_transacao_com_a_trilha(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()
    units = [
        {"unit_id": str(UNIT_ID), "responsibility": "unit_manager", "is_primary": True},
        {"unit_id": str(UNIT_ID), "responsibility": "hr", "is_primary": False},
    ]

    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/unidades",
        json={"units": units},
        headers=cabecalho,
    )

    assert resposta.status_code == 200, resposta.text
    ordem = stubs.bound.statements
    assert ordem.index(canais_regras._DELETE_UNIT_RESPONSIBLE_SQL) < ordem.index(
        canais_regras._INSERT_UNIT_RESPONSIBLE_SQL
    )
    assert stubs.bound_ctx.opened == 1
    [(_, params)] = _statements(stubs.bound, "insert into app.unit_responsible")
    assert params["unit_ids"] == [str(UNIT_ID), str(UNIT_ID)]
    assert params["responsibilities"] == ["unit_manager", "hr"]
    assert params["primaries"] == [True, False]
    [audit] = _audits(stubs)
    assert audit["entity"] == "unit_responsible" and audit["entity_id"] == str(CONTACT_ID)
    assert audit["antes"].obj == [
        {"unit_id": str(UNIT_ID), "responsibility": "hr", "is_primary": False}
    ]
    assert audit["depois"].obj == units


def test_tirar_da_matriz_a_responsabilidade_de_regra_ligada_e_409_antes_de_apagar(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`PUT /unidades` sem a responsabilidade que uma regra ligada resolve — e
    sem outro responsável ativo na unidade — é a mesma cerca de `desativar`:
    409 listando as regras, e a matriz não é tocada. O que a matriz nova
    repete vai em `kept`, porque manter não é perder."""
    stubs = db(last_responsible=[{"id": RULE_ID, "name": "Resumo por unidade"}])
    units = [{"unit_id": str(UNIT_ID), "responsibility": "hr", "is_primary": False}]

    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/unidades",
        json={"units": units},
        headers=cabecalho,
    )

    assert resposta.status_code == 409, resposta.text
    corpo = resposta.json()
    assert corpo["code"] == "contact_last_responsible"
    assert corpo["rules"] == [{"id": str(RULE_ID), "name": "Resumo por unidade"}]
    [(_, params)] = _statements(stubs.bound, canais_regras._LAST_RESPONSIBLE_RULES_SQL)
    assert params == {
        "contact_id": str(CONTACT_ID),
        "kept_unit_ids": [str(UNIT_ID)],
        "kept_responsibilities": ["hr"],
    }
    assert canais_regras._DELETE_UNIT_RESPONSIBLE_SQL not in stubs.bound.statements
    assert canais_regras._INSERT_UNIT_RESPONSIBLE_SQL not in stubs.bound.statements
    assert not _audits(stubs)
    assert stubs.bound_ctx.exited_with is canais_regras._RefusedError


def test_a_consulta_do_ultimo_responsavel_so_conta_contato_ativo_e_regra_ligada() -> None:
    """O predicado é o do outbox: resolve quem está ATIVO. Os três `active`
    e a exclusão do que a matriz nova mantém são o que a consulta afirma."""
    sql = canais_regras._LAST_RESPONSIBLE_RULES_SQL
    assert "join app.contact me on me.id = ur.contact_id and me.active" in sql
    assert "join app.contact c on c.id = o.contact_id and c.active" in sql
    assert "and r.active" in sql
    assert "o.contact_id <> ur.contact_id" in sql
    assert "unnest(%(kept_unit_ids)s::uuid[], %(kept_responsibilities)s::text[])" in sql
    assert "r.scope_unit_id is null or r.scope_unit_id = ur.unit_id" in sql


def test_um_grupo_so_entra_na_matriz_como_group(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """O gatilho da regra 7 só vê `responsibility = 'group'` no destino por
    responsabilidade: um grupo como `unit_manager` seria resolvido pelo outbox
    para uma regra individual sem recusa. A porta fecha aqui, antes de escrever."""
    stubs = db(
        visible_contact={"id": GROUP_ID, "name": "Grupo", "type": "whatsapp_group", "active": True}
    )

    resposta = client.put(
        f"/canais/destinatarios/contatos/{GROUP_ID}/unidades",
        json={"units": [{"unit_id": str(UNIT_ID), "responsibility": "unit_manager"}]},
        headers=cabecalho,
    )
    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["code"] == "group_responsibility"
    assert stubs.bound_ctx.opened == 0

    resposta = client.put(
        f"/canais/destinatarios/contatos/{GROUP_ID}/unidades",
        json={"units": [{"unit_id": str(UNIT_ID), "responsibility": "group"}]},
        headers=cabecalho,
    )
    assert resposta.status_code == 200, resposta.text


def test_a_matriz_vazia_so_apaga_e_a_repetida_e_422(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()
    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/unidades",
        json={"units": []},
        headers=cabecalho,
    )
    assert resposta.status_code == 200
    assert not _statements(stubs.bound, "insert into app.unit_responsible")
    assert len(_audits(stubs)) == 1

    repetida = [{"unit_id": str(UNIT_ID), "responsibility": "hr"}] * 2
    stubs = db()
    resposta = client.put(
        f"/canais/destinatarios/contatos/{CONTACT_ID}/unidades",
        json={"units": repetida},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert stubs.bound_ctx.opened == 0


# ---------------------------------------------------------------------------
# Portão 6 — o teste vai para quem clicou
# ---------------------------------------------------------------------------
def _testar(client: TestClient, cabecalho: dict[str, str]):
    return client.post(f"/canais/regras/{RULE_ID}/testar", headers=cabecalho)


def test_testar_enfileira_uma_linha_com_destino_no_chamador_e_a_chave_da_casa(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """⛔ Mutação m4: destino no primeiro contato do tenant em vez do chamador
    deixa isto vermelho — pelo e-mail perguntado, pelo contato roteado e pelo
    destino gravado."""
    # O primeiro contato do tenant NÃO é o chamador; a rota do stub responde
    # pelo contato perguntado — e é o destino gravado que denuncia a mutação.
    stubs = db(
        contacts=[contact_row(id=OTHER_CONTACT_ID, whatsapp=FIRST_CONTACT_PHONE), contact_row()],
        route=lambda p: (
            caller_route()
            if p["contact_id"] == str(CONTACT_ID)
            else caller_route(contact_id=OTHER_CONTACT_ID, whatsapp=FIRST_CONTACT_PHONE)
        ),
    )

    resposta = _testar(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["rule_id"] == str(RULE_ID)
    assert corpo["contact_id"] == str(CONTACT_ID)
    assert corpo["queued"] == [{"channel": "whatsapp", "provider": "z_api"}]
    test_id = UUID(corpo["test_id"])

    # (1) quem clicou é achado pelo e-mail do token, como o usuário.
    [(statement, params)] = _statements(stubs.user, "from app.contact c\n where c.tenant_id")
    assert statement == canais_regras._CALLER_CONTACT_SQL
    assert "lower(c.email) = lower(%(email)s)" in statement
    assert params["email"] == CALLER_EMAIL
    assert "c.type = 'person'" in statement and "c.active" in statement
    # (2) a rota é decidida para ESSE contato.
    [(_, params)] = _statements(stubs.bound, "as telegram_ready")
    assert params["contact_id"] == str(CONTACT_ID)
    # (3) a linha da fila: a instrução do outbox, destino do chamador, a regra,
    # sem ciclo, o template, e a chave da casa com o sufixo do clique.
    [(statement, params)] = _statements(stubs.bound, "insert into app.alert_queue")
    assert statement == outbox._ENQUEUE_SQL
    assert params["destination"] == CALLER_PHONE
    assert params["destination"] != FIRST_CONTACT_PHONE
    assert params["rule_id"] == str(RULE_ID)
    assert params["cycle_id"] is None
    assert params["channel"] == "whatsapp" and params["provider"] == "z_api"
    assert params["template_code"] == "deviation_summary"
    prefixo, sufixo = params["idempotency_key"].rsplit(":test:", 1)
    assert sufixo == str(test_id)
    assert prefixo.startswith(f"{RULE_ID}:{date.today()}:{CONTACT_ID}:whatsapp:")
    assert len(prefixo.rsplit(":", 1)[1]) == 16
    # (4) o payload é `outbox.facts` — as chaves que um template pode declarar —
    # e a declaração diz que é teste.
    import json

    payload = json.loads(params["payload"])
    assert set(payload) == set(
        outbox.facts(
            Cycle(RULE_ID, UNIT_ID, "x", date.today(), date.today(), 0, 0, 0), base_url="http://x"
        )
    )
    assert payload["unit"] == "Unidade Centro"
    assert payload["total_events"] == "3" and payload["deviation_minutes"] == "47"
    assert "Mensagem de teste da regra «Resumo diário»" in payload["declaration"]
    assert payload["link"].startswith("http://localhost:3000/dashboard?un=")
    # (5) a trilha leva o test_id e o contato — nunca o destino.
    [audit] = _audits(stubs)
    assert audit["entity"] == "alert_queue" and audit["entity_id"] == str(QUEUE_ID)
    assert audit["depois"].obj["test_id"] == str(test_id)
    assert CALLER_PHONE not in _all_text(audit)
    assert stubs.bound_ctx.exited_with is None


def test_a_chave_do_teste_e_a_do_outbox_com_o_sufixo() -> None:
    cycle = Cycle(RULE_ID, UNIT_ID, "x", date(2026, 9, 15), date(2026, 9, 21), 1, 2, 0)
    payload = {"unit": "x"}
    test_id = UUID("88888888-8888-4888-8888-888888888888")
    esperada = outbox._key(RULE_ID, cycle, CONTACT_ID, "whatsapp", payload) + f":test:{test_id}"
    assert (
        canais_regras.key_for_test(RULE_ID, cycle, CONTACT_ID, "whatsapp", payload, test_id)
        == esperada
    )


def test_testar_vai_pelo_telegram_quando_o_chamador_aderiu_e_o_bot_esta_pronto(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """A mesma `outbox.route` da entrega real decide o canal."""
    stubs = db(route=caller_route(telegram_external_id="987654321", telegram_ready=True))

    resposta = _testar(client, cabecalho)

    assert resposta.json()["queued"] == [{"channel": "telegram", "provider": "telegram"}]
    [(_, params)] = _statements(stubs.bound, "insert into app.alert_queue")
    assert params["destination"] == "987654321"
    assert params["channel"] == "telegram"
    # O chat_id não volta na resposta nem vai à trilha.
    assert "987654321" not in resposta.text
    assert "987654321" not in _all_text(*_audits(stubs))


def test_testar_com_both_enfileira_as_duas_metades(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(rule=visible_rule(channel="both"))

    resposta = _testar(client, cabecalho)

    assert resposta.json()["queued"] == [
        {"channel": "whatsapp", "provider": "z_api"},
        {"channel": "email", "provider": "smtp"},
    ]
    linhas = _statements(stubs.bound, "insert into app.alert_queue")
    assert [p["destination"] for _, p in linhas] == [CALLER_PHONE, CALLER_EMAIL]
    assert len({p["idempotency_key"] for _, p in linhas}) == 2
    assert len(_audits(stubs)) == 2


@pytest.mark.parametrize(
    ("kwargs", "status_code", "code"),
    [
        ({"caller": None}, 409, "caller_has_no_contact"),
        ({"unit": None}, 409, "no_unit"),
        ({"route": caller_route(whatsapp=None)}, 409, "caller_unreachable"),
        ({"provider": None}, 409, "no_channel"),
        ({"template": None}, 409, "template_not_found"),
        (
            {"template": {"code": "deviation_summary", "variables": ["employee"]}},
            422,
            "template_mismatch",
        ),
        (
            {
                "enqueue": _TriggerRefusal(
                    "Template deviation_summary está draft e o provedor é meta_cloud."
                )
            },
            422,
            "queue_refused",
        ),
    ],
)
def test_testar_recusa_nomeado_e_nada_fica_na_fila(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    kwargs: dict[str, Any],
    status_code: int,
    code: str,
) -> None:
    stubs = db(**kwargs)

    resposta = _testar(client, cabecalho)

    assert resposta.status_code == status_code, resposta.text
    assert resposta.json()["code"] == code
    assert _audits(stubs) == []
    if stubs.bound_ctx.opened:
        assert stubs.bound_ctx.exited_with is canais_regras._RefusedError
    if code == "caller_has_no_contact":
        assert CALLER_EMAIL in resposta.json()["detail"]
    if code == "queue_refused":
        assert (
            resposta.json()["detail"]
            == "Template deviation_summary está draft e o provedor é meta_cloud."
        )
    if code == "template_mismatch":
        assert "employee" in resposta.json()["detail"]


def test_testar_nao_exige_a_regra_ligada(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """*"rodar primeiro com destino no próprio owner"* — o teste vem ANTES de ligar."""
    db(rule=visible_rule(active=False))
    assert _testar(client, cabecalho).status_code == 200


def test_os_fatos_do_teste_sao_lidos_e_nao_reservados() -> None:
    """Reservar seria tirar os desvios do relatório de verdade (`ciclo.py`)."""
    sql = canais_regras._TEST_FACTS_SQL
    assert sql.lstrip().startswith("select")
    assert "update" not in sql and "report_cycle_id" not in sql
    assert "d.mode = 'production'" in sql and "d.status = 'active'" in sql


def test_as_duas_entradas_de_route_sao_as_de_targets_sql_letra_por_letra() -> None:
    """`telegram_ready` e a identidade vigente em `_CALLER_ROUTE_SQL` são os
    blocos de `outbox._TARGETS_SQL`, sem reescrita — se lá mudar, aqui quebra."""

    def bloco(sql: str, inicio: str, fim: str) -> str:
        i = sql.index(inicio)
        j = sql.index(fim, i) + len(fim)
        return " ".join(sql[i:j].split())

    for inicio, fim in (
        ("exists (select 1 from app.integration i", ") as telegram_ready"),
        ("left join lateral (", "limit 1) mi on true"),
    ):
        assert bloco(canais_regras._CALLER_ROUTE_SQL, inicio, fim) == bloco(
            outbox._TARGETS_SQL, inicio, fim
        )


# ---------------------------------------------------------------------------
# blocked_reason — puro, sobre as duas leituras que já existem
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("rule", "readiness_map", "blocked_rows", "esperado"),
    [
        (rule_row(active=False, targets=[]), {}, [], None),
        (rule_row(active=True, targets=[]), {"whatsapp": readiness()}, [], "Nenhum destino ativo"),
        (
            rule_row(active=True, targets=[target(contact_active=False)]),
            {"whatsapp": readiness()},
            [],
            "Nenhum destino ativo",
        ),
        (
            rule_row(
                active=True,
                targets=[
                    target(
                        contact_id=None, contact_name=None, contact_active=None, responsibility="hr"
                    )
                ],
            ),
            {"whatsapp": readiness()},
            [],
            None,
        ),
        (rule_row(active=True, template_code=None), {"whatsapp": readiness()}, [], "Sem template"),
        (
            rule_row(active=True),
            {"whatsapp": readiness()},
            [blocked(status=None)],
            "não existe ou está inativo",
        ),
        (
            rule_row(active=True),
            {"whatsapp": readiness("meta_cloud")},
            [blocked(status="pending")],
            "está «pending» na Meta",
        ),
        (
            rule_row(active=True),
            {"whatsapp": readiness("z_api")},
            [blocked(status="pending")],
            None,
        ),
        (rule_row(active=True), {}, [], "Nenhum canal de mensageria"),
        (rule_row(active=True), {"telegram": bot(ready=True)}, [], None),
        (rule_row(active=True), {"telegram": bot(ready=False)}, [], "Nenhum canal de mensageria"),
        (
            rule_row(active=True, channel="email", template_code=None),
            {},
            [],
            "e-mail ainda não tem provedor",
        ),
        (rule_row(active=True, channel="both"), {"whatsapp": readiness()}, [], None),
        # A lista casa por (nome, template): outra regra com o mesmo template não
        # contamina esta.
        (
            rule_row(active=True),
            {"whatsapp": readiness("meta_cloud")},
            [blocked(name="Outra", status="pending")],
            None,
        ),
    ],
)
def test_blocked_reason(
    rule: dict[str, Any],
    readiness_map: dict[str, Any],
    blocked_rows: list[dict[str, Any]],
    esperado: str | None,
) -> None:
    razao = canais_regras.blocked_reason(rule, readiness_map, blocked_rows)
    if esperado is None:
        assert razao is None
    else:
        assert razao is not None and esperado in razao


def test_blocked_reason_chega_na_lista_a_partir_das_duas_consultas(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    db(
        rules=[rule_row(active=True)],
        readiness_rows=[readiness("meta_cloud")],
        blocked_rows=[blocked(status="rejected")],
    )

    [regra] = client.get("/canais/regras", headers=cabecalho).json()

    assert "rejected" in regra["blocked_reason"]


# ---------------------------------------------------------------------------
# Toda consulta de escrita carrega o tenant; a resposta não carrega segredo
# ---------------------------------------------------------------------------
def test_toda_instrucao_do_modulo_liga_o_tenant_menos_o_catalogo_global() -> None:
    """`tenant_scope` recusaria o que não liga `%(tenant_id)s`; o catálogo de
    tipos de desvio é global e roda como o usuário — é a única exceção."""
    for name, sql in vars(canais_regras).items():
        if not name.endswith("_SQL"):
            continue
        if name == "_DEVIATION_TYPE_SQL":
            assert "tenant_id" not in sql
            continue
        assert "%(tenant_id)s" in sql, name
        assert re.search(r"\btenant_id\b", sql.replace("%(tenant_id)s", "")), name


# ---------------------------------------------------------------------------
# O navegador chega ao PUT: o preflight de CORS aceita o método
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method", ["PUT", "POST", "GET", "PATCH", "DELETE"])
def test_o_preflight_de_cors_aceita_o_put_das_rotas_de_escrita(
    client: TestClient, method: str
) -> None:
    """O painel chama a API de outra origem, e o navegador pergunta antes de
    cada `PUT`. Medido antes do C6: `PUT` não estava em `allow_methods`, o
    Starlette respondia 400 «Disallowed CORS method», e o `PUT` de templates e
    o de configuração do assistente eram inalcançáveis pelo painel com toda a
    suíte verde. As quatro rotas `PUT` desta sprint dependem disto."""
    resposta = client.options(
        f"/canais/regras/{RULE_ID}",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert resposta.status_code == 200, resposta.text
    assert method in resposta.headers["access-control-allow-methods"]
    assert resposta.headers["access-control-allow-origin"] == "http://localhost:3000"
