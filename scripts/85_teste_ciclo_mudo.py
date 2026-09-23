#!/usr/bin/env python3
"""Prova o ciclo mudo (C7) contra o banco: uma transação só, e o que ela desfaz.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/85_teste_ciclo_mudo.py

POR QUE ESTE NÃO É MAIS UM SCRIPT DE SQL
Os outros testes desta pasta leem as instruções dos módulos e as rodam por
`psql`, porque rodam fora do venv. Aqui isso seria um falso verde: o que está
sob teste não é uma instrução, é a **fronteira da transação** e o **laço que
pula a regra doente** — os dois em Python. Um roteiro de `psql` que executasse
`_RESERVE_SQL` e `_ENQUEUE_SQL` na ordem certa passaria mesmo com o defeito de
pé. Então este roda o código de verdade, `alertas.__main__._por_tenant`, que é
o turno inteiro, e só olha para o estado do banco depois.

O defeito que ele prende, medido em 23/09/2026 antes do conserto:

    depois do assemble:  ciclos 1 · reservados 2 · livres 0 · fila 0
    enqueue levantou TemplateMismatchError
    depois do enqueue:   ciclos 1 · reservados 2 · livres 0 · fila 0
    segundo turno: assemble devolveu 0 ciclo(s)   ← os desvios não voltam nunca

Cinco cenários, e o que cada um existe para pegar:

1. **doente + saudável na mesma unidade** — a saudável entrega, a doente é
   nomeada, o ciclo fica de pé. Um conserto que pulasse o lote inteiro também
   passaria no cenário 2; este é o par que o separa.
2. **doente sozinha** — nenhuma mensagem, NENHUM ciclo, e os desvios livres.
3. **o turno seguinte** — os mesmos desvios voltam, e voltam com mensagem
   quando o template é consertado. É o que torna o conserto auto-curável, e é
   a asserção que o `_RESERVE_SQL` (`report_cycle_id is null`) não perdoa.
4. **transação única** — a falha que vem do BANCO (`meta_cloud` com template
   não aprovado, o gatilho `util.validate_alert_template`) não pode deixar
   nada commitado. Antes do C7 deixava: a reserva já tinha commitado sozinha.
5. **regra 6** — nenhum desvio é apagado em nenhum dos quatro. O que se apaga
   é o ciclo mudo, e o `on delete set null` do FK devolve o desvio.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date

DSN = os.environ.get("ENSAIO_DATABASE_URL")
if not DSN:
    print("  ✖ defina ENSAIO_DATABASE_URL com o DSN do banco de ensaio")
    raise SystemExit(1)

os.environ["DATABASE_URL"] = DSN
os.environ.setdefault("SUPABASE_URL", "https://project.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key-for-tests")
os.environ.setdefault(
    "SUPABASE_JWT_JWKS_URL", "https://project.supabase.co/auth/v1/.well-known/jwks.json"
)
os.environ.setdefault("ANTHROPIC_API_KEY", "anthropic-key-for-tests")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from operax.alertas import __main__ as turno  # noqa: E402
from operax.alertas import ciclo  # noqa: E402
from operax.core.db import get_pools  # noqa: E402
from operax.core.tenant import SystemContext, tenant_scope  # noqa: E402

TENANT = "c7000000-0000-0000-0000-000000000001"
COMPANY = "c7000000-0000-0000-0000-0000000000c1"
UNIT = "c7000000-0000-0000-0000-0000000000a1"
EMPLOYEE = "c7000000-0000-0000-0000-0000000000e1"
DOENTE = "c7000000-0000-0000-0000-0000000000d1"
SAUDAVEL = "c7000000-0000-0000-0000-0000000000d2"
GESTOR = "c7000000-0000-0000-0000-0000000000f1"
DP = "c7000000-0000-0000-0000-0000000000f2"
HOJE = date(2026, 9, 23)
UNIT2 = "c7000000-0000-0000-0000-0000000000a2"
VIZINHO = "c7000000-0000-0000-0000-000000000002"
VIZINHO_COMPANY = "c7000000-0000-0000-0000-0000000000c2"
VIZINHO_UNIT = "c7000000-0000-0000-0000-0000000000a3"
VIZINHO_EMPLOYEE = "c7000000-0000-0000-0000-0000000000e2"
CONTEXT = SystemContext(tenant_id=uuid.UUID(TENANT), task="85-teste-ciclo-mudo")

#: A ordem importa: fila antes de ciclo, ciclo antes de desvio.
_LIMPAR = f"""
delete from app.alert_queue where tenant_id = '{TENANT}';
delete from app.alert_rule_target where rule_id in
  (select id from app.alert_rule where tenant_id = '{TENANT}');
