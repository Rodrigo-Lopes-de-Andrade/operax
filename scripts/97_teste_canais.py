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

SEGUNDA PARTE — A CREDENCIAL (C2), CONTRA O COFRE DE VERDADE
O banco de ensaio tem o `supabase_vault` 0.3.1, o mesmo de produção, então o que
`operax/core/vault.py` e as três rotas de credencial fazem é executado aqui, com
o SQL real dos dois módulos, em `begin … rollback`:

* **papéis**: `util.is_admin` diz sim a `owner` e `hr`, não a `unit_supervisor`
  e `executive` — a tabela que o pytest só estuba;
* **gate 1, o lado do banco**: a gravação do segredo ligada a outro tenant não
  cria nada (zero linhas, `vault.secrets` não cresce); o caminho feliz cria
  exatamente 1 integração, N ponteiros e N segredos;
* **cofre de verdade**: o ciphertext em `vault.secrets.secret` ≠ valor; a leitura
  pelo ponteiro devolve o valor; regravar **atualiza** (o `count` não cresce) e a
  leitura devolve o novo;
* **gate 2**: a linha da consulta do `GET` varrida como JSON — nem o valor nem
  `vault_id`;
* **troca de provedor**: `meta_cloud` ativo → `z_api` gravado → um só ativo, e é
  o `z_api`; o `meta_cloud` continua existindo, inativo — e a desativação
  seguinte devolve **só** o `z_api`, não a linha inativa;
* **isolamento**: outro tenant não lê nem sobrescreve pelo `join`;
* **atomicidade**: falha injetada depois do primeiro segredo desfaz integração,
  ponteiro e linha do cofre;
* **auditoria**: a linha leva as chaves, e o `depois::text` não contém o valor.

O valor de teste é uma string óbvia; nenhum segredo real passa por aqui.
"""

import importlib.util
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
COFRE = RAIZ / "backend" / "operax" / "core" / "vault.py"

USUARIO = "7c000000-0000-0000-0000-000000000001"
TENANT = "7ca70000-0000-0000-0000-0000000000a1"
OUTRO = "7ca70000-0000-0000-0000-0000000000b1"

# A credencial: outro par de tenants, quatro papéis no primeiro e um no segundo.
C_TENANT = "7ca70000-0000-0000-0000-0000000000c1"
C_OUTRO = "7ca70000-0000-0000-0000-0000000000d1"
C_OWNER = "7c000000-0000-0000-0000-0000000000c1"
C_HR = "7c000000-0000-0000-0000-0000000000c2"
C_SUPERVISOR = "7c000000-0000-0000-0000-0000000000c3"
C_EXECUTIVE = "7c000000-0000-0000-0000-0000000000c4"
C_OUTRO_OWNER = "7c000000-0000-0000-0000-0000000000d1"
#: Valores de teste, óbvios de propósito. Nenhum é real.
VALOR = "valor-de-teste-nao-e-real"
VALOR2 = "segundo-valor-de-teste-nao-e-real"
DESCRICAO = "descricao de teste"


def whatsapp_providers() -> str:
    """`'meta_cloud', 'z_api', 'uazapi'` — como `canais.py` e `outbox.py` renderizam o token."""
    caminho = RAIZ / "backend" / "operax" / "alertas" / "capacidades.py"
    spec = importlib.util.spec_from_file_location("capacidades", caminho)
    assert spec is not None and spec.loader is not None
    capacidades = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = capacidades  # `dataclass(slots=True)` procura o módulo aqui
    spec.loader.exec_module(capacidades)
    return ", ".join(f"'{provider}'" for provider in capacidades.WHATSAPP_PROVIDERS)


def instrucoes(modulo: pathlib.Path = MODULO) -> dict[str, str]:
    fonte = modulo.read_text()
    achadas = re.findall(r'^(_?[A-Z][A-Z_]*_SQL) = """(.*?)"""', fonte, re.DOTALL | re.MULTILINE)
    lista = whatsapp_providers()
    return {nome: sql.replace("{whatsapp_providers}", lista) for nome, sql in achadas}


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


CENARIO_CREDENCIAL = """
begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

