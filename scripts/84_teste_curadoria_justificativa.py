#!/usr/bin/env python3
"""O gate do S6 contra o banco: a curadoria que destrava a apuração — e só ela.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/84_teste_curadoria_justificativa.py

⛔ POR QUE ESTE NÃO É UM ROTEIRO DE `psql`
O que está sob teste é um acordo entre DUAS peças de Python e um `check` do
banco: a porta canonicaliza a chave com `ciclo.canonical_justification`, o banco
a exige em `upper(btrim(...))`, e o apurador procura por ela. Um roteiro de SQL
que inserisse na `app.leave_justification_map` na mão provaria o `check` e
mentiria sobre o acordo — ele passaria verde com a porta gravando `Atested`
enquanto o apurador procura `ATESTED`, que é justamente o defeito que o
cabeçalho da migration `dp_absence_map` diz ser o pior possível. Então este
roda o código de verdade: `dp/justificativas.py` escreve e `dp/ciclo.py` apura.

E é aqui que o gate vive porque `scripts/` não tinha onde ele coubesse: o
`93_teste_ciclo.py` é do ciclo de RELATÓRIO (alertas), o `85` é do ciclo mudo e
o `87` é do painel de DP, em SQL puro. Nenhum apura cesta nem vale transporte.

O cenário é o de produção, medido em 23/09/2026: 64 afastamentos e cinco
justificativas distintas — `Férias` 43, `Atested` 13, `ATEST M` 5, `AFASTAD` 2,
`FALTA` 1 —, quatro delas truncadas pela origem. A competência é a cesta de
09/2026, cuja janela é o mês civil e cujas faltas são contadas em **agosto**.

Sete cenários:

1. **Sem curadoria** a apuração recusa e NOMEIA a string; validar o que ninguém
   classificou é recusa nomeada.
2. **Classificadas e não validadas** — a apuração CONTINUA recusando, agora
   dizendo que ninguém validou. É a metade do gate que um clique único apagaria.
3. **Validadas** — a apuração roda, e quem tem `FALTA` em agosto perde a cesta
   enquanto quem tem `FÉRIAS` fica com ela. Sem este par, "deixou de recusar"
   seria satisfeito por uma apuração que não olha para a curadoria.
4. **Reclassificar derruba o aval** — e reclassificar é `update`: a linha
   continua uma só, e a trilha guarda as duas passagens.
5. **A classificação move dinheiro** — `FALTA` como `vacation` devolve a cesta a
   quem faltou. É o que torna o cenário 3 uma afirmação e não um acaso.
6. **Nada é apagado** — nem pela porta, nem por `service_role`, que não tem
   `delete` nesta tabela.
7. **O afastamento sem nome** trava a apuração e não é curável: ele sai da fila
   e volta contado, senão a tela diria "tudo curado" com a competência parada.
"""

from __future__ import annotations

import asyncio
import os
import re
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

from operax.core.db import get_pools  # noqa: E402
from operax.core.tenant import TenantContext, UserRole  # noqa: E402
from operax.dp import ciclo, justificativas  # noqa: E402

TENANT = "56000000-0000-0000-0000-000000000001"
#: O vizinho existe para UMA pergunta: a escrita atravessa o tenant? A leitura
#: já era medida; a escrita não era, e o mutante que tirava o filtro do `update`
#: sobrevivia ao pytest E à suíte (achado da revisão do S6).
VIZINHO = "56000000-0000-0000-0000-000000000002"
VIZINHO_USER = "56000000-0000-0000-0000-0000000000f2"
USER = "56000000-0000-0000-0000-0000000000f1"
COMPANY = "56000000-0000-0000-0000-0000000000c1"
UNIT = "56000000-0000-0000-0000-0000000000a1"

#: A cesta de 09/2026: janela 01/09 a 30/09, faltas contadas em AGOSTO.
ANO, MES = 2026, 9

#: As cinco como a ORIGEM as escreve. Quatro são truncadas em 7 caracteres pelo
#: Secullum, e isso não se conserta aqui: é a chave que a origem oferece.
CINCO = {
    "Férias": ("vacation", 43, "Bea Ferias"),
    "Atested": ("leave_period", 13, "Caio Atestado"),
    "ATEST M": ("leave_period", 5, "Dora Atestado"),
    "AFASTAD": ("leave_of_absence", 2, "Edu Afastado"),
    "FALTA": ("unjustified_absence", 1, "Ana Faltou"),
}