delete from app.alert_rule where tenant_id = '{TENANT}';
delete from app.contact where tenant_id = '{TENANT}';
delete from app.deviation_event where tenant_id = '{TENANT}';
delete from app.report_cycle where tenant_id = '{TENANT}';
delete from app.employee where tenant_id = '{TENANT}';
delete from app.unit where tenant_id = '{TENANT}';
delete from app.company where tenant_id = '{TENANT}';
delete from app.integration where tenant_id = '{TENANT}';
delete from app.message_template where tenant_id = '{TENANT}';
delete from app.tenant where id = '{TENANT}';
"""

_CADASTRO = f"""
insert into app.tenant (id, slug, name) values ('{TENANT}', 'c7-ciclo-mudo', 'C7');
insert into app.company (id, tenant_id, legal_name) values ('{COMPANY}', '{TENANT}', 'C7 LTDA');
insert into app.unit (id, tenant_id, company_id, code, name)
  values ('{UNIT}', '{TENANT}', '{COMPANY}', 'C7-1', 'Unidade Alfa');
insert into app.employee (id, tenant_id, company_id, unit_id, name)
  values ('{EMPLOYEE}', '{TENANT}', '{COMPANY}', '{UNIT}', 'Colaborador C7');
insert into app.contact (id, tenant_id, name, type, whatsapp, email) values
  ('{GESTOR}', '{TENANT}', 'Gestor', 'person', '+5511999990001', 'gestor@c7.test'),
  ('{DP}', '{TENANT}', 'DP', 'person', null, 'dp@c7.test');
"""

_LIMPAR_VIZINHO = f"""
delete from app.alert_queue where tenant_id = '{VIZINHO}';
delete from app.deviation_event where tenant_id = '{VIZINHO}';
delete from app.report_cycle where tenant_id = '{VIZINHO}';
delete from app.employee where tenant_id = '{VIZINHO}';
delete from app.unit where tenant_id = '{VIZINHO}';
delete from app.company where tenant_id = '{VIZINHO}';
delete from app.tenant where id = '{VIZINHO}';
"""

#: O segundo cliente existe para uma pergunta só: o turno deste alcança o ciclo
#: daquele? `bind_tenant` não responde — a subconsulta do `delete` cita
#: `tenant_id` e isso lhe basta, mesmo que o `delete` não filtre.
_CADASTRO_VIZINHO = f"""
insert into app.tenant (id, slug, name) values ('{VIZINHO}', 'c7-vizinho', 'C7 Vizinho');
insert into app.company (id, tenant_id, legal_name)
  values ('{VIZINHO_COMPANY}', '{VIZINHO}', 'Empresa Vizinha LTDA');
insert into app.unit (id, tenant_id, company_id, code, name)
  values ('{VIZINHO_UNIT}', '{VIZINHO}', '{VIZINHO_COMPANY}', 'C7-V1', 'Unidade Vizinha');
insert into app.employee (id, tenant_id, company_id, unit_id, name)
  values ('{VIZINHO_EMPLOYEE}', '{VIZINHO}', '{VIZINHO_COMPANY}', '{VIZINHO_UNIT}', 'Colaborador Vizinho');