create or replace function pg_temp.assert_not_in(rotulo text, palheiro text, agulha text)
returns void language plpgsql as $$
begin
  if position(agulha in palheiro) > 0 then
    raise exception 'FALHA [%]: o valor do segredo apareceu', rotulo;
  end if;
  raise notice '  ok  %', rotulo;
end $$;

insert into auth.users (id, email) values
  ('{C_OWNER}',       'owner@credencial'),
  ('{C_HR}',          'hr@credencial'),
  ('{C_SUPERVISOR}',  'supervisor@credencial'),
  ('{C_EXECUTIVE}',   'executive@credencial'),
  ('{C_OUTRO_OWNER}', 'owner@outro');

insert into app.tenant (id, slug, name) values
  ('{C_TENANT}', 'credencial-teste', 'Credencial'),
  ('{C_OUTRO}',  'credencial-outro', 'Outro');

insert into app.tenant_member (tenant_id, user_id, role) values
  ('{C_TENANT}', '{C_OWNER}',       'owner'),
  ('{C_TENANT}', '{C_HR}',          'hr'),
  ('{C_TENANT}', '{C_SUPERVISOR}',  'unit_supervisor'),
  ('{C_TENANT}', '{C_EXECUTIVE}',   'executive'),
  ('{C_OUTRO}',  '{C_OUTRO_OWNER}', 'owner');

-- ---------------------------------------------------------------------------
-- Papéis: a tabela de `util.is_admin` que o pytest só estuba
-- ---------------------------------------------------------------------------
do $$
declare
  quem record;
  admin boolean;
begin
  for quem in
    select * from (values
      ('owner',           '{C_OWNER}'::uuid,      true),
      ('hr',              '{C_HR}'::uuid,         true),
      ('unit_supervisor', '{C_SUPERVISOR}'::uuid, false),
      ('executive',       '{C_EXECUTIVE}'::uuid,  false)
    ) as v(papel, uid, esperado)
  loop
    set local role authenticated;
    perform set_config('request.jwt.claim.sub', quem.uid::text, true);
    select x.admin into admin from ({PERMISSION}) x;
    reset role;
    perform pg_temp.assert_eq('util.is_admin para ' || quem.papel, admin::text, quem.esperado::text);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Gate 1, o lado do banco: ligado a outro tenant, a gravação não cria nada
-- ---------------------------------------------------------------------------
create temp table marcos (nome text primary key, contagem bigint);
insert into marcos values ('vault_antes', (select count(*) from vault.secrets));

do $$
declare
  v_meta uuid;
  n int;
