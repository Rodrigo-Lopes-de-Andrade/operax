#!/usr/bin/env python3
"""Prova a tela de Conexões contra o banco: a lista é a decomposição da contagem.

    python3 scripts/97_teste_canais.py

`tests/test_canais.py` confere as cláusulas de `_BLOCKED_SQL` contra a CTE da
função por texto; este script as **executa**. Primeiro compila as instruções
fixas de `server/routers/canais.py` contra o schema real (`prepare`). Depois
semeia dois tenants no `meta_cloud` com o mesmo template pendente e, no
primeiro, cinco regras — três que a função conta e duas que não — e afirma:

* como `authenticated`, `_BLOCKED_SQL` devolve exatamente o que
  `fn_whatsapp_readiness().rules_blocked` conta, nomeia as três, deixa de fora a
  desligada e a de e-mail, e traz os três formatos documentados em
  `BlockedAlertRule` (pendente, código inexistente, sem template);
* como `postgres`, que ignora RLS, o `tenant_id` escrito na consulta basta
  sozinho — o segundo tenant não vaza.

O SQL é lido do módulo em vez de copiado, pelo mesmo motivo do `93`: o módulo
puxa o driver, este teste roda fora do venv, e a cópia divergiria na primeira
alteração.
"""

import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}

MODULO = RAIZ / "backend" / "server" / "routers" / "canais.py"

USUARIO = "7c000000-0000-0000-0000-000000000001"
TENANT = "7ca70000-0000-0000-0000-0000000000a1"
OUTRO = "7ca70000-0000-0000-0000-0000000000b1"


def instrucoes() -> dict[str, str]:
    fonte = MODULO.read_text()
    return dict(re.findall(r'^(_?[A-Z][A-Z_]*_SQL) = """(.*?)"""', fonte, re.DOTALL | re.MULTILINE))


def posicionar(sql: str) -> str:
    """`%(nome)s` do psycopg vira `$n` do Postgres, na ordem de aparição."""
    ordem: list[str] = []

    def trocar(m: re.Match) -> str:
        if m.group(1) not in ordem:
            ordem.append(m.group(1))
        return f"${ordem.index(m.group(1)) + 1}"

    return re.sub(r"%\((\w+)\)s", trocar, sql)


def psql(argumentos: list[str], entrada: str | None = None):
    return subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", *argumentos],
        input=entrada,
        capture_output=True,
        text=True,
        env=ENV,
        check=False,  # o código de retorno é lido por quem chama
    )


def ligar(sql: str, **valores: str) -> str:
    for nome, valor in valores.items():
        sql = sql.replace(f"%({nome})s", f"'{valor}'")
    return sql