"""

_ESTADO = f"""
select
  (select count(*) from app.report_cycle where tenant_id = '{TENANT}') as ciclos,
  (select count(*) from app.deviation_event where tenant_id = '{TENANT}') as desvios,
  (select count(*) from app.deviation_event
     where tenant_id = '{TENANT}' and report_cycle_id is null) as livres,
  (select count(*) from app.alert_queue where tenant_id = '{TENANT}') as fila
"""

falhas: list[str] = []


def sql(texto: str, *, uma: bool = False):
    with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as conexao:
        with conexao.cursor() as cur:
            cur.execute(texto)
            if not cur.description:
                return []
            linhas = cur.fetchall()
            return linhas[0] if uma else linhas


def igual(rotulo: str, obtido: object, esperado: object) -> None:
    if obtido != esperado:
        falhas.append(f"{rotulo}: esperado {esperado!r}, obtido {obtido!r}")
        print(f"  ✖ {rotulo}: esperado {esperado!r}, obtido {obtido!r}")
    else:
        print(f"  ok  {rotulo} ({obtido!r})")


def contem(rotulo: str, texto: str, trecho: str) -> None:
    igual(rotulo, trecho in texto, True)


def desvios(quantos: int) -> None:
    """`quantos` desvios livres de produção, e mais nada reservado."""
    linhas = ",\n".join(
        f"('{TENANT}', '{EMPLOYEE}', '{COMPANY}', '{UNIT}', '{HOJE}', "
        f"'{tipo}', {minutos}, 'production', 'active')"
        for tipo, minutos in [("late_entry", -20), ("late_exit", 27), ("early_exit", -14)][:quantos]
    )
    sql(
        "insert into app.deviation_event (tenant_id, employee_id, company_id, unit_id, "
        f"reference_date, type, minutes, mode, status) values\n{linhas}"
    )


def regra(rule_id: str, nome: str, canal: str, template: str | None, contato: str) -> None:
    codigo = "null" if template is None else f"'{template}'"
    sql(
        f"insert into app.alert_rule (id, tenant_id, name, content, channel, template_code, "
        f"active) values ('{rule_id}', '{TENANT}', '{nome}', 'aggregate', '{canal}', "
        f"{codigo}, true);"
        f"insert into app.alert_rule_target (rule_id, contact_id) values "
        f"('{rule_id}', '{contato}');"
    )


async def rodar() -> list[str]:
    """O turno inteiro, como o cron o roda. Levantar é resposta possível."""
    await get_pools().open()
    return await turno._por_tenant(CONTEXT, HOJE, "http://localhost:3000")


def turno_ok() -> str:
    return "\n".join(asyncio.run(rodar()))


async def _desfazer(onde: str = TENANT) -> list[str]:
    """`ciclo.drop_silent` sobre os ciclos vivos de `onde`, SEMPRE no escopo do
    tenant deste teste — o código, nunca uma cópia do predicado.

    `onde` existe para a única pergunta que o `cycle_id` não responde sozinho:
    e se alguém passar a este turno um ciclo que não é dele? Hoje os ciclos vêm
    do `assemble` do próprio tenant, então o `rc.tenant_id` do `delete` é defesa
    em profundidade — e defesa que ninguém exercita é defesa que se apaga sem
    ninguém ver."""
    await get_pools().open()
    linhas = sql(
        f"select id, unit_id, period_start, period_end, total_events "
        f"from app.report_cycle where tenant_id = '{onde}'"
    )
    vivos = [
        ciclo.Cycle(
            cycle_id=linha["id"],
            unit_id=linha["unit_id"],
            unit_name="",
            period_start=linha["period_start"],
            period_end=linha["period_end"],
            total_events=linha["total_events"],
            deviation_minutes=0,
            from_previous_days=0,
        )
        for linha in linhas
    ]
    async with tenant_scope(CONTEXT) as escopo:
        return [str(c.cycle_id) for c in await ciclo.drop_silent(escopo, vivos)]


def desfazer(onde: str = TENANT) -> list[str]:
    return asyncio.run(_desfazer(onde))


def turno_levanta() -> str:
    try:
        asyncio.run(rodar())
    except Exception as exc:  # noqa: BLE001 — é o que está sob teste
        return f"{type(exc).__name__}: {exc}"
    return "(não levantou)"


# ---------------------------------------------------------------------------
# 1. Doente e saudável na mesma unidade: a saudável entrega, a doente é nomeada
# ---------------------------------------------------------------------------
print("\n--- 1. regra doente + regra saudável na mesma unidade")
sql(_LIMPAR)
sql(_CADASTRO)
sql(
    f"insert into app.integration (tenant_id, provider, alias, config, active) "
    f"values ('{TENANT}', 'z_api', 'z_api', '{{\"instance_id\": \"X\"}}', true)"
)
desvios(2)
regra(DOENTE, "Doente (template inexistente)", "whatsapp", "nao_existe", GESTOR)
regra(SAUDAVEL, "Saudavel (e-mail)", "email", None, DP)
igual("antes: dois desvios livres, nada na fila", sql(_ESTADO, uma=True)["livres"], 2)

relato = turno_ok()
estado = sql(_ESTADO, uma=True)
igual("a saudável enfileirou uma mensagem", estado["fila"], 1)
igual("o ciclo com mensagem fica de pé", estado["ciclos"], 1)
igual("os desvios foram consumidos", estado["livres"], 0)
igual("e nenhum desvio foi apagado (regra 6)", estado["desvios"], 2)
contem("o relatório nomeia a regra doente", relato, "Doente (template inexistente)")
contem("e diz por quê", relato, "não existe ou está inativo")
igual(
    "a única linha da fila é a de e-mail",
    [(linha["channel"], linha["template_code"]) for linha in sql(
        f"select channel, template_code from app.alert_queue where tenant_id = '{TENANT}'"
    )],
    [("email", None)],
)

# ---------------------------------------------------------------------------
# 2. A doente sozinha: nenhuma mensagem, nenhum ciclo, desvios livres
# ---------------------------------------------------------------------------
print("\n--- 2. a regra doente sozinha: nada na fila, e NENHUM ciclo")
sql(f"delete from app.alert_rule_target where rule_id = '{SAUDAVEL}'")
sql(f"delete from app.alert_rule where id = '{SAUDAVEL}'")
sql(f"delete from app.alert_queue where tenant_id = '{TENANT}'")
sql(f"delete from app.report_cycle where tenant_id = '{TENANT}'")
igual("os dois desvios voltaram a livres", sql(_ESTADO, uma=True)["livres"], 2)

relato = turno_ok()
estado = sql(_ESTADO, uma=True)
igual("nenhuma mensagem", estado["fila"], 0)
igual("NENHUM ciclo — o mudo foi desfeito", estado["ciclos"], 0)
igual("e os desvios continuam livres", estado["livres"], 2)
igual("nenhum desvio apagado (regra 6)", estado["desvios"], 2)
contem("o relatório diz que o ciclo foi desfeito", relato, "desfeito: nenhuma mensagem")
contem("e nomeia a regra que ficou de fora", relato, "Doente (template inexistente)")

# ---------------------------------------------------------------------------
# 3. O turno seguinte: voltam, e entregam quando o template é consertado
# ---------------------------------------------------------------------------
print("\n--- 3. o turno seguinte: os mesmos desvios voltam, e agora entregam")
relato = turno_ok()
estado = sql(_ESTADO, uma=True)
igual("a doente sozinha de novo: seguem livres", estado["livres"], 2)
igual("e seguem sem ciclo", estado["ciclos"], 0)

sql(
    f"insert into app.message_template (tenant_id, code, body, variables, active) "
    f"values ('{TENANT}', 'nao_existe', 'Unidade {{{{1}}}}: veja em {{{{2}}}}', "
    f"array['unit','link'], true)"
)
relato = turno_ok()
estado = sql(_ESTADO, uma=True)
igual("template consertado: a mensagem sai", estado["fila"], 1)
igual("o ciclo fica de pé", estado["ciclos"], 1)
igual("e os desvios são consumidos", estado["livres"], 0)
igual("sem nenhum desvio apagado (regra 6)", estado["desvios"], 2)
igual("ninguém ficou de fora", "ficou de fora" in relato, False)

# ---------------------------------------------------------------------------
# 4. A transação única: a recusa do BANCO não pode deixar nada commitado
# ---------------------------------------------------------------------------
print("\n--- 4. transação única: uma recusa do BANCO não deixa NADA commitado")
# ⛔ A recusa aqui é um gatilho que o código NÃO conhece, e é de propósito.
# Os três motivos de `util.validate_alert_template` o `enqueue` pergunta antes,
# justamente para poder pular em vez de estourar (é o que os cenários 1 a 3
# medem). O que sobra — e sempre vai sobrar — é a recusa imprevista: um gatilho
# novo, uma constraint nova, o banco caindo no meio. Prender o cenário a um
# motivo específico faria este teste apodrecer no dia em que alguém o passasse
# a prever; prendê-lo à classe não.
#
# A recusa cai sobre a SEGUNDA unidade: a mensagem da primeira já entrou quando
# ela acontece. Se a transação não fosse uma só, o ciclo da Alfa e a reserva
# dela ficariam de pé.
sql(_LIMPAR)
sql(_CADASTRO)
sql(
    f"insert into app.unit (id, tenant_id, company_id, code, name) "
    f"values ('{UNIT2}', '{TENANT}', '{COMPANY}', 'C7-2', 'Unidade Beta')"
)
sql(
    f"insert into app.integration (tenant_id, provider, alias, config, active) "
    f"values ('{TENANT}', 'z_api', 'z_api', '{{\"instance_id\": \"X\"}}', true)"
)
desvios(2)
sql(
    f"insert into app.deviation_event (tenant_id, employee_id, company_id, unit_id, "
    f"reference_date, type, minutes, mode, status) values "
    f"('{TENANT}', '{EMPLOYEE}', '{COMPANY}', '{UNIT2}', '{HOJE}', 'early_exit', -31, "
    f"'production', 'active')"
)
regra(SAUDAVEL, "Saudavel, as duas unidades", "email", None, DP)
sql(
    """