CONTEXTO = TenantContext(tenant_id=uuid.UUID(TENANT), user_id=uuid.UUID(USER), role=UserRole.OWNER)

_LIMPAR = f"""
delete from app.audit_log where tenant_id = '{TENANT}';
delete from app.leave_justification_map where tenant_id = '{TENANT}';
delete from secullum."FuncionarioAfastamento" where tenant_id = '{TENANT}';
delete from secullum."Funcionario" where tenant_id = '{TENANT}';
delete from secullum."Departamento" where tenant_id = '{TENANT}';
delete from secullum."Empresa" where tenant_id = '{TENANT}';
delete from app.employee where tenant_id = '{TENANT}';
delete from app.unit where tenant_id = '{TENANT}';
delete from app.company where tenant_id = '{TENANT}';
delete from app.tenant where id = '{TENANT}';
delete from app.audit_log where tenant_id = '{VIZINHO}';
delete from app.leave_justification_map where tenant_id = '{VIZINHO}';
delete from app.tenant where id = '{VIZINHO}';
-- Os dois usuários por último: `validated_by` os referencia, e uma escrita que
-- tivesse atravessado o tenant deixaria a linha de um apontando para o outro.
delete from auth.users where id in ('{USER}', '{VIZINHO_USER}');
"""

_CADASTRO = f"""
insert into auth.users (id, email) values ('{USER}', 'dp.s6@teste');
insert into app.tenant (id, slug, name) values ('{TENANT}', 's6-curadoria', 'S6');
insert into app.company (id, tenant_id, legal_name)
  values ('{COMPANY}', '{TENANT}', 'S6 LTDA');
insert into app.unit (id, tenant_id, company_id, code, name)
  values ('{UNIT}', '{TENANT}', '{COMPANY}', 'S6-1', 'Pátio Centro');
insert into secullum."Empresa" (id, "EmpresaId", "Documento", "Nome", "Desativada", tenant_id)
  values ('56000000-0000-0000-0000-0000000000e1', 5601, '11.222.333/0001-81', 'S6 LTDA',
          false, '{TENANT}');
insert into secullum."Departamento" (id, "DepartamentoId", empresa_id, "Descricao", tenant_id)
  values ('56000000-0000-0000-0000-0000000000d1', 5611,
          '56000000-0000-0000-0000-0000000000e1', 'Pátio Centro', '{TENANT}');
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
    if trecho not in texto:
        falhas.append(f"{rotulo}: {trecho!r} não está em {texto!r}")
        print(f"  ✖ {rotulo}: {trecho!r} não está em {texto!r}")
    else:
        print(f"  ok  {rotulo}")


def semear_pessoas_e_afastamentos() -> None:
    """As cinco justificativas, com as 64 ocorrências de produção.

    Cada pessoa carrega uma justificativa só, e cada uma tem pelo menos uma
    ocorrência em AGOSTO/2026 — o mês contado pela cesta de setembro. As demais
    ocorrências ficam fora da janela de propósito: a fila da curadoria conta a
    história inteira do espelho, e a apuração só olha o mês.
    """
    for indice, (justificativa, (_, ocorrencias, nome)) in enumerate(CINCO.items(), start=1):
        funcionario = f"56000000-0000-0000-0000-00000000f{indice:03d}"
        colaborador = f"56000000-0000-0000-0000-00000000e{indice:03d}"
        secullum_id = 5700 + indice
        sql(
            f"""
            insert into secullum."Funcionario"
              (id, "FuncionarioId", "Nome", "Admissao", empresa_id, departamento_id, tenant_id)
            values ('{funcionario}', {secullum_id}, '{nome}', '2020-01-01',
                    '56000000-0000-0000-0000-0000000000e1',
                    '56000000-0000-0000-0000-0000000000d1', '{TENANT}');
            insert into app.employee
              (id, tenant_id, company_id, unit_id, name, registration_number,
               secullum_employee_id, hired_on)
            values ('{colaborador}', '{TENANT}', '{COMPANY}', '{UNIT}', '{nome}',
                    '{secullum_id}', {secullum_id}, '2020-01-01');
            -- A ocorrência de agosto: a que a competência de setembro conta.
            insert into secullum."FuncionarioAfastamento"
              (funcionario_id, "AfastamentoId", "Inicio", "Fim", "JustificativaNome", tenant_id)
            values ('{funcionario}', 1, '2026-08-0{indice}', '2026-08-0{indice}',
                    '{justificativa}', '{TENANT}');
            -- O resto da história, fora da janela contada.
            insert into secullum."FuncionarioAfastamento"
              (funcionario_id, "AfastamentoId", "Inicio", "Fim", "JustificativaNome", tenant_id)
            select '{funcionario}', n + 2,
                   date '2024-07-01' + (n * 7), date '2024-07-02' + (n * 7),
                   '{justificativa}', '{TENANT}'
              from generate_series(0, {ocorrencias - 2}) as n;
            """
        )


def fila() -> justificativas.Queue:
    async def _ler() -> justificativas.Queue:
        await get_pools().open()
        return await justificativas.read_queue(CONTEXTO)

    return asyncio.run(_ler())


def classificar(justificativa: str, categoria: str) -> justificativas.Justification:
    async def _classificar() -> justificativas.Justification:
        await get_pools().open()
        return await justificativas.classify(
            CONTEXTO, justification=justificativa, category=categoria
        )

    return asyncio.run(_classificar())


def validar(justificativa: str) -> justificativas.Justification:
    async def _validar() -> justificativas.Justification:
        await get_pools().open()
        return await justificativas.validate(CONTEXTO, justification=justificativa)

    return asyncio.run(_validar())


def apurar() -> ciclo.Cycle:
    async def _apurar() -> ciclo.Cycle:
        await get_pools().open()
        return await ciclo.compute_cycle(
            CONTEXTO, kind=ciclo.FOOD_BASKET, period_year=ANO, period_month=MES
        )

    return asyncio.run(_apurar())


def apuracao_recusa() -> str:
    """A recusa como texto. "(não recusou)" é resposta possível — e é a que falha."""
    try:
        apurar()
    except ciclo.UncuratedJustificationError as recusa:
        return str(recusa)
    return "(não recusou)"


def nomeada(mensagem: str) -> str:
    achado = re.search(r"«(.+?)»", mensagem)
    return achado.group(1) if achado else "(sem string nomeada)"


def direito(cycle: ciclo.Cycle) -> dict[str, tuple[bool, str | None]]:
    return {linha.name: (linha.entitled, linha.reason) for linha in cycle.lines}


# ---------------------------------------------------------------------------
# 1. Sem curadoria: a apuração recusa e diz qual string
# ---------------------------------------------------------------------------
print("\n--- 1. sem curadoria: a recusa nomeia a string, e validar não tem o que conferir")
sql(_LIMPAR)
sql(_CADASTRO)
semear_pessoas_e_afastamentos()

pendente = fila()
igual(
    "a fila traz as cinco do espelho, canonicalizadas e por peso",
    [(linha.justification, linha.occurrences) for linha in pendente.rows],
    [("FÉRIAS", 43), ("ATESTED", 13), ("ATEST M", 5), ("AFASTAD", 2), ("FALTA", 1)],
)
igual("nenhuma classificada", [linha.category for linha in pendente.rows], [None] * 5)
igual("as cinco são pendência", pendente.pending, 5)
igual(
    "e a fila mostra desde quando cada uma aparece",
    (pendente.rows[0].first_leave, pendente.rows[0].last_leave),
    (date(2024, 7, 1), date(2026, 8, 1)),
)

recusa = apuracao_recusa()
contem("a apuração da cesta de 09/2026 recusa", recusa, "não está classificada")
igual(
    "e nomeia uma das cinco",
    nomeada(recusa) in {linha.justification for linha in pendente.rows},
    True,
)

try:
    validar("FALTA")
    sem_classe = "(não recusou)"
except justificativas.UnclassifiedJustificationError as erro:
    sem_classe = str(erro)
contem("validar o que ninguém classificou é recusa nomeada", sem_classe, "não foi classificada")
igual(
    "e nada foi gravado no mapa",
    sql(
        f"select count(*) as n from app.leave_justification_map where tenant_id='{TENANT}'",
        uma=True,
    )["n"],
    0,
)

# ---------------------------------------------------------------------------
# 2. Classificadas e não validadas: a apuração CONTINUA recusando
# ---------------------------------------------------------------------------
print("\n--- 2. classificadas pela porta, sem aval: a apuração continua parada")
for justificativa, (categoria, _, _) in CINCO.items():
    curada = classificar(justificativa, categoria)
    # A porta recebe a string como a ORIGEM a escreve e grava a chave do BANCO.
    igual(f"«{justificativa}» entra como {curada.justification}", curada.validated, False)

igual(
    "as cinco chaves gravadas são as canônicas",
    [
        linha["justification"]
        for linha in sql(
            f"select justification from app.leave_justification_map "
            f"where tenant_id = '{TENANT}' order by justification"
        )
    ],
    # `ATEST M` vem antes de `ATESTED` porque quem ordena é a colação do
    # banco, e não a tabela ASCII — o espaço não conta.
    ["AFASTAD", "ATEST M", "ATESTED", "FALTA", "FÉRIAS"],
)
igual(
    "nenhuma carimbada na classificação",
    sql(
        f"select count(*) as n from app.leave_justification_map "
        f"where tenant_id='{TENANT}' and validated_at is not null",
        uma=True,
    )["n"],
    0,
)
igual("e as cinco continuam pendentes", fila().pending, 5)

recusa = apuracao_recusa()
contem("a apuração recusa por falta de VALIDAÇÃO, não de classificação", recusa, "ninguém validou")

# ---------------------------------------------------------------------------
# 3. Validadas: a apuração roda — e a curadoria decide quem perde a cesta
# ---------------------------------------------------------------------------
print("\n--- 3. validadas: a competência deixa de recusar, e o dinheiro muda de mão")
for justificativa in CINCO:
    validar(justificativa)

igual("sem pendência", fila().pending, 0)
igual("sem afastamento sem nome", fila().without_justification, 0)

cycle = apurar()
linhas = direito(cycle)
igual("a apuração devolve as cinco pessoas", len(linhas), 5)
igual("quem tem FALTA em agosto perde a cesta", linhas["Ana Faltou"][0], False)
contem(
    "e o motivo diz por quê", linhas["Ana Faltou"][1] or "", "falta(s) injustificada(s) em 08/2026"
)
igual("quem tem FÉRIAS fica com ela", linhas["Bea Ferias"], (True, None))
igual("quem tem atestado também", linhas["Caio Atestado"], (True, None))
igual("nas duas grafias", linhas["Dora Atestado"], (True, None))
igual("e quem está afastado idem", linhas["Edu Afastado"], (True, None))

# ---------------------------------------------------------------------------
# 4. Reclassificar derruba o aval — e nunca apaga a linha
# ---------------------------------------------------------------------------
print("\n--- 4. reclassificar é update, volta a provisório, e a apuração para de novo")
antes = sql(
    f"select count(*) as n from app.leave_justification_map where tenant_id='{TENANT}'", uma=True
)["n"]
classificar("FALTA", "vacation")
depois = sql(
    f"select count(*) as n from app.leave_justification_map where tenant_id='{TENANT}'", uma=True
)["n"]
igual("a linha continua uma só (nada apagado, nada duplicado)", (antes, depois), (5, 5))
igual(
    "e voltou a provisória",
    sql(
        f"select validated_at, validated_by from app.leave_justification_map "
        f"where tenant_id='{TENANT}' and justification='FALTA'",
        uma=True,
    ),
    {"validated_at": None, "validated_by": None},
)
contem("a apuração recusa de novo", apuracao_recusa(), "ninguém validou")

# ---------------------------------------------------------------------------
# 5. A classificação move dinheiro — o positivo que torna o cenário 3 afirmação
# ---------------------------------------------------------------------------
print("\n--- 5. validada como férias, a MESMA falta devolve a cesta a quem faltou")
validar("FALTA")
igual("agora Ana fica com a cesta", direito(apurar())["Ana Faltou"], (True, None))

classificar("FALTA", "unjustified_absence")
validar("FALTA")
igual(
    "e desclassificada de volta, ela a perde outra vez",
    direito(apurar())["Ana Faltou"][0],
    False,
)

# ---------------------------------------------------------------------------
# 6. Nada é apagado: nem pela porta, nem por `service_role`
# ---------------------------------------------------------------------------
print("\n--- 6. a trilha fica inteira, e o `delete` não existe nem como privilégio")
igual(
    "as cinco linhas, depois de nove escritas",
    sql(
        f"select count(*) as n from app.leave_justification_map where tenant_id='{TENANT}'",
        uma=True,
    )["n"],
    5,
)
igual(
    "service_role não tem delete nesta tabela",
    sql(
        "select has_table_privilege('service_role','app.leave_justification_map','DELETE') as pode",
        uma=True,
    )["pode"],
    False,
)
trilha = sql(
    f"select count(*) as n from app.audit_log "
    f"where tenant_id = '{TENANT}' and entity = 'leave_justification_map'",
    uma=True,
)["n"]
# 5 classificações + 5 validações + 3 atos do cenário 4/5 + 1 revalidação.
igual("cada ato deixou uma linha de trilha", trilha, 14)
igual(
    "e a trilha guarda o estado anterior de quem foi reclassificada",
    sql(
        f"select count(*) as n from app.audit_log where tenant_id = '{TENANT}' "
        f"and entity = 'leave_justification_map' and entity_id = 'FALTA' "
        f"and antes ->> 'category' = 'unjustified_absence'",
        uma=True,
    )["n"]
    > 0,
    True,
)

# ---------------------------------------------------------------------------
# 7. O afastamento SEM NOME: trava a apuração e não é curável
# ---------------------------------------------------------------------------
print("\n--- 7. o afastamento sem justificativa nenhuma: contado, e fora da fila")
sql(
    f"""
    insert into secullum."FuncionarioAfastamento"
      (funcionario_id, "AfastamentoId", "Inicio", "Fim", "JustificativaNome", tenant_id)
    values ('56000000-0000-0000-0000-00000000f005', 900, '2026-08-20', '2026-08-21', null,
            '{TENANT}');
    """
)
sem_nome = fila()
igual("ele não entra na fila (não há o que classificar)", len(sem_nome.rows), 5)
igual("mas é contado à parte", sem_nome.without_justification, 1)
igual("e a fila continua sem pendência de curadoria", sem_nome.pending, 0)
contem(
    "⛔ e a apuração para mesmo com as cinco validadas",
    apuracao_recusa(),
    "há afastamento sem justificativa no Secullum",
)
try:
    classificar("   ", "unjustified_absence")
    recusa_vazia = "(não recusou)"
except justificativas.UnknownJustificationError as erro:
    recusa_vazia = str(erro)
contem("e ele não é curável pela porta", recusa_vazia, "não tem o que classificar")

sql(
    f'delete from secullum."FuncionarioAfastamento" '
    f"where tenant_id = '{TENANT}' and \"AfastamentoId\" = 900"
)
igual("removido o afastamento sem nome, a competência volta a apurar", len(apurar().lines), 5)

# ---------------------------------------------------------------------------
# 8. O eixo de tenant da ESCRITA: a porta de um cliente não encosta no outro
# ---------------------------------------------------------------------------
# `bind_tenant` se satisfaz com UM `%(tenant_id)s` na instrução — um `update`
# que perdesse o filtro e o recuperasse num `exists` decorativo passava no
# estrangulamento, no pytest e nesta suíte. O que pega é medir duas linhas com
# a MESMA chave, uma em cada cliente.
print("\n--- 8. a escrita de um cliente não toca a curadoria do outro")
sql(_LIMPAR)
sql(_CADASTRO)
semear_pessoas_e_afastamentos()
sql(
    f"insert into auth.users (id, email) values ('{VIZINHO_USER}', 'vizinho.s6@teste');"
    f"insert into app.tenant (id, slug, name) values ('{VIZINHO}', 's6-vizinho', 'Vizinho');"
    f"insert into app.leave_justification_map "
    f"  (tenant_id, justification, category, validated_by, validated_at, notes) values "
    # MESMA chave e MESMA categoria do que vamos validar aqui: é o que deixa o
    # filtro de tenant como a única coisa separando as duas linhas.
    f"  ('{VIZINHO}', 'FALTA', 'vacation', '{VIZINHO_USER}', now(), 'do vizinho')"
)
antes_vizinho = sql(
    f"select category, notes, validated_at is not null as val "
    f"from app.leave_justification_map where tenant_id = '{VIZINHO}'",
    uma=True,
)

classificar("FALTA", "vacation")   # o MESMO texto, no cliente de cá
validar("FALTA")

depois_vizinho = sql(
    f"select category, notes, validated_at is not null as val "
    f"from app.leave_justification_map where tenant_id = '{VIZINHO}'",
    uma=True,
)
igual("a linha do vizinho não foi recarimbada nem mudou", dict(depois_vizinho), dict(antes_vizinho))
igual(
    "e quem validou a linha do vizinho continua sendo o vizinho",
    str(
        sql(
            f"select validated_by from app.leave_justification_map where tenant_id = '{VIZINHO}'",
            uma=True,
        )["validated_by"]
    ),
    VIZINHO_USER,
)
igual(
    "e a deste cliente é a que mudou",
    sql(
        f"select category from app.leave_justification_map "
        f"where tenant_id = '{TENANT}' and justification = 'FALTA'",
        uma=True,
    )["category"],
    "vacation",
)
igual(
    "duas linhas 'FALTA' no banco, uma por cliente",
    sql("select count(*) as n from app.leave_justification_map where justification = 'FALTA'", uma=True)["n"],
    2,
)
igual(
    "e a trilha do vizinho continua vazia",
    sql(f"select count(*) as n from app.audit_log where tenant_id = '{VIZINHO}'", uma=True)["n"],
    0,
)

# ---------------------------------------------------------------------------
# 9. Espaço que não é espaço: os três juízes têm de aparar a mesma coisa
# ---------------------------------------------------------------------------
# `str.strip()` do Python apara tabulação, quebra de linha e NBSP; o `btrim` do
# Postgres apara só `' '`. Com as duas réguas diferentes, um afastamento com
# NBSP colado de outra tela era apurado sob a curadoria de OUTRA chave — sem
# erro e sem aviso. Achado da revisão do S6.
print("\n--- 9. tabulação e NBSP: a porta, a fila e o apurador veem a mesma chave")
sql(_LIMPAR)
sql(_CADASTRO)
semear_pessoas_e_afastamentos()
# A mesma pessoa que já tem FALTA ganha um segundo afastamento, com tabulação.
sql(
    f'insert into secullum."FuncionarioAfastamento" '
    f'  (id, funcionario_id, "AfastamentoId", "JustificativaNome", "Inicio", "Fim", tenant_id) '
    f"select '56000000-0000-0000-0000-0000000009a1', f.id, 901, 'FALTA' || chr(9), "
    f"       date '{ANO:04d}-08-20', date '{ANO:04d}-08-20', '{TENANT}' "
    f'  from secullum."Funcionario" f '
    f"  where f.tenant_id = '{TENANT}' order by f.\"FuncionarioId\" limit 1"
)

na_fila = [linha.justification for linha in fila().rows]
igual("a fila traz a chave com a tabulação, como o banco a agrupa", "FALTA\t" in na_fila, True)

# E a porta grava exatamente essa chave — o `check` da tabela é o terceiro juiz
# e recusaria qualquer outra coisa.
curada = classificar("FALTA\t", "vacation")
igual("a porta grava a mesma chave que a fila mostrou", curada.justification, "FALTA\t")
validar("FALTA\t")
# O fecho: o apurador procura a chave dele e ACHA a que foi curada. Com as
# réguas divergentes, ele procuraria 'FALTA' e apuraria sob a curadoria alheia.
for justificativa, (categoria, _, _) in CINCO.items():
    if justificativa != "FALTA":
        classificar(justificativa, categoria)
        validar(justificativa)
classificar("FALTA", "unjustified_absence")
validar("FALTA")
igual(
    "duas linhas distintas no mapa: a com tabulação e a sem",
    sorted(
        linha["justification"]
        for linha in sql(
            f"select justification from app.leave_justification_map "
            f"where tenant_id = '{TENANT}' and justification like 'FALTA%'"
        )
    ),
    ["FALTA", "FALTA\t"],
)
igual("e, com as duas curadas, a competência apura", len(apurar().lines), 5)

sql(_LIMPAR)

print()
if falhas:
    print(f"  ✖ {len(falhas)} FALHA(S)")
    sys.exit(1)
print("================================================")
print(" CURADORIA DE JUSTIFICATIVA (S6): TODOS OS TESTES OK")
print("================================================")