CENARIO = """
begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

insert into auth.users (id, email) values ('{USUARIO}', 'canais@teste');

insert into app.tenant (id, slug, name) values
  ('{TENANT}', 'canais-teste', 'Canais'),
  ('{OUTRO}',  'canais-outro', 'Outro');

-- Só o primeiro tenant tem membro: o segundo existe para provar o recorte.
insert into app.tenant_member (tenant_id, user_id, role)
values ('{TENANT}', '{USUARIO}', 'owner');

-- Os dois no provedor oficial, com o mesmo template pendente na Meta.
insert into app.integration (tenant_id, provider, active) values
  ('{TENANT}', 'meta_cloud', true),
  ('{OUTRO}',  'meta_cloud', true);

insert into app.message_template (tenant_id, code, variables, body, meta_status) values
  ('{TENANT}', 'deviation_summary', array['unit','occurrences'],
   'OperaX: {{1}} com {{2}} ocorrencias.', 'pending'),
  ('{OUTRO}',  'deviation_summary', array['unit','occurrences'],
   'OperaX: {{1}} com {{2}} ocorrencias.', 'pending');

-- Cinco regras no primeiro tenant. Três a função conta; duas ela não conta, e
-- cada uma por um motivo diferente: desligada, e canal que não alcança WhatsApp.
insert into app.alert_rule (tenant_id, name, content, channel, active, template_code) values
  ('{TENANT}', 'Ligada, template pendente',   'aggregate', 'whatsapp', true,  'deviation_summary'),
  ('{TENANT}', 'Ligada, codigo inexistente',  'aggregate', 'whatsapp', true,  'nao_existe'),
  ('{TENANT}', 'Ligada, sem template',        'aggregate', 'whatsapp', true,  null),
  ('{TENANT}', 'Desligada, template pendente','aggregate', 'whatsapp', false, 'deviation_summary'),
  ('{TENANT}', 'Ligada, so e-mail',           'aggregate', 'email',    true,  'deviation_summary'),
  ('{OUTRO}',  'Ligada no outro tenant',      'aggregate', 'whatsapp', true,  'deviation_summary');

-- ---------------------------------------------------------------------------
-- Como o usuário: a contagem da função e a lista da rota são o mesmo número
-- ---------------------------------------------------------------------------
do $$
declare
  prontidao record;
  n int;
  nomes text;
  pendente text;
  inexistente text;
  sem_template text;
begin
  set local role authenticated;
  set local request.jwt.claim.sub = '{USUARIO}';

  select * into prontidao from ({READINESS}) x;
  select count(*), string_agg(rule_name, ',' order by rule_name)
    into n, nomes
    from ({BLOCKED}) x;
  select coalesce(template_code, '(nulo)') || ' / ' || coalesce(meta_status, '(nulo)')
    into pendente from ({BLOCKED}) x where rule_name = 'Ligada, template pendente';
  select coalesce(template_code, '(nulo)') || ' / ' || coalesce(meta_status, '(nulo)')
    into inexistente from ({BLOCKED}) x where rule_name = 'Ligada, codigo inexistente';
  select coalesce(template_code, '(nulo)') || ' / ' || coalesce(meta_status, '(nulo)')
    into sem_template from ({BLOCKED}) x where rule_name = 'Ligada, sem template';

  reset role;

  perform pg_temp.assert_eq('a função vê o provedor oficial', prontidao.provider, 'meta_cloud');
  perform pg_temp.assert_eq('e diz que não está pronto', prontidao.ready::text, 'false');
  perform pg_temp.assert_eq('a função conta três regras bloqueadas', prontidao.rules_blocked::text, '3');
  perform pg_temp.assert_eq('a lista tem o mesmo tamanho que a contagem', n::text, prontidao.rules_blocked::text);
  perform pg_temp.assert_eq('e nomeia as três — a desligada e a de e-mail ficam de fora', nomes,
    'Ligada, codigo inexistente,Ligada, sem template,Ligada, template pendente');
  perform pg_temp.assert_eq('caso 1: template existe e está pendente', pendente, 'deviation_summary / pending');
  perform pg_temp.assert_eq('caso 2: código que não existe vem sem status', inexistente, 'nao_existe / (nulo)');
  perform pg_temp.assert_eq('caso 3: regra sem template vem com os dois nulos', sem_template, '(nulo) / (nulo)');
end $$;

-- ---------------------------------------------------------------------------
-- Sem RLS: o filtro escrito na consulta basta sozinho
-- ---------------------------------------------------------------------------
do $$
declare
  n_tenant int;
  n_outro int;
begin
  select count(*) into n_tenant from ({BLOCKED}) x;
  select count(*) into n_outro from ({BLOCKED_OUTRO}) x;
  perform pg_temp.assert_eq('como postgres, o tenant ligado devolve só as suas', n_tenant::text, '3');
  perform pg_temp.assert_eq('e o outro tenant, só a dele', n_outro::text, '1');
end $$;

-- ---------------------------------------------------------------------------
-- O positivo do par: a Meta aprova o template, e a conta muda dos dois lados
-- ---------------------------------------------------------------------------
-- Sem este bloco, "contagem = lista" ficaria verde num banco em que os dois
-- fossem sempre 3. Aprovar o template tem de tirar UMA regra da conta (a que o
-- cita); as outras duas seguem bloqueadas por motivos que a aprovação não cura.
update app.message_template
   set meta_status = 'approved'
 where tenant_id = '{TENANT}' and code = 'deviation_summary';

do $$
declare
  prontidao record;
  n int;
  nomes text;
begin
  set local role authenticated;
  set local request.jwt.claim.sub = '{USUARIO}';

  select * into prontidao from ({READINESS}) x;
  select count(*), string_agg(rule_name, ',' order by rule_name)
    into n, nomes from ({BLOCKED}) x;

  reset role;

  perform pg_temp.assert_eq('aprovado: a contagem cai para as duas sem cura', prontidao.rules_blocked::text, '2');
  perform pg_temp.assert_eq('e a lista acompanha', n::text, '2');
  perform pg_temp.assert_eq('a regra do template aprovado saiu; as outras duas ficaram', nomes,
    'Ligada, codigo inexistente,Ligada, sem template');
  perform pg_temp.assert_eq('ainda não está pronto — sobrou bloqueio', prontidao.ready::text, 'false');
end $$;

-- E com as outras duas desligadas, `ready` vira verdade: é o único caminho em
-- que a função diz "sim", e ele existe para que o "false" acima não seja um
-- "false" fixo.
update app.alert_rule
   set active = false
 where tenant_id = '{TENANT}'
   and name in ('Ligada, codigo inexistente', 'Ligada, sem template');

do $$
declare
  prontidao record;
  n int;
begin
  set local role authenticated;
  set local request.jwt.claim.sub = '{USUARIO}';
  select * into prontidao from ({READINESS}) x;
  select count(*) into n from ({BLOCKED}) x;
  reset role;

  perform pg_temp.assert_eq('zero bloqueadas na função', prontidao.rules_blocked::text, '0');
  perform pg_temp.assert_eq('zero na lista', n::text, '0');
  perform pg_temp.assert_eq('e agora PRONTO', prontidao.ready::text, 'true');
end $$;

rollback;
"""


def main() -> None:
    fixas = instrucoes()
    esperadas = {"_READINESS_SQL", "_BLOCKED_SQL"}
    if set(fixas) != esperadas:
        print(f"  ✖ esperava as instruções {sorted(esperadas)} em canais.py, achei {sorted(fixas)}")
        sys.exit(1)

    problemas: list[str] = []
    for nome, sql in fixas.items():
        r = psql(["-c", f"prepare p as {posicionar(sql)}"])
        if r.returncode != 0:
            problemas.append(f"{nome} não compila: {r.stderr.strip().splitlines()[0]}")
    if problemas:
        for p in problemas:
            print(f"  ✖ {p}")
        sys.exit(1)
    print(f"  instruções fixas da tela de Conexões compiladas: {len(fixas)}")

    script = (
        CENARIO.replace("{USUARIO}", USUARIO)
        .replace("{TENANT}", TENANT)
        .replace("{OUTRO}", OUTRO)
        .replace("{READINESS}", ligar(fixas["_READINESS_SQL"], tenant_id=TENANT))
        .replace("{BLOCKED_OUTRO}", ligar(fixas["_BLOCKED_SQL"], tenant_id=OUTRO))
        .replace("{BLOCKED}", ligar(fixas["_BLOCKED_SQL"], tenant_id=TENANT))
    )

    r = psql([], script)
    saida = "\n".join(
        linha
        for linha in (r.stdout + r.stderr).splitlines()
        if linha.strip()
        and not linha.startswith(("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK", "UPDATE", "CREATE"))
    )
    print(saida)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print("\n================================================")
    print(" TELA DE CONEXÕES: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