create or replace function pg_temp_recusa() returns trigger
language plpgsql as $$
begin
  if new.payload ->> 'unit' = 'Unidade Beta' then
    raise exception using errcode = 'raise_exception',
      message = 'recusa imprevista do banco (gatilho de teste)';
  end if;
  return new;
end $$;
drop trigger if exists trg_recusa_de_teste on app.alert_queue;
create trigger trg_recusa_de_teste before insert on app.alert_queue
  for each row execute function pg_temp_recusa();
"""
)
igual("antes: três desvios livres", sql(_ESTADO, uma=True)["livres"], 3)

erro = turno_levanta()
estado = sql(_ESTADO, uma=True)
sql("drop trigger if exists trg_recusa_de_teste on app.alert_queue; drop function if exists pg_temp_recusa()")
contem("o turno morre alto, com a recusa do banco", erro, "recusa imprevista")
igual("nenhum ciclo commitado — nem o da unidade que já tinha enfileirado", estado["ciclos"], 0)
igual("nenhuma linha na fila", estado["fila"], 0)
igual("TODOS os desvios continuam livres", estado["livres"], 3)
igual("e nenhum foi apagado (regra 6)", estado["desvios"], 3)

# ---------------------------------------------------------------------------
# 5. O ciclo que TEM mensagem nunca é apagado
# ---------------------------------------------------------------------------
# Começa do zero: o cenário 4 deixou a transação desfeita, e depender do que
# sobrou de outro cenário é como um teste passa a falhar quando o vizinho muda.
print("\n--- 5. o ciclo com mensagem sobrevive a um `drop_silent` de novo")
sql(_LIMPAR)
sql(_CADASTRO)
desvios(2)
regra(SAUDAVEL, "Saudavel (e-mail)", "email", None, DP)
turno_ok()
estado = sql(_ESTADO, uma=True)
igual("um ciclo, uma mensagem", (estado["ciclos"], estado["fila"]), (1, 1))
# ⛔ Chamando `ciclo.drop_silent`, não uma cópia do predicado: recopiar o SQL
# aqui é o falso verde contra o qual este arquivo inteiro argumenta — mutar
# `_DROP_SILENT_SQL` deixaria o cenário verde.
igual("o drop_silent não alcança o ciclo com mensagem", desfazer(), [])
estado = sql(_ESTADO, uma=True)
igual("o ciclo com mensagem continua lá", estado["ciclos"], 1)
igual("e os desvios continuam nele", estado["livres"], 0)

# ---------------------------------------------------------------------------
# 6. Duas unidades no mesmo turno: uma entrega, a outra é desfeita
# ---------------------------------------------------------------------------
print("\n--- 6. duas unidades no mesmo turno: só a muda é desfeita")
sql(_LIMPAR)
sql(_CADASTRO)
sql(
    f"insert into app.unit (id, tenant_id, company_id, code, name) "
    f"values ('{UNIT2}', '{TENANT}', '{COMPANY}', 'C7-2', 'Unidade Beta')"
)
sql(
    f"insert into app.integration (tenant_id, provider, alias, config, active) "
    f"values ('{TENANT}', 'z_api', 'z_api', '{{\"instance_id\": \"X\"}}', true)"
)
desvios(2)
sql(
    f"insert into app.deviation_event (tenant_id, employee_id, company_id, unit_id, "
    f"reference_date, type, minutes, mode, status) values "
    f"('{TENANT}', '{EMPLOYEE}', '{COMPANY}', '{UNIT2}', '{HOJE}', 'early_exit', -31, "
    f"'production', 'active')"
)
# A saudável é da Alfa; a Beta só tem a doente. O turno monta os dois ciclos.
regra(SAUDAVEL, "Saudavel da Alfa", "email", None, DP)
sql(f"update app.alert_rule set scope_unit_id = '{UNIT}' where id = '{SAUDAVEL}'")
regra(DOENTE, "Doente da Beta", "whatsapp", "nao_existe", GESTOR)
sql(f"update app.alert_rule set scope_unit_id = '{UNIT2}' where id = '{DOENTE}'")

turno_ok()
ciclos = sql(
    f"select u.name, c.total_events, "
    f"(select count(*) from app.alert_queue q where q.report_cycle_id = c.id) as msgs "
    f"from app.report_cycle c join app.unit u on u.id = c.unit_id "
    f"where c.tenant_id = '{TENANT}' order by u.name"
)
igual("sobrou UM ciclo, o da unidade que entregou", [(c["name"], c["msgs"]) for c in ciclos], [("Unidade Alfa", 1)])
igual("o desvio da Beta voltou a livre", sql(_ESTADO, uma=True)["livres"], 1)
igual("e nenhum desvio foi apagado (regra 6)", sql(_ESTADO, uma=True)["desvios"], 3)

# ---------------------------------------------------------------------------
# 7. A fila do tenant CHEIA: o mudo ainda é desfeito
# ---------------------------------------------------------------------------
# Em produção a fila nunca está vazia — o `sender` faz `update`, nunca `delete`.
# Um predicado sem a correlação `q.report_cycle_id = rc.id` passaria nos
# cenários de fila vazia e pararia de funcionar no primeiro dia real.
print("\n--- 7. com a fila do tenant cheia, o ciclo mudo ainda é desfeito")
sql(_LIMPAR)
sql(_CADASTRO)
sql(
    f"insert into app.integration (tenant_id, provider, alias, config, active) "
    f"values ('{TENANT}', 'z_api', 'z_api', '{{\"instance_id\": \"X\"}}', true)"
)
desvios(2)
regra(DOENTE, "Doente (template inexistente)", "whatsapp", "nao_existe", GESTOR)
# Uma mensagem velha, de outro ciclo, já entregue: a fila NÃO está vazia.
velho = sql(
    f"insert into app.report_cycle (tenant_id, unit_id, period_start, period_end, status, "
    f"total_events) values ('{TENANT}', '{UNIT}', '{HOJE}', '{HOJE}', 'sent', 1) returning id"
)[0]["id"]
sql(
    f"insert into app.alert_queue (tenant_id, rule_id, report_cycle_id, channel, provider, "
    f"destination, payload, idempotency_key, template_code, status) values "
    f"('{TENANT}', '{DOENTE}', '{velho}', 'email', 'smtp', 'dp@c7.test', '{{}}'::jsonb, "
    f"'velha-85', null, 'sent')"
)
turno_ok()
igual("a mensagem velha continua na fila", sql(_ESTADO, uma=True)["fila"], 1)
igual("o ciclo novo (mudo) foi desfeito; só o velho ficou", sql(_ESTADO, uma=True)["ciclos"], 1)
igual("e os dois desvios voltaram a livres", sql(_ESTADO, uma=True)["livres"], 2)

# ---------------------------------------------------------------------------
# 8. O turno de um tenant não alcança o ciclo mudo do outro
# ---------------------------------------------------------------------------
# `bind_tenant` NÃO pega a falta do filtro no `delete`: a subconsulta cita
# `tenant_id` e isso basta para o estrangulamento. Quem pega é este cenário.
print("\n--- 8. o turno de um tenant não desfaz o ciclo mudo do outro")
sql(_LIMPAR)
sql(_LIMPAR_VIZINHO)
sql(_CADASTRO)
sql(_CADASTRO_VIZINHO)
desvios(2)
sql(
    f"insert into app.deviation_event (tenant_id, employee_id, company_id, unit_id, "
    f"reference_date, type, minutes, mode, status) values "
    f"('{VIZINHO}', '{VIZINHO_EMPLOYEE}', '{VIZINHO_COMPANY}', '{VIZINHO_UNIT}', '{HOJE}', "
    f"'late_entry', -18, 'production', 'active')"
)
# O vizinho tem um ciclo MUDO de véspera — o alvo mais apetitoso possível.
mudo_alheio = sql(
    f"insert into app.report_cycle (tenant_id, unit_id, period_start, period_end, status, "
    f"total_events) values ('{VIZINHO}', '{VIZINHO_UNIT}', '{HOJE}', '{HOJE}', 'open', 1) "
    f"returning id"
)[0]["id"]
sql(
    f"update app.deviation_event set report_cycle_id = '{mudo_alheio}' "
    f"where tenant_id = '{VIZINHO}'"
)
regra(DOENTE, "Doente (template inexistente)", "whatsapp", "nao_existe", GESTOR)

turno_ok()  # o turno do TENANT, não o do vizinho
igual(
    "o ciclo mudo do vizinho continua de pé",
    sql(f"select count(*) as n from app.report_cycle where tenant_id = '{VIZINHO}'", uma=True)["n"],
    1,
)
igual(
    "e o desvio dele continua reservado nele",
    sql(
        f"select count(*) as n from app.deviation_event where tenant_id = '{VIZINHO}' "
        f"and report_cycle_id = '{mudo_alheio}'",
        uma=True,
    )["n"],
    1,
)
igual("o ciclo mudo do próprio tenant foi desfeito", sql(_ESTADO, uma=True)["ciclos"], 0)

# E o filtro de tenant do `delete`, exercitado de frente: entregamos ao
# `drop_silent` deste tenant o ciclo MUDO do vizinho. O `cycle_id` sozinho o
# apagaria; o `rc.tenant_id` é o que não deixa.
igual("o drop_silent deste tenant não apaga ciclo do vizinho nem quando recebe o id dele", desfazer(VIZINHO), [])
igual(
    "e o ciclo do vizinho continua lá",
    sql(f"select count(*) as n from app.report_cycle where tenant_id = '{VIZINHO}'", uma=True)["n"],
    1,
)

sql(_LIMPAR)
sql(_LIMPAR_VIZINHO)

print()
if falhas:
    print(f"  ✖ {len(falhas)} FALHA(S)")
    sys.exit(1)
print("================================================")
print(" CICLO MUDO (C7): TODOS OS TESTES OK")
print("================================================")