begin
  -- A rota: desliga o que estava ativo (nada), upsert do meta_cloud.
  execute $q${DEACTIVATE}$q$;
  execute $q$with x as ({UPSERT_META}) select id from x$q$ into v_meta;
  perform pg_temp.assert_eq('o upsert devolve o id da integração', (v_meta is not null)::text, 'true');

  -- O segredo ligado ao OUTRO tenant, apontando para a integração do primeiro.
  execute $q$with x as ({CREATE_OUTRO_TENANT}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('outro tenant: zero linhas gravadas', n::text, '0');
  perform pg_temp.assert_eq('outro tenant: vault.secrets não cresceu',
    (select count(*) from vault.secrets)::text, (select contagem from marcos where nome = 'vault_antes')::text);
  perform pg_temp.assert_eq('outro tenant: nenhum ponteiro',
    (select count(*) from app.integration_secret)::text, '0');

  -- O caminho feliz: um segredo por campo secreto do meta_cloud (um só: token).
  execute $q$with x as ({CREATE_META_TOKEN}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('caminho feliz: o segredo entrou', n::text, '1');
  perform pg_temp.assert_eq('caminho feliz: exatamente 1 integração de WhatsApp ativa',
    (select count(*) from app.integration where tenant_id = '{C_TENANT}' and active
       and provider in ({PROVIDERS}))::text, '1');
  perform pg_temp.assert_eq('caminho feliz: 1 ponteiro',
    (select count(*) from app.integration_secret)::text, '1');
  perform pg_temp.assert_eq('caminho feliz: 1 linha nova em vault.secrets',
    (select count(*) from vault.secrets)::text, ((select contagem from marcos where nome = 'vault_antes') + 1)::text);
end $$;

-- ---------------------------------------------------------------------------
-- O cofre de verdade: cifrado, ida e volta, e regravar atualiza
-- ---------------------------------------------------------------------------
do $$
declare
  v_meta uuid := (select id from app.integration where tenant_id = '{C_TENANT}' and provider = 'meta_cloud');
  cifrado text;
  lido text;
  n int;
begin
  select s.secret into cifrado
    from app.integration_secret p join vault.secrets s on s.id = p.vault_id
   where p.integration_id = v_meta and p.key = 'token';
  perform pg_temp.assert_not_in('vault.secrets.secret é o ciphertext, não o valor', cifrado, '{VALOR}');
  perform pg_temp.assert_eq('o nome no cofre é determinístico pelo ponteiro',
    (select s.name from app.integration_secret p join vault.secrets s on s.id = p.vault_id
      where p.integration_id = v_meta and p.key = 'token'),
    'app.integration_secret/' || v_meta || '/token');

  execute $q${READ_META_TOKEN}$q$ into lido;
  perform pg_temp.assert_eq('read_secret devolve o valor (ida e volta)', lido, '{VALOR}');

  -- Regravar: o caminho de update do módulo.
  -- `_UPDATE_SQL` já é uma CTE modificadora (não aninha): conta pelo diagnóstico.
  execute $q${UPDATE_META_TOKEN_V2}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('regravar encontra o ponteiro', n::text, '1');
  perform pg_temp.assert_eq('regravar NÃO cria linha em vault.secrets',
    (select count(*) from vault.secrets)::text, ((select contagem from marcos where nome = 'vault_antes') + 1)::text);
  execute $q${READ_META_TOKEN}$q$ into lido;
  perform pg_temp.assert_eq('e a leitura devolve o novo valor', lido, '{VALOR2}');
end $$;

-- ---------------------------------------------------------------------------
-- Gate 2: a consulta do GET, varrida como JSON
-- ---------------------------------------------------------------------------
do $$
declare
  linha json;
  chaves text;
begin
  select row_to_json(x) into linha from ({STATUS}) x;
  perform pg_temp.assert_eq('o GET vê uma credencial configurada', (linha is not null)::text, 'true');
  perform pg_temp.assert_eq('do meta_cloud', linha ->> 'provider', 'meta_cloud');
  perform pg_temp.assert_eq('com a identidade pública', linha ->> 'public_identity', 'FastPark (+55 21 99999-0000)');
  perform pg_temp.assert_not_in('gate 2: o valor não está em coluna nenhuma', linha::text, '{VALOR}');
  perform pg_temp.assert_not_in('gate 2: nem o valor anterior', linha::text, '{VALOR2}');
  select string_agg(k, ',' order by k) into chaves from json_object_keys(linha) k;
  perform pg_temp.assert_eq('gate 2: as colunas são só as do contrato (sem vault_id)', chaves,
    'provider,public_identity,updated_at');
end $$;

-- ---------------------------------------------------------------------------
-- Isolamento: o outro tenant não lê nem sobrescreve pelo join
-- ---------------------------------------------------------------------------
do $$
declare
  n int;
  lido text;
begin
  select count(*) into n from ({STATUS_OUTRO}) x;
  perform pg_temp.assert_eq('outro tenant: o GET não vê o ponteiro', n::text, '0');
  execute $q${READ_OUTRO_TENANT}$q$ into lido;
  perform pg_temp.assert_eq('outro tenant: read_secret devolve nada', coalesce(lido, '(nulo)'), '(nulo)');
  execute $q${UPDATE_OUTRO_TENANT}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('outro tenant: o update não alcança o ponteiro', n::text, '0');
  execute $q${READ_META_TOKEN}$q$ into lido;
  perform pg_temp.assert_eq('e o valor do primeiro tenant continua o dele', lido, '{VALOR2}');
end $$;

-- ---------------------------------------------------------------------------
-- Troca de provedor: meta_cloud ativo → z_api gravado → um só ativo, o z_api
-- ---------------------------------------------------------------------------
do $$
declare
  anterior text;
  v_z uuid;
  n int;
begin
  execute $q$with x as ({DEACTIVATE}) select string_agg(provider, ',') from x$q$ into anterior;
  perform pg_temp.assert_eq('a desativação devolve quem estava ativo', anterior, 'meta_cloud');
  execute $q$with x as ({UPSERT_Z}) select id from x$q$ into v_z;
  execute $q$with x as ({CREATE_Z_TOKEN}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('z_api: token gravado', n::text, '1');
  execute $q$with x as ({CREATE_Z_CLIENT_TOKEN}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('z_api: client_token gravado', n::text, '1');

  perform pg_temp.assert_eq('um só WhatsApp ativo no tenant',
    (select count(*) from app.integration where tenant_id = '{C_TENANT}' and active
       and provider in ({PROVIDERS}))::text, '1');
  perform pg_temp.assert_eq('e é o z_api',
    (select provider from app.integration where tenant_id = '{C_TENANT}' and active
       and provider in ({PROVIDERS})), 'z_api');
  perform pg_temp.assert_eq('o meta_cloud continua existindo, inativo',
    (select active::text from app.integration where tenant_id = '{C_TENANT}' and provider = 'meta_cloud'), 'false');
  perform pg_temp.assert_eq('ponteiros: 1 do meta_cloud + 2 do z_api',
    (select count(*) from app.integration_secret)::text, '3');
  perform pg_temp.assert_eq('vault.secrets: três novas ao todo',
    (select count(*) from vault.secrets)::text, ((select contagem from marcos where nome = 'vault_antes') + 3)::text);
  perform pg_temp.assert_eq('o GET agora diz z_api',
    (select provider from ({STATUS}) x), 'z_api');

  -- Regravar o mesmo provedor é upsert, não segunda linha.
  execute $q$with x as ({UPSERT_Z}) select id from x$q$ into v_z;
  perform pg_temp.assert_eq('regravar o z_api não cria segunda integração',
    (select count(*) from app.integration where tenant_id = '{C_TENANT}' and provider = 'z_api')::text, '1');
end $$;

-- ---------------------------------------------------------------------------
-- Atomicidade: falha depois do primeiro segredo desfaz tudo
-- ---------------------------------------------------------------------------
-- Aqui o meta_cloud está INATIVO ao lado do z_api ativo. Sem `and active` o
-- `returning` traria os dois, em ordem de heap, e `previous[0]` da rota poderia
-- gravar `meta_cloud` como o provedor anterior. Só o ativo volta. Fora de
-- qualquer sub-bloco com `exception`, de propósito: uma asserção engolida por
-- `when others` é verde que mente (aconteceu aqui, na mutação C1 do ciclo 2).
do $$
declare
  anterior text;
  v_z uuid;
begin
  execute $q$with x as ({DEACTIVATE}) select string_agg(provider, ',' order by provider) from x$q$
    into anterior;
  perform pg_temp.assert_eq('a desativação devolve SÓ o que estava ativo (o meta_cloud inativo não)',
    anterior, 'z_api');
  -- Devolve o estado: o z_api volta a ser o ativo, pelo mesmo upsert da rota.
  execute $q$with x as ({UPSERT_Z}) select id from x$q$ into v_z;
  perform pg_temp.assert_eq('e o upsert o religa',
    (select provider from app.integration where tenant_id = '{C_TENANT}' and active
       and provider in ({PROVIDERS})), 'z_api');
end $$;

do $$
declare
  v_u uuid;
  n int;
begin
  begin
    execute $q${DEACTIVATE}$q$;
    execute $q$with x as ({UPSERT_U}) select id from x$q$ into v_u;
    execute $q$with x as ({CREATE_U_TOKEN}) select count(*) from x$q$ into n;
    perform pg_temp.assert_eq('atomicidade: o primeiro segredo entrou', n::text, '1');
    raise exception using errcode = 'OX001', message = 'injetada: o segundo segredo falhou';
  exception when sqlstate 'OX001' then
    -- Só a falha injetada. Uma asserção reprovada lá dentro (P0001) atravessa
    -- e derruba o script, como deve.
    raise notice '  ok  a falha injetada foi capturada (%)', sqlerrm;
  end;

  perform pg_temp.assert_eq('atomicidade: o uazapi não ficou',
    (select count(*) from app.integration where tenant_id = '{C_TENANT}' and provider = 'uazapi')::text, '0');
  perform pg_temp.assert_eq('atomicidade: o z_api segue ativo',
    (select provider from app.integration where tenant_id = '{C_TENANT}' and active
       and provider in ({PROVIDERS})), 'z_api');
  perform pg_temp.assert_eq('atomicidade: os ponteiros continuam 3',
    (select count(*) from app.integration_secret)::text, '3');
  perform pg_temp.assert_eq('atomicidade: a linha do cofre do primeiro segredo sumiu',
    (select count(*) from vault.secrets)::text, ((select contagem from marcos where nome = 'vault_antes') + 3)::text);
end $$;

-- ---------------------------------------------------------------------------
-- Auditoria: chaves, nunca valores
-- ---------------------------------------------------------------------------
do $$
declare
  trilha record;
begin
  execute $q${AUDIT}$q$;
  select * into trilha from app.audit_log
   where tenant_id = '{C_TENANT}' and entity = 'integration' order by created_at desc limit 1;
  perform pg_temp.assert_eq('a auditoria gravou a troca', trilha.action, 'update');
  perform pg_temp.assert_eq('com as chaves', (trilha.depois -> 'keys')::text, '["token", "client_token"]');
  perform pg_temp.assert_eq('e o provedor anterior', trilha.antes ->> 'provider', 'meta_cloud');
  perform pg_temp.assert_not_in('auditoria: sem o valor', trilha.depois::text || trilha.antes::text, '{VALOR}');
  perform pg_temp.assert_not_in('auditoria: sem o segundo valor', trilha.depois::text || trilha.antes::text, '{VALOR2}');
end $$;

rollback;
"""


def rodar(script: str) -> None:
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


def credencial(fixas: dict[str, str], cofre: dict[str, str]) -> str:
    """O cenário da credencial, com o SQL real dos dois módulos ligado aos valores."""
    z_config = '{"instance_id": "3C4E5F6A7B8C9D0E", "public_identity": "instância conectada"}'
    meta_config = '{"phone_number_id": "123456789012345", "public_identity": "FastPark (+55 21 99999-0000)"}'
    u_config = '{"base_url": "https://instancia.exemplo.test", "public_identity": "x conectado"}'
    v_meta = "(select id from app.integration where tenant_id = '{C_TENANT}' and provider = 'meta_cloud')"
    v_z = "(select id from app.integration where tenant_id = '{C_TENANT}' and provider = 'z_api')"
    v_u = "(select id from app.integration where tenant_id = '{C_TENANT}' and provider = 'uazapi')"

    def cria(tenant: str, integracao: str, key: str, valor: str) -> str:
        return ligar(
            cofre["_CREATE_SQL"], tenant_id=tenant, key=key, value=valor, description=DESCRICAO
        ).replace("%(integration_id)s", integracao)

    def atualiza(tenant: str, integracao: str, key: str, valor: str) -> str:
        return ligar(cofre["_UPDATE_SQL"], tenant_id=tenant, key=key, value=valor).replace(
            "%(integration_id)s", integracao
        )

    def le(tenant: str, integracao: str, key: str) -> str:
        return ligar(cofre["_READ_SQL"], tenant_id=tenant, key=key).replace(
            "%(integration_id)s", integracao
        )

    depois = '{"provider": "z_api", "public_identity": "instância conectada", "keys": ["token", "client_token"]}'
    substituicoes = {
        "{PERMISSION}": ligar(fixas["_PERMISSION_SQL"], tenant_id=C_TENANT),
        "{STATUS}": ligar(fixas["_CREDENTIAL_STATUS_SQL"], tenant_id=C_TENANT),
        "{STATUS_OUTRO}": ligar(fixas["_CREDENTIAL_STATUS_SQL"], tenant_id=C_OUTRO),
        "{DEACTIVATE}": ligar(fixas["_DEACTIVATE_SQL"], tenant_id=C_TENANT),
        "{UPSERT_META}": ligar(
            fixas["_UPSERT_INTEGRATION_SQL"], tenant_id=C_TENANT, provider="meta_cloud", config=meta_config
        ),
        "{UPSERT_Z}": ligar(
            fixas["_UPSERT_INTEGRATION_SQL"], tenant_id=C_TENANT, provider="z_api", config=z_config
        ),
        "{UPSERT_U}": ligar(
            fixas["_UPSERT_INTEGRATION_SQL"], tenant_id=C_TENANT, provider="uazapi", config=u_config
        ),
        "{CREATE_OUTRO_TENANT}": cria(C_OUTRO, v_meta, "token", VALOR),
        "{CREATE_META_TOKEN}": cria(C_TENANT, v_meta, "token", VALOR),
        "{CREATE_Z_TOKEN}": cria(C_TENANT, v_z, "token", VALOR),
        "{CREATE_Z_CLIENT_TOKEN}": cria(C_TENANT, v_z, "client_token", VALOR),
        "{CREATE_U_TOKEN}": cria(C_TENANT, v_u, "token", VALOR),
        "{UPDATE_META_TOKEN_V2}": atualiza(C_TENANT, v_meta, "token", VALOR2),
        "{UPDATE_OUTRO_TENANT}": atualiza(C_OUTRO, v_meta, "token", VALOR),
        "{READ_META_TOKEN}": le(C_TENANT, v_meta, "token"),
        "{READ_OUTRO_TENANT}": le(C_OUTRO, v_meta, "token"),
        "{AUDIT}": ligar(
            fixas["_AUDIT_SQL"],
            tenant_id=C_TENANT,
            user_id=C_OWNER,
            antes='{"provider": "meta_cloud"}',
            depois=depois,
        ).replace("%(entity_id)s", v_z + "::text"),
        "{PROVIDERS}": whatsapp_providers(),
    }
    script = CENARIO_CREDENCIAL
    for marcador, texto in substituicoes.items():
        script = script.replace(marcador, texto)
    for nome, valor in {
        "{C_TENANT}": C_TENANT,
        "{C_OUTRO}": C_OUTRO,
        "{C_OWNER}": C_OWNER,
        "{C_HR}": C_HR,
        "{C_SUPERVISOR}": C_SUPERVISOR,
        "{C_EXECUTIVE}": C_EXECUTIVE,
        "{C_OUTRO_OWNER}": C_OUTRO_OWNER,
        "{VALOR}": VALOR,
        "{VALOR2}": VALOR2,
    }.items():
        script = script.replace(nome, valor)
    return script


def main() -> None:
    fixas = instrucoes()
    cofre = instrucoes(COFRE)
    esperadas = {
        "_READINESS_SQL",
        "_BLOCKED_SQL",
        "_PERMISSION_SQL",
        "_CREDENTIAL_STATUS_SQL",
        "_DEACTIVATE_SQL",
        "_UPSERT_INTEGRATION_SQL",
        "_AUDIT_SQL",
    }
    if set(fixas) != esperadas:
        print(f"  ✖ esperava as instruções {sorted(esperadas)} em canais.py, achei {sorted(fixas)}")
        sys.exit(1)
    esperadas_cofre = {"_UPDATE_SQL", "_CREATE_SQL", "_READ_SQL"}
    if set(cofre) != esperadas_cofre:
        print(f"  ✖ esperava {sorted(esperadas_cofre)} em vault.py, achei {sorted(cofre)}")
        sys.exit(1)

    problemas: list[str] = []
    for origem, lote in (("canais.py", fixas), ("vault.py", cofre)):
        for nome, sql in lote.items():
            r = psql(["-c", f"prepare p as {posicionar(sql)}"])
            if r.returncode != 0:
                problemas.append(f"{origem}:{nome} não compila: {r.stderr.strip().splitlines()[0]}")
    if problemas:
        for p in problemas:
            print(f"  ✖ {p}")
        sys.exit(1)
    print(f"  instruções fixas compiladas: {len(fixas)} de canais.py, {len(cofre)} de vault.py")

    script = (
        CENARIO.replace("{USUARIO}", USUARIO)
        .replace("{TENANT}", TENANT)
        .replace("{OUTRO}", OUTRO)
        .replace("{READINESS}", ligar(fixas["_READINESS_SQL"], tenant_id=TENANT))
        .replace("{BLOCKED_OUTRO}", ligar(fixas["_BLOCKED_SQL"], tenant_id=OUTRO))
        .replace("{BLOCKED}", ligar(fixas["_BLOCKED_SQL"], tenant_id=TENANT))
    )
    rodar(script)

    print("\n--- a credencial, contra o cofre de verdade")
    rodar(credencial(fixas, cofre))

    print("\n================================================")
    print(" TELA DE CONEXÕES E CREDENCIAL: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
