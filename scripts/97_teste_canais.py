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

TERCEIRA PARTE — OS TEMPLATES (C2b), CONTRA O GATILHO E A POLICY DE VERDADE
As seis instruções novas de `canais.py` compilam e executam aqui:

* **o gatilho de verdade**: o upsert com corpo sem `{{2}}` levanta `P0001` com a
  frase que a rota devolve como `detail` — e a linha não muda;
* **trocar o nome na Meta volta a `draft`**: o upsert que mantém
  `meta_template_name` preserva `approved` (e depois `rejected` + razão); o que
  o troca leva `meta_status` a `draft` e `meta_rejection` a nulo, e `before`
  traz a linha anterior;
* **só o que mudou**: a instrução da sincronização grava 1 na primeira vez e 0
  na segunda com os mesmos valores; e com o id do outro tenant no array, o
  `tenant_id` ligado deixa a linha dele intacta;
* **a leitura sob RLS**: como o owner do tenant A, o `select` do catálogo vê o
  próprio e não vê o do tenant B — nem ligado ao tenant B.

QUARTA PARTE — O BOT (C3, onda 2a), OS DOIS CANAIS LADO A LADO
Um tenant com `meta_cloud` **e** `telegram` ativos, e o SQL real de `canais.py`:

* **as duas linhas**: `_READINESS_SQL` (agora `fn_channel_readiness`) devolve
  uma por canal; a do bot nasce `not ready` e sem saúde;
* **o estado do bot**: `_TELEGRAM_STATE_SQL` lê só as três chaves públicas de
  `config` e a idade da saúde; `_TELEGRAM_WEBHOOK_SQL` acrescenta o webhook sem
  apagar `public_identity`;
* **a saúde pela porta única**: `_RECORD_HEALTH_SQL` grava `connected` e a
  linha do bot vira `ready`; a mesma medição de novo não move
  `health_changed_at`, uma diferente move (regra da §7, pela instrução da rota);
  ligada ao OUTRO tenant, zero linhas e a saúde intacta;
* **linha 1 da SPEC §2.2 pela porta da credencial**: a `_DEACTIVATE_SQL` do
  canal `telegram` desliga o bot e **não** o `meta_cloud`; a do canal `whatsapp`
  desliga o `meta_cloud` e **não** o bot; `_CREDENTIAL_STATUS_SQL` responde por
  canal.

QUINTA PARTE — O WEBHOOK `/start` (C3, onda 2b), O SQL DO PASSO 6 CONTRA O BANCO
`context_for_webhook` (`core/tenant.py`) e as cinco instruções de
`server/routers/webhooks.py`, executadas como o webhook as executa:

* **a resolução pelo `path_token`**: acha o tenant dono e a integração dele;
  o token do outro tenant acha o outro; token inventado, tenant inativo e
  integração inativa são zero linhas;
* **`/start` válido**: o convite é achado pelo hash (nunca pelo token), não
  está expirado nem usado, é consumido (1 linha), a identidade nasce vigente
  com o `chat_id`, a auditoria leva canal e convite e **não** o `chat_id`; o
  mesmo convite relido está usado e o consumo de novo é 0 linhas;
* **expirado e usado não vinculam**: o banco diz `expired = true` para o
  vencido e `used_at` preenchido para o usado; o hash inventado e o hash do
  outro tenant ligado a este são zero linhas;
* **`chat_in_use`**: o convite do gestor com o `chat_id` do colaborador — o
  índice `messaging_identity_vigente_external_uk` recusa **nomeado**, e a
  subtransação desfaz o consumo: o convite do gestor continua inteiro;
* **a segunda adesão**: o segundo convite do mesmo colaborador com outro
  `chat_id` revoga a vigente anterior (`novo /start`), deixa exatamente uma
  vigente, e nada é apagado; e o `chat_id` antigo, agora livre, vincula o gestor.

SEXTA PARTE — O CONVITE DE ADESÃO (C4), O SQL DA ROTA CONTRA O BANCO
As oito instruções novas de `canais.py`, mais `outbox._PROVIDER_SQL`,
`_TEMPLATE_SQL` e `_ENQUEUE_SQL` (importadas pela rota, não copiadas) e o
`_REVOKE_PREVIOUS_SQL` do webhook, executadas como `POST /canais/telegram/
convites`, o `GET` e o `revogar` as executam:

* **o titular, como o usuário**: o owner vê o colaborador e o responsável
  (com o `type`, para a rota recusar grupo); o supervisor sem escopo não vê
  o colaborador (`util.can_see_employee` decidindo de verdade) — e vê o
  responsável, porque `contact_read` é `has_tenant`: quem barra o convite
  dele é o passo 1 da rota, `util.is_admin`;
* **o número**: só a coluna, pelo tenant ligado; ligado ao outro tenant, nada;
* **as quatro condições**: o bot com `public_identity`, o provedor de
  WhatsApp, o template com `nome,link`;
* **o convite anterior em aberto expira** (`expires_at = now()`, 1 linha), o
  usado e o vencido ficam como estavam, e nada é apagado;
* **o convite novo** nasce com `expires_at` a 7 dias (o default da tabela) e
  só com o hash — o token literal não está na tabela;
* **a linha da fila passa pelo gatilho** `validate_alert_template` com o
  payload `nome`/`link`, sem regra e sem ciclo; a mesma chave de idempotência
  de novo é 0 linhas; e **o gatilho recusa nomeado** o payload sem `link`
  (`Payload não cobre … link`) e o `meta_cloud` com o template em `draft`;
* **a auditoria** leva o titular e o convite — não o hash, não o número;
* **a ficha** (`_LINK_SQL`, que não seleciona `external_id` — conferido no
  texto antes de rodar) nos quatro estados: convite em aberto → vinculado →
  desvinculado pelo administrador (a linha fica, `revoked_at` preenchido, o
  convite em aberto expira junto, 1 linha) → e revogar de novo é 0 linhas
  (o 409) → e um convite novo reabre a ficha ao lado da revogação.

SÉTIMA PARTE — O ROTEAMENTO E O SENDER (C5, onda 1, metade A), CONTRA O BANCO
`outbox._TARGETS_SQL` (as duas entradas de `route`) e as doze instruções de
`sender.py`, mais o `_REVOKE_PREVIOUS_SQL` do webhook e o `_PROVIDER_SQL` do
outbox, executadas como o sender as executa — e o gatilho de verdade no meio:

* **as duas entradas de `route`**: o contato com identidade vigente traz o
  `external_id`; o revogado e o sem identidade trazem nulo; `telegram_ready`
  é o predicado de `fn_channel_readiness` — bot ativo E `channel_health` em
  `connected` pela porta `app.fn_record_channel_health`: sem medição é
  `false`, `connected` é `true`, `disconnected` volta a `false`, bot
  desligado com saúde boa é `false` — e o `external_id` continua vindo em
  todos (quem decide é `route`, e ele exige os dois); ligado ao outro tenant,
  zero linhas;
* **a re-rota recusada pelo gatilho** (o ALTO da revisão do ciclo 1): z_api
  desligada, meta_cloud ativa, template em `draft`; a linha de Telegram é
  estacionada por `_PARK_SQL`, a `_REROUTE_SQL` para meta_cloud é RECUSADA
  pelo gatilho de verdade com a frase que nomeia template e provedor (sem
  payload), a linha continua como (c1) a deixou, vai a `_DISCARD_SQL` com o
  motivo no log — e as outras linhas do lote continuam `sent`;
* **os pinos da revisão**: uma integração de canal desligada e uma `secullum`
  ativa ficam fora de `_INTEGRATIONS_SQL`; o mesmo chat_id revogado de outro
  contato não desvia o titular; `_WAITING_SQL` cai a 0 depois das marcas; o
  gatilho recusa o scrub numa `sending`; `_PARK_SQL` conta a tentativa sem
  mexer no horário e `_REROUTE_SQL` zera as tentativas; `_DISCARD_SQL` não
  conta de novo;
* **o check novo**: a linha de fila com `channel = 'telegram'` entra;
* **a espera e a reserva**: `_WAITING_SQL` conta só `pending`/`failed`
  vencidas; `_CLAIM_SQL` reserva essas E a `sending` presa há mais de 10
  minutos (com `previous_status = 'sending'`), e NÃO a `sending` fresca nem a
  agendada para o futuro — e carimba `next_attempt_at = now()`;
* **os cinco campos do template** e as integrações dos provedores de canal
  (o e-mail fica de fora; o outro tenant, zero);
* **o scrub contra o gatilho de verdade**: `sent` no convite tira `link` e
  deixa `nome`; `sent` no alerta mantém o link do painel; `discarded` (quinta
  falha) tira o link do convite; `failed` (primeira) o mantém — e o gatilho
  ainda RECUSA `payload - 'link'` numa linha `pending` (o negativo: a abertura
  é só para o estado terminal);
* **`blocked`, passo a passo**: o titular pelo chat_id (vigente e revogado; o
  inventado é zero), a revogação do webhook com a razão, a auditoria sem o
  chat_id, o WhatsApp ativo, e o re-roteamento — a MESMA linha vira `whatsapp`,
  para o número do contato, `failed`, devida já; o contato sem número devolve
  zero e a linha é descartada; e `_TARGETS_SQL` depois da revogação já não traz
  o `external_id` (o próximo ciclo degrada sozinho);
* **`alert_sent` com os quatro provedores**, pela `_LOG_SQL`, e
  `fn_delivery_by_channel` como o owner: conta por semana, canal e provedor, e
  o owner do outro tenant vê zero.

O valor de teste é uma string óbvia; nenhum segredo real passa por aqui.
"""

import hashlib
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
SAUDE = RAIZ / "backend" / "operax" / "alertas" / "saude.py"
WEBHOOK = RAIZ / "backend" / "server" / "routers" / "webhooks.py"
TENANT_PY = RAIZ / "backend" / "operax" / "core" / "tenant.py"
OUTBOX = RAIZ / "backend" / "operax" / "alertas" / "outbox.py"
SENDER = RAIZ / "backend" / "operax" / "alertas" / "sender.py"

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
# Os templates: mais um par de tenants, um owner em cada.
T_TENANT = "7ca70000-0000-0000-0000-0000000000e1"
T_OUTRO = "7ca70000-0000-0000-0000-0000000000f1"
T_OWNER = "7c000000-0000-0000-0000-0000000000e1"
T_OUTRO_OWNER = "7c000000-0000-0000-0000-0000000000f1"
T_WABA = "102030405060708"
# O bot: um tenant com os dois canais ativos, um owner, e um segundo tenant só
# para provar o recorte da saúde.
B_TENANT = "7ca70000-0000-0000-0000-000000000101"
B_OUTRO = "7ca70000-0000-0000-0000-000000000102"
B_OWNER = "7c000000-0000-0000-0000-000000000101"
B_PATH_TOKEN = "cauda-publica-de-teste-000000000"
B_WEBHOOK_URL = "https://api.exemplo.test/webhooks/telegram/" + B_PATH_TOKEN
# O webhook: um tenant com colaborador e gestor, um segundo tenant com o próprio
# bot, um tenant inativo — e os tokens do convite, que só entram como hash.
W_TENANT = "7ca70000-0000-0000-0000-000000000201"
W_OUTRO = "7ca70000-0000-0000-0000-000000000202"
W_INATIVO = "7ca70000-0000-0000-0000-000000000203"
W_COMPANY = "7ca70000-0000-0000-0000-0000000002e1"
W_UNIT = "7ca70000-0000-0000-0000-0000000002c1"
W_EMPLOYEE = "7ca70000-0000-0000-0000-0000000002b1"
W_CONTACT = "7ca70000-0000-0000-0000-00000000f201"
W_OUTRO_CONTACT = "7ca70000-0000-0000-0000-00000000f202"
W_PATH = "cauda-do-webhook-de-teste-000000"
W_PATH_OUTRO = "cauda-do-outro-tenant-0000000000"
W_PATH_INATIVO = "cauda-do-tenant-inativo-00000000"
W_PATH_ANTIGO = "cauda-da-integracao-inativa-0000"
INV_VALIDO = "7ca70000-0000-0000-0000-0000000002a1"
INV_EXPIRADO = "7ca70000-0000-0000-0000-0000000002a2"
INV_USADO = "7ca70000-0000-0000-0000-0000000002a3"
INV_GESTOR = "7ca70000-0000-0000-0000-0000000002a4"
INV_SEGUNDO = "7ca70000-0000-0000-0000-0000000002a5"
INV_OUTRO = "7ca70000-0000-0000-0000-0000000002a6"
W_CHAT1 = "987654321012"
W_CHAT2 = "987654321013"
# O convite: um tenant com colaborador (e o número dele na PII), um responsável
# pessoa e um grupo, o bot e um WhatsApp ativos, o template; um owner e um
# supervisor sem escopo; e um segundo tenant só para provar o recorte.
I_TENANT = "7ca70000-0000-0000-0000-000000000301"
I_OUTRO = "7ca70000-0000-0000-0000-000000000302"
I_OWNER = "7c000000-0000-0000-0000-000000000301"
I_SUPERVISOR = "7c000000-0000-0000-0000-000000000302"
I_COMPANY = "7ca70000-0000-0000-0000-0000000003e1"
I_UNIT = "7ca70000-0000-0000-0000-0000000003c1"
I_EMPLOYEE = "7ca70000-0000-0000-0000-0000000003b1"
I_CONTACT = "7ca70000-0000-0000-0000-00000000f301"
I_GROUP = "7ca70000-0000-0000-0000-00000000f302"
INV_ABERTO = "7ca70000-0000-0000-0000-0000000003a1"
INV_JA_USADO = "7ca70000-0000-0000-0000-0000000003a2"
INV_VENCIDO = "7ca70000-0000-0000-0000-0000000003a3"
#: O número como o RH o digitou; o E.164 que a rota manda à fila.
I_PHONE = "(11) 99999-0303"
I_E164 = "+5511999990303"
I_CHAT = "987654321303"
#: O token do convite novo — só o hash chega ao SQL; o token vai no `link`.
I_TOKEN = "convite-novo-de-teste-000000000000000000000"
I_LINK = "https://t.me/ConviteBot?start=" + I_TOKEN
# O roteamento: um tenant com bot e WhatsApp ativos, uma regra agregada com três
# contatos (aderiu, revogou, nunca aderiu), um owner; e um segundo tenant com o
# próprio owner, só para provar o recorte.
R_TENANT = "7ca70000-0000-0000-0000-000000000401"
R_OUTRO = "7ca70000-0000-0000-0000-000000000402"
R_OWNER = "7c000000-0000-0000-0000-000000000401"
R_OUTRO_OWNER = "7c000000-0000-0000-0000-000000000402"
R_COMPANY = "7ca70000-0000-0000-0000-0000000004e1"
R_UNIT = "7ca70000-0000-0000-0000-0000000004c1"
R_RULE = "7ca70000-0000-0000-0000-0000000004d1"
R_ADERIU = "7ca70000-0000-0000-0000-00000000f401"
R_REVOGOU = "7ca70000-0000-0000-0000-00000000f402"
R_SEM = "7ca70000-0000-0000-0000-00000000f403"
R_SEM_NUMERO = "7ca70000-0000-0000-0000-00000000f404"
R_BOT = "7ca70000-0000-0000-0000-0000000004b1"
R_ZAPI = "7ca70000-0000-0000-0000-0000000004b2"
R_CHAT_ADERIU = "987654321401"
R_CHAT_REVOGOU = "987654321402"
R_CHAT_SEM_NUMERO = "987654321404"
Q_TELEGRAM = "7ca70000-0000-0000-0000-0000000004a1"
Q_WHATSAPP = "7ca70000-0000-0000-0000-0000000004a2"
Q_INVITE = "7ca70000-0000-0000-0000-0000000004a3"
Q_PRESA = "7ca70000-0000-0000-0000-0000000004a4"
Q_FRESCA = "7ca70000-0000-0000-0000-0000000004a5"
Q_FUTURA = "7ca70000-0000-0000-0000-0000000004a6"
Q_INVITE_5 = "7ca70000-0000-0000-0000-0000000004a7"
Q_INVITE_1 = "7ca70000-0000-0000-0000-0000000004a8"
Q_SEM_NUMERO = "7ca70000-0000-0000-0000-0000000004a9"
Q_RECUSADA = "7ca70000-0000-0000-0000-0000000004aa"
R_META = "7ca70000-0000-0000-0000-0000000004b3"
R_UAZAPI_INATIVA = "7ca70000-0000-0000-0000-0000000004b4"
R_SECULLUM = "7ca70000-0000-0000-0000-0000000004b5"
R_INVITE_LINK = "https://t.me/RotaBot?start=token-que-nao-pode-ficar-na-fila-0000"


def _hash(token: str) -> str:
    """O que o webhook grava e procura: `sha256(token)`, nunca o token."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


#: Os tokens dos convites — só o hash chega ao SQL abaixo.
HASH_VALIDO = _hash("convite-valido-de-teste-000000000000")
HASH_EXPIRADO = _hash("convite-expirado-de-teste-0000000000")
HASH_USADO = _hash("convite-usado-de-teste-0000000000000")
HASH_GESTOR = _hash("convite-do-gestor-de-teste-000000000")
HASH_SEGUNDO = _hash("segundo-convite-de-teste-00000000000")
HASH_OUTRO = _hash("convite-do-outro-tenant-000000000000")
HASH_INVENTADO = _hash("convite-que-ninguem-gerou-00000000000")
HASH_ABERTO = _hash("convite-anterior-em-aberto-0000000000")
HASH_JA_USADO = _hash("convite-anterior-ja-usado-00000000000")
HASH_VENCIDO = _hash("convite-anterior-vencido-000000000000")
HASH_NOVO = _hash(I_TOKEN)
HASH_NOVO_2 = _hash("segundo-convite-novo-de-teste-00000000000")
HASH_NOVO_3 = _hash("terceiro-convite-novo-de-teste-0000000000")

#: Valores de teste, óbvios de propósito. Nenhum é real.
VALOR = "valor-de-teste-nao-e-real"
VALOR2 = "segundo-valor-de-teste-nao-e-real"
DESCRICAO = "descricao de teste"


def _capacidades():
    caminho = RAIZ / "backend" / "operax" / "alertas" / "capacidades.py"
    spec = importlib.util.spec_from_file_location("capacidades", caminho)
    assert spec is not None and spec.loader is not None
    capacidades = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = capacidades  # `dataclass(slots=True)` procura o módulo aqui
    spec.loader.exec_module(capacidades)
    return capacidades


def provider_list(channel: str = "whatsapp") -> str:
    """`'meta_cloud', 'z_api', 'uazapi'` (ou `'telegram'`) — como `canais.py` e
    `outbox.py` renderizam o token `{channel_providers}`, por canal."""
    return ", ".join(f"'{provider}'" for provider in _capacidades().providers_of(channel))


def whatsapp_providers() -> str:
    return provider_list("whatsapp")


def instrucoes(modulo: pathlib.Path = MODULO, channel: str = "whatsapp") -> dict[str, str]:
    """As instruções fixas do módulo, com `{channel_providers}` renderizado para
    `channel` — o WhatsApp por padrão, porque é o que os três primeiros cenários
    exercitam; a quarta parte pede as duas renderizações."""
    fonte = modulo.read_text()
    achadas = re.findall(r'^(_?[A-Z][A-Z_]*_SQL) = """(.*?)"""', fonte, re.DOTALL | re.MULTILINE)
    lista = provider_list(channel)
    return {nome: sql.replace("{channel_providers}", lista) for nome, sql in achadas}


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


CENARIO_TEMPLATES = """
begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

insert into auth.users (id, email) values
  ('{T_OWNER}',       'owner@templates'),
  ('{T_OUTRO_OWNER}', 'owner@templates-outro');

insert into app.tenant (id, slug, name) values
  ('{T_TENANT}', 'templates-teste', 'Templates'),
  ('{T_OUTRO}',  'templates-outro', 'Outro');

insert into app.tenant_member (tenant_id, user_id, role) values
  ('{T_TENANT}', '{T_OWNER}',       'owner'),
  ('{T_OUTRO}',  '{T_OUTRO_OWNER}', 'owner');

-- O primeiro no oficial, com o `waba_id` que o C2b grava em `config`; o
-- segundo num não-oficial — para o `select` da integração oficial não o achar.
insert into app.integration (tenant_id, provider, alias, config, active) values
  ('{T_TENANT}', 'meta_cloud', 'meta_cloud',
   '{"phone_number_id": "123456789012345", "waba_id": "{T_WABA}", "public_identity": "FastPark"}', true),
  ('{T_OUTRO}',  'z_api', 'z_api', '{"instance_id": "X"}', true);

-- O tenant B já tem um template aprovado, com nome na WABA.
insert into app.message_template
  (tenant_id, code, variables, body, meta_template_name, meta_status)
values
  ('{T_OUTRO}', 'deviation_summary', array['unit','occurrences'],
   'Outro: {{1}} com {{2}}.', 'outro_v1', 'approved');

-- ---------------------------------------------------------------------------
-- A integração oficial: só a ativa do provedor oficial, com o waba_id
-- ---------------------------------------------------------------------------
do $$
declare
  linha record;
  n int;
begin
  select * into linha from ({OFFICIAL}) x;
  perform pg_temp.assert_eq('a integração oficial do tenant A é achada', (linha.id is not null)::text, 'true');
  perform pg_temp.assert_eq('com o waba_id de config', linha.waba_id, '{T_WABA}');
  select count(*) into n from ({OFFICIAL_OUTRO}) x;
  perform pg_temp.assert_eq('o tenant B, no z_api, não tem integração oficial', n::text, '0');
end $$;

-- ---------------------------------------------------------------------------
-- O upsert: insert, e o gatilho de verdade
-- ---------------------------------------------------------------------------
do $$
declare
  rec record;
  falhou boolean := false;
  mensagem text;
begin
  execute $q${UPSERT_V1}$q$ into rec;
  perform pg_temp.assert_eq('insert: before é nulo', (rec.before is null)::text, 'true');
  perform pg_temp.assert_eq('insert: nasce draft', rec.meta_status, 'draft');
  perform pg_temp.assert_eq('insert: o gatilho carimbou updated_at', (rec.updated_at is not null)::text, 'true');

  -- Corpo sem {{2}}: só o upsert dentro do sub-bloco, e só o P0001 é capturado.
  -- A asserção fica FORA, para não ser engolida pelo handler.
  begin
    execute $q${UPSERT_SEM_2}$q$;
  exception when raise_exception then
    falhou := true;
    mensagem := sqlerrm;
  end;
  perform pg_temp.assert_eq('gatilho: o corpo sem {{2}} é recusado com P0001', falhou::text, 'true');
  perform pg_temp.assert_eq('gatilho: a frase é a que a rota devolve como detail', mensagem,
    'Template deviation_summary declara a variável 2 (occurrences) mas o corpo não usa {{2}}.');
  perform pg_temp.assert_eq('gatilho: a linha não mudou',
    (select body from app.message_template where tenant_id = '{T_TENANT}' and code = 'deviation_summary'),
    'FastPark: {{1}} com {{2}} ocorrencias.');
end $$;

-- ---------------------------------------------------------------------------
-- A sincronização: só grava o que mudou, e só no tenant ligado
-- ---------------------------------------------------------------------------
do $$
declare
  n int;
  codigo text;
begin
  execute $q${SYNC_APPROVED}$q$ into codigo;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('sync: approved grava 1', n::text, '1');
  perform pg_temp.assert_eq('sync: e devolve o code', codigo, 'deviation_summary');

  execute $q${SYNC_APPROVED}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('sync: o mesmo par de novo grava 0 (is distinct from)', n::text, '0');

  -- O id do tenant B no array, ligado ao tenant A: a linha dele fica intacta.
  execute $q${SYNC_CROSS}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('sync: com o id do outro tenant no array, só o próprio muda', n::text, '1');
  perform pg_temp.assert_eq('sync: o tenant B continua approved',
    (select meta_status from app.message_template where tenant_id = '{T_OUTRO}'), 'approved');
  perform pg_temp.assert_eq('sync: e o tenant A foi a pending',
    (select meta_status from app.message_template where tenant_id = '{T_TENANT}' and code = 'deviation_summary'),
    'pending');

  execute $q${SYNC_APPROVED}$q$;
end $$;

-- ---------------------------------------------------------------------------
-- Trocar o nome na Meta volta a draft; manter preserva
-- ---------------------------------------------------------------------------
do $$
declare
  rec record;
  n int;
begin
  execute $q${UPSERT_V1}$q$ into rec;
  perform pg_temp.assert_eq('mesmo nome: update, before vem preenchido', (rec.before ->> 'meta_status'), 'approved');
  perform pg_temp.assert_eq('mesmo nome: meta_status preservado', rec.meta_status, 'approved');

  execute $q${SYNC_REJECTED}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('sync: rejected com razão grava 1', n::text, '1');
  execute $q${UPSERT_V1}$q$ into rec;
  perform pg_temp.assert_eq('mesmo nome: rejected preservado', rec.meta_status, 'rejected');
  perform pg_temp.assert_eq('mesmo nome: a razão preservada', rec.meta_rejection, 'INVALID_FORMAT');

  -- Só a razão muda, de valor para nulo, com o mesmo status. `<>` diria
  -- "nada mudou" (nulo não é diferente de nada); `is distinct from` grava.
  execute $q${SYNC_REJECTED_SEM_RAZAO}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('sync: mesmo status e razão indo a nulo grava 1 (null-safe)', n::text, '1');
  execute $q${SYNC_REJECTED_SEM_RAZAO}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('sync: e de novo grava 0', n::text, '0');
  perform pg_temp.assert_eq('sync: a razão foi limpa de fato',
    coalesce((select meta_rejection from app.message_template where tenant_id = '{T_TENANT}' and code = 'deviation_summary'), '(nulo)'),
    '(nulo)');

  execute $q${UPSERT_V2}$q$ into rec;
  perform pg_temp.assert_eq('nome novo: volta a draft', rec.meta_status, 'draft');
  perform pg_temp.assert_eq('nome novo: a razão é limpa', coalesce(rec.meta_rejection, '(nulo)'), '(nulo)');
  perform pg_temp.assert_eq('nome novo: before traz a linha anterior', (rec.before ->> 'meta_template_name'), 'deviation_summary_v1');
  perform pg_temp.assert_eq('nome novo: e o status anterior', (rec.before ->> 'meta_status'), 'rejected');

  -- A corrida: o veredito da WABA sobre o nome velho chega depois do PUT.
  execute $q${SYNC_NOME_VELHO}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('sync: veredito do nome velho depois do rename grava 0', n::text, '0');
  perform pg_temp.assert_eq('sync: e a linha segue draft, como o PUT a deixou',
    (select meta_status from app.message_template where tenant_id = '{T_TENANT}' and code = 'deviation_summary'),
    'draft');

  execute $q${UPSERT_SEM_NOME}$q$ into rec;
  perform pg_temp.assert_eq('nome removido (nulo): também é distinto, volta a draft', rec.meta_status, 'draft');
  perform pg_temp.assert_eq('uma linha só por (tenant, code, language)',
    (select count(*) from app.message_template where tenant_id = '{T_TENANT}' and code = 'deviation_summary')::text, '1');
end $$;

-- ---------------------------------------------------------------------------
-- Os nomeados: com nome, ativo ou não; sem nome, não
-- ---------------------------------------------------------------------------
do $$
declare
  rec record;
  codigos text;
begin
  execute $q${UPSERT_INATIVO}$q$ into rec;
  perform pg_temp.assert_eq('inativo com nome: gravado inativo', rec.active::text, 'false');
  select string_agg(code, ',' order by code) into codigos from ({NAMED}) x;
  perform pg_temp.assert_eq('nomeados: o inativo entra, o sem nome não, o do tenant B não',
    codigos, 'deviation_inactive');
end $$;

-- ---------------------------------------------------------------------------
-- A auditoria: as duas formas da rota
-- ---------------------------------------------------------------------------
do $$
declare
  trilha record;
begin
  execute $q${AUDIT_SYNC}$q$;
  execute $q${AUDIT_INSERT}$q$;
  select * into trilha from app.audit_log
   where tenant_id = '{T_TENANT}' and entity = 'message_template' and entity_id is null;
  perform pg_temp.assert_eq('auditoria da sync: resumo em depois', (trilha.depois ->> 'meta_total'), '1');
  perform pg_temp.assert_eq('auditoria da sync: action update', trilha.action, 'update');
  perform pg_temp.assert_eq('auditoria do insert: entity_id é o id',
    (select count(*) from app.audit_log where tenant_id = '{T_TENANT}' and entity = 'message_template'
       and action = 'insert' and entity_id is not null)::text, '1');
end $$;

-- ---------------------------------------------------------------------------
-- A leitura sob RLS: o owner do tenant A vê o próprio e não vê o do B
-- ---------------------------------------------------------------------------
do $$
declare
  codigos_a text;
  n_b int;
begin
  set local role authenticated;
  set local request.jwt.claim.sub = '{T_OWNER}';
  select string_agg(code, ',' order by code) into codigos_a from ({TEMPLATES}) x;
  select count(*) into n_b from ({TEMPLATES_OUTRO}) x;
  reset role;
  perform pg_temp.assert_eq('RLS: o owner de A vê os dois de A (o inativo inclusive)', codigos_a,
    'deviation_inactive,deviation_summary');
  perform pg_temp.assert_eq('RLS: ligado ao tenant B, o owner de A vê zero', n_b::text, '0');

  set local role authenticated;
  set local request.jwt.claim.sub = '{T_OUTRO_OWNER}';
  select count(*) into n_b from ({TEMPLATES_OUTRO}) x;
  reset role;
  perform pg_temp.assert_eq('RLS: e o owner de B vê o dele', n_b::text, '1');
end $$;

rollback;
"""


CENARIO_TELEGRAM = """
begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

insert into auth.users (id, email) values ('{B_OWNER}', 'owner@bot');
insert into app.tenant (id, slug, name) values
  ('{B_TENANT}', 'bot-teste', 'Bot'),
  ('{B_OUTRO}',  'bot-outro', 'Outro');
insert into app.tenant_member (tenant_id, user_id, role) values ('{B_TENANT}', '{B_OWNER}', 'owner');

-- Os dois canais ativos no mesmo tenant: é a linha 1 da SPEC §2.2, inserida.
-- `alias = provider`, como a rota grava, para o upsert dela encontrar a linha.
insert into app.integration (tenant_id, provider, alias, config, active) values
  ('{B_TENANT}', 'meta_cloud', 'meta_cloud',
   '{"phone_number_id": "123456789012345", "waba_id": "102030405060708", "public_identity": "FastPark"}', true),
  ('{B_TENANT}', 'telegram', 'telegram', '{"public_identity": "@FastParkAlertasBot"}', true);

-- Um ponteiro por integração: `configured` exige o `join` com o cofre.
do $$
declare n int;
begin
  execute $q$with x as ({CREATE_META_TOKEN}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('ponteiro do meta_cloud gravado', n::text, '1');
  execute $q$with x as ({CREATE_BOT_TOKEN}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('ponteiro do bot gravado', n::text, '1');
end $$;

-- ---------------------------------------------------------------------------
-- As duas linhas da função, como o owner; o bot nasce sem saúde e não pronto
-- ---------------------------------------------------------------------------
do $$
declare
  n int;
  provedores text;
  bot record;
  outro int;
begin
  set local role authenticated;
  set local request.jwt.claim.sub = '{B_OWNER}';
  select count(*), string_agg(provider, ',' order by provider) into n, provedores from ({READINESS}) x;
  select * into bot from ({READINESS}) x where provider = 'telegram';
  select count(*) into outro from ({READINESS_OUTRO}) x;
  reset role;

  perform pg_temp.assert_eq('a função devolve UMA linha por canal ativo', n::text, '2');
  perform pg_temp.assert_eq('e são o meta_cloud e o bot, lado a lado', provedores, 'meta_cloud,telegram');
  perform pg_temp.assert_eq('o bot nasce sem medição', coalesce(bot.health_status, '(nulo)'), '(nulo)');
  perform pg_temp.assert_eq('e sem medição NÃO está pronto', bot.ready::text, 'false');
  perform pg_temp.assert_eq('o bot não tem template a aprovar', bot.templates_total::text || '/' || bot.rules_blocked::text, '0/0');
  perform pg_temp.assert_eq('ligada ao outro tenant, a leitura não devolve nada', outro::text, '0');
end $$;

-- ---------------------------------------------------------------------------
-- O estado do bot: só as três chaves públicas; o webhook entra sem apagar o resto
-- ---------------------------------------------------------------------------
do $$
declare
  estado json;
  chaves text;
  n int;
begin
  select row_to_json(x) into estado from ({STATE}) x;
  perform pg_temp.assert_eq('o estado vê o bot ativo', (estado is not null)::text, 'true');
  select string_agg(k, ',' order by k) into chaves from json_object_keys(estado) k;
  perform pg_temp.assert_eq('e traz só as colunas do contrato', chaves,
    'health_checked_at,health_detail,id,public_identity,webhook_path_token,webhook_url');
  perform pg_temp.assert_eq('o @username é o public_identity', estado ->> 'public_identity', '@FastParkAlertasBot');
  perform pg_temp.assert_eq('sem webhook ainda', coalesce(estado ->> 'webhook_url', '(nulo)'), '(nulo)');
  perform pg_temp.assert_eq('sem saúde ainda', coalesce(estado ->> 'health_detail', '(nulo)'), '(nulo)');

  select count(*) into n from ({STATE_OUTRO}) x;
  perform pg_temp.assert_eq('ligado ao outro tenant, o estado não vê o bot', n::text, '0');

  execute $q${WEBHOOK_PATCH}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('o patch do webhook alcança a integração', n::text, '1');
  select row_to_json(x) into estado from ({STATE}) x;
  perform pg_temp.assert_eq('o webhook_url ficou', estado ->> 'webhook_url', '{B_WEBHOOK_URL}');
  perform pg_temp.assert_eq('o path_token ficou', estado ->> 'webhook_path_token', '{B_PATH_TOKEN}');
  perform pg_temp.assert_eq('e o public_identity NÃO foi apagado pelo patch', estado ->> 'public_identity', '@FastParkAlertasBot');
end $$;

-- ---------------------------------------------------------------------------
-- A saúde pela porta única — e a regra da §7 pela instrução da rota
-- ---------------------------------------------------------------------------
do $$
declare
  bot record;
  primeira timestamptz;
  n int;
  estado json;
begin
  execute $q${HEALTH_CONNECTED}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('a medição alcança a integração do tenant', n::text, '1');

  set local role authenticated;
  set local request.jwt.claim.sub = '{B_OWNER}';
  select * into bot from ({READINESS}) x where provider = 'telegram';
  reset role;
  perform pg_temp.assert_eq('connected: o bot está pronto', bot.ready::text, 'true');
  perform pg_temp.assert_eq('e a função diz connected', bot.health_status, 'connected');

  select row_to_json(x) into estado from ({STATE}) x;
  perform pg_temp.assert_eq('o estado traz o detail — a frase da rota', estado ->> 'health_detail', 'webhook registrado');
  perform pg_temp.assert_eq('e a idade da medição', (estado ->> 'health_checked_at' is not null)::text, 'true');

  -- A mesma medição de novo não move o status_changed_at (regra da §7). Como
  -- no `86`: `now()` é um só na transação inteira, então a linha é recuada uma
  -- hora à mão para a diferença entre "ficou" e "moveu" ser visível.
  update app.channel_health
     set status_changed_at = now() - interval '1 hour', checked_at = now() - interval '1 hour'
   where tenant_id = '{B_TENANT}';
  primeira := now() - interval '1 hour';
  execute $q${HEALTH_CONNECTED}$q$;
  set local role authenticated;
  set local request.jwt.claim.sub = '{B_OWNER}';
  select * into bot from ({READINESS}) x where provider = 'telegram';
  reset role;
  perform pg_temp.assert_eq('a mesma medição de novo não move health_changed_at',
    (bot.health_changed_at = primeira)::text, 'true');
  perform pg_temp.assert_eq('mas checked_at avança',
    (select (checked_at = now())::text from app.channel_health where tenant_id = '{B_TENANT}'), 'true');

  -- Ligada ao OUTRO tenant, a integração deste não é alcançada: zero linhas,
  -- função nunca avaliada, saúde intacta.
  execute $q${HEALTH_DISCONNECTED_OUTRO}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('outro tenant: a medição não alcança o bot', n::text, '0');
  perform pg_temp.assert_eq('outro tenant: a saúde continua connected',
    (select status from app.channel_health where tenant_id = '{B_TENANT}'), 'connected');

  -- Uma medição diferente move.
  execute $q${HEALTH_DISCONNECTED}$q$;
  set local role authenticated;
  set local request.jwt.claim.sub = '{B_OWNER}';
  select * into bot from ({READINESS}) x where provider = 'telegram';
  reset role;
  perform pg_temp.assert_eq('disconnected: o bot deixa de estar pronto', bot.ready::text, 'false');
  perform pg_temp.assert_eq('e health_changed_at moveu para agora', (bot.health_changed_at = now())::text, 'true');
  perform pg_temp.assert_eq('o detail é a frase da rota com o código, nada do provedor',
    (select detail from app.channel_health where tenant_id = '{B_TENANT}'), 'setWebhook recusado: unauthorized');
end $$;

-- ---------------------------------------------------------------------------
-- Linha 1 da §2.2 pela porta da credencial: cada canal desliga só o seu
-- ---------------------------------------------------------------------------
do $$
declare
  desligado text;
  v uuid;
begin
  perform pg_temp.assert_eq('status por canal: whatsapp → meta_cloud',
    (select provider from ({STATUS_WHATSAPP}) x), 'meta_cloud');
  perform pg_temp.assert_eq('status por canal: telegram → o bot',
    (select provider from ({STATUS_TELEGRAM}) x), 'telegram');

  execute $q$with x as ({DEACTIVATE_TELEGRAM}) select string_agg(provider, ',') from x$q$ into desligado;
  perform pg_temp.assert_eq('a desativação do canal telegram devolve SÓ o bot', desligado, 'telegram');
  perform pg_temp.assert_eq('e o meta_cloud CONTINUA ativo',
    (select active::text from app.integration where tenant_id = '{B_TENANT}' and provider = 'meta_cloud'), 'true');
  perform pg_temp.assert_eq('o bot ficou inativo',
    (select active::text from app.integration where tenant_id = '{B_TENANT}' and provider = 'telegram'), 'false');
  perform pg_temp.assert_eq('status do canal telegram: nada',
    (select count(*) from ({STATUS_TELEGRAM}) x)::text, '0');
  perform pg_temp.assert_eq('status do canal whatsapp: intacto',
    (select provider from ({STATUS_WHATSAPP}) x), 'meta_cloud');

  -- O upsert da rota religa o bot (uma linha só, pelo alias).
  execute $q$with x as ({UPSERT_BOT}) select id from x$q$ into v;
  perform pg_temp.assert_eq('o upsert religa o bot sem segunda linha',
    (select count(*) from app.integration where tenant_id = '{B_TENANT}' and provider = 'telegram')::text, '1');

  execute $q$with x as ({DEACTIVATE_WHATSAPP}) select string_agg(provider, ',') from x$q$ into desligado;
  perform pg_temp.assert_eq('a desativação do canal whatsapp devolve SÓ o meta_cloud', desligado, 'meta_cloud');
  perform pg_temp.assert_eq('e o bot CONTINUA ativo',
    (select active::text from app.integration where tenant_id = '{B_TENANT}' and provider = 'telegram'), 'true');
end $$;

rollback;
"""


CENARIO_WEBHOOK = """
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
    raise exception 'FALHA [%]: o valor apareceu', rotulo;
  end if;
  raise notice '  ok  %', rotulo;
end $$;

insert into app.tenant (id, slug, name) values
  ('{W_TENANT}',  'webhook-teste',   'Webhook'),
  ('{W_OUTRO}',   'webhook-outro',   'Outro'),
  ('{W_INATIVO}', 'webhook-inativo', 'Inativo');
update app.tenant set active = false where id = '{W_INATIVO}';

insert into app.company (id, tenant_id, legal_name) values
  ('{W_COMPANY}', '{W_TENANT}', 'Empresa Webhook LTDA');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('{W_UNIT}', '{W_TENANT}', '{W_COMPANY}', 'WH-1', 'Unidade Webhook');
insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('{W_EMPLOYEE}', '{W_TENANT}', '{W_COMPANY}', '{W_UNIT}', 'Colab Webhook');
insert into app.contact (id, tenant_id, name, type, whatsapp) values
  ('{W_CONTACT}',       '{W_TENANT}', 'Gestor Webhook', 'person', '+5511999990202'),
  ('{W_OUTRO_CONTACT}', '{W_OUTRO}',  'Gestor Outro',   'person', '+5511999990203');

-- Quatro bots: o do tenant, o do outro, o de um tenant inativo, e um inativo
-- do próprio tenant (o `alias` diferente é o que o índice irmão permite).
insert into app.integration (tenant_id, provider, alias, config, active) values
  ('{W_TENANT}',  'telegram', 'telegram',
   '{"public_identity": "@WebhookBot", "webhook_path_token": "{W_PATH}"}', true),
  ('{W_OUTRO}',   'telegram', 'telegram',
   '{"public_identity": "@OutroBot", "webhook_path_token": "{W_PATH_OUTRO}"}', true),
  ('{W_INATIVO}', 'telegram', 'telegram',
   '{"webhook_path_token": "{W_PATH_INATIVO}"}', true),
  ('{W_TENANT}',  'telegram', 'antigo',
   '{"webhook_path_token": "{W_PATH_ANTIGO}"}', false);

-- Os convites. Só o hash: o token nunca passa por aqui.
insert into app.messaging_invite (id, tenant_id, channel, employee_id, contact_id, token_hash, expires_at, used_at)
values
  ('{INV_VALIDO}',   '{W_TENANT}', 'telegram', '{W_EMPLOYEE}', null, '{HASH_VALIDO}',   now() + interval '7 days', null),
  ('{INV_EXPIRADO}', '{W_TENANT}', 'telegram', '{W_EMPLOYEE}', null, '{HASH_EXPIRADO}', now() - interval '1 day',  null),
  ('{INV_USADO}',    '{W_TENANT}', 'telegram', '{W_EMPLOYEE}', null, '{HASH_USADO}',    now() + interval '7 days', now() - interval '1 hour'),
  ('{INV_GESTOR}',   '{W_TENANT}', 'telegram', null, '{W_CONTACT}',  '{HASH_GESTOR}',   now() + interval '7 days', null),
  ('{INV_SEGUNDO}',  '{W_TENANT}', 'telegram', '{W_EMPLOYEE}', null, '{HASH_SEGUNDO}',  now() + interval '7 days', null),
  ('{INV_OUTRO}',    '{W_OUTRO}',  'telegram', null, '{W_OUTRO_CONTACT}', '{HASH_OUTRO}', now() + interval '7 days', null);

-- ---------------------------------------------------------------------------
-- context_for_webhook: o path_token acha o tenant dono, e só ele
-- ---------------------------------------------------------------------------
do $$
declare
  r record;
  n int;
begin
  select * into r from ({RESOLVE}) x;
  perform pg_temp.assert_eq('o path_token acha o tenant dono', r.tenant_id::text, '{W_TENANT}');
  perform pg_temp.assert_eq('e a integração ativa dele', r.id::text,
    (select id::text from app.integration where tenant_id = '{W_TENANT}' and alias = 'telegram'));
  select count(*) into n from ({RESOLVE}) x;
  perform pg_temp.assert_eq('uma linha só', n::text, '1');

  select * into r from ({RESOLVE_OUTRO}) x;
  perform pg_temp.assert_eq('o token do outro tenant acha o outro', r.tenant_id::text, '{W_OUTRO}');

  select count(*) into n from ({RESOLVE_INVENTADO}) x;
  perform pg_temp.assert_eq('token inventado: zero linhas', n::text, '0');
  select count(*) into n from ({RESOLVE_INATIVO}) x;
  perform pg_temp.assert_eq('token de tenant inativo: zero linhas', n::text, '0');
  select count(*) into n from ({RESOLVE_ANTIGO}) x;
  perform pg_temp.assert_eq('token de integração inativa: zero linhas', n::text, '0');
end $$;

-- ---------------------------------------------------------------------------
-- /start válido: acha pelo hash, consome, vincula, audita sem chat_id
-- ---------------------------------------------------------------------------
do $$
declare
  inv record;
  n int;
  trilha record;
begin
  select * into inv from ({INVITE_VALIDO}) x;
  perform pg_temp.assert_eq('o convite válido é achado pelo hash', inv.id::text, '{INV_VALIDO}');
  perform pg_temp.assert_eq('não expirado', inv.expired::text, 'false');
  perform pg_temp.assert_eq('não usado', (inv.used_at is null)::text, 'true');
  perform pg_temp.assert_eq('titular: o colaborador', inv.employee_id::text, '{W_EMPLOYEE}');

  execute $q${CONSUME_VALIDO}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('consumido: 1 linha', n::text, '1');

  execute $q$with x as ({REVOKE_EMPLOYEE}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('primeira adesão: nada a revogar', n::text, '0');

  execute $q${INSERT_EMPLOYEE_CHAT1}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('a identidade entrou', n::text, '1');
  perform pg_temp.assert_eq('e nasceu vigente, com o chat_id',
    (select count(*) from app.messaging_identity
      where tenant_id = '{W_TENANT}' and employee_id = '{W_EMPLOYEE}'
        and revoked_at is null and external_id = '{W_CHAT1}')::text, '1');

  execute $q${AUDIT_EMPLOYEE_CHAT1}$q$;
  select * into trilha from app.audit_log
   where tenant_id = '{W_TENANT}' and entity = 'messaging_identity';
  perform pg_temp.assert_eq('auditoria: action insert', trilha.action, 'insert');
  perform pg_temp.assert_eq('auditoria: sem usuário (quem agiu foi o titular, pelo bot)',
    (trilha.user_id is null)::text, 'true');
  perform pg_temp.assert_eq('auditoria: o convite', trilha.depois ->> 'invite_id', '{INV_VALIDO}');
  perform pg_temp.assert_eq('auditoria: o canal', trilha.depois ->> 'channel', 'telegram');
  perform pg_temp.assert_eq('auditoria: entity_id é a identidade nova', trilha.entity_id,
    (select id::text from app.messaging_identity where tenant_id = '{W_TENANT}' and external_id = '{W_CHAT1}'));
  perform pg_temp.assert_not_in('auditoria: SEM o chat_id',
    coalesce(trilha.depois::text, '') || coalesce(trilha.antes::text, '') || coalesce(trilha.entity_id, ''),
    '{W_CHAT1}');

  -- O mesmo link, clicado de novo: o banco diz "usado", e o consumo é 0.
  select * into inv from ({INVITE_VALIDO}) x;
  perform pg_temp.assert_eq('relido: agora está usado', (inv.used_at is not null)::text, 'true');
  execute $q${CONSUME_VALIDO}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('consumir de novo: 0 linhas (used_at is null no where)', n::text, '0');
end $$;

-- ---------------------------------------------------------------------------
-- Expirado e usado: o veredito do banco; inventado e de outro tenant: nada
-- ---------------------------------------------------------------------------
do $$
declare
  inv record;
  n int;
begin
  select * into inv from ({INVITE_EXPIRADO}) x;
  perform pg_temp.assert_eq('expirado: o banco diz expired', inv.expired::text, 'true');
  perform pg_temp.assert_eq('expirado: e não está usado', (inv.used_at is null)::text, 'true');

  select * into inv from ({INVITE_USADO}) x;
  perform pg_temp.assert_eq('usado: used_at preenchido', (inv.used_at is not null)::text, 'true');
  perform pg_temp.assert_eq('usado: não expirou', inv.expired::text, 'false');

  select count(*) into n from ({INVITE_INVENTADO}) x;
  perform pg_temp.assert_eq('hash inventado: zero linhas', n::text, '0');
  select count(*) into n from ({INVITE_OUTRO_LIGADO_A_ESTE}) x;
  perform pg_temp.assert_eq('hash do outro tenant, ligado a este: zero linhas', n::text, '0');
  select count(*) into n from ({INVITE_OUTRO}) x;
  perform pg_temp.assert_eq('e ligado ao outro, uma', n::text, '1');

  perform pg_temp.assert_eq('nenhuma identidade além da primeira',
    (select count(*) from app.messaging_identity where tenant_id = '{W_TENANT}')::text, '1');
end $$;

-- ---------------------------------------------------------------------------
-- chat_in_use: o índice recusa nomeado, e a subtransação desfaz o consumo
-- ---------------------------------------------------------------------------
do $$
declare
  falhou boolean := false;
  nome text;
  n int;
begin
  begin
    execute $q${CONSUME_GESTOR}$q$;
    get diagnostics n = row_count;
    perform pg_temp.assert_eq('chat_in_use: o consumo aconteceu dentro da transação', n::text, '1');
    execute $q$with x as ({REVOKE_CONTACT}) select count(*) from x$q$ into n;
    execute $q${INSERT_CONTACT_CHAT1}$q$;
    raise exception 'FALHA [chat_in_use]: o mesmo chat_id vigente entrou para duas pessoas';
  exception when unique_violation then
    falhou := true;
    get stacked diagnostics nome = constraint_name;
  end;
  perform pg_temp.assert_eq('chat_in_use: o índice recusou', falhou::text, 'true');
  perform pg_temp.assert_eq('e é o índice do external_id vigente', nome,
    'messaging_identity_vigente_external_uk');
  perform pg_temp.assert_eq('chat_in_use: o convite do gestor NÃO foi consumido',
    (select (used_at is null)::text from app.messaging_invite where id = '{INV_GESTOR}'), 'true');
  perform pg_temp.assert_eq('chat_in_use: o gestor segue sem identidade',
    (select count(*) from app.messaging_identity where contact_id = '{W_CONTACT}')::text, '0');
end $$;

-- ---------------------------------------------------------------------------
-- Segunda adesão: a anterior revogada, uma vigente só, nada apagado
-- ---------------------------------------------------------------------------
do $$
declare
  inv record;
  n int;
  antiga record;
begin
  select * into inv from ({INVITE_SEGUNDO}) x;
  perform pg_temp.assert_eq('segundo convite: válido', (inv.expired or inv.used_at is not null)::text, 'false');
  execute $q${CONSUME_SEGUNDO}$q$;
  execute $q$with x as ({REVOKE_EMPLOYEE}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('segunda adesão: a vigente anterior foi revogada', n::text, '1');
  execute $q${INSERT_EMPLOYEE_CHAT2}$q$;

  perform pg_temp.assert_eq('exatamente UMA vigente para o colaborador',
    (select count(*) from app.messaging_identity
      where tenant_id = '{W_TENANT}' and employee_id = '{W_EMPLOYEE}' and revoked_at is null)::text, '1');
  perform pg_temp.assert_eq('e é a do chat novo',
    (select external_id from app.messaging_identity
      where tenant_id = '{W_TENANT}' and employee_id = '{W_EMPLOYEE}' and revoked_at is null), '{W_CHAT2}');
  select * into antiga from app.messaging_identity
   where tenant_id = '{W_TENANT}' and employee_id = '{W_EMPLOYEE}' and external_id = '{W_CHAT1}';
  perform pg_temp.assert_eq('a antiga ficou (nada é apagado)', (antiga.id is not null)::text, 'true');
  perform pg_temp.assert_eq('revogada', (antiga.revoked_at is not null)::text, 'true');
  perform pg_temp.assert_eq('pelo motivo do webhook', antiga.revoked_reason, 'novo /start');
  perform pg_temp.assert_eq('duas linhas na história do colaborador',
    (select count(*) from app.messaging_identity where employee_id = '{W_EMPLOYEE}')::text, '2');

  -- O chat antigo ficou livre: agora o gestor vincula com ele.
  execute $q${CONSUME_GESTOR}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('o convite do gestor, intacto, agora é consumido', n::text, '1');
  execute $q$with x as ({REVOKE_CONTACT}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('gestor: nada a revogar', n::text, '0');
  execute $q${INSERT_CONTACT_CHAT1}$q$;
  perform pg_temp.assert_eq('o chat_id liberado pela revogação vincula o gestor',
    (select count(*) from app.messaging_identity
      where contact_id = '{W_CONTACT}' and external_id = '{W_CHAT1}' and revoked_at is null)::text, '1');
  perform pg_temp.assert_eq('três identidades no tenant, duas vigentes',
    (select count(*) || '/' || count(*) filter (where revoked_at is null)
       from app.messaging_identity where tenant_id = '{W_TENANT}'), '3/2');
end $$;

rollback;
"""


CENARIO_CONVITE = """
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
    raise exception 'FALHA [%]: o valor apareceu', rotulo;
  end if;
  raise notice '  ok  %', rotulo;
end $$;

insert into auth.users (id, email) values
  ('{I_OWNER}',      'owner@convite'),
  ('{I_SUPERVISOR}', 'supervisor@convite');

insert into app.tenant (id, slug, name) values
  ('{I_TENANT}', 'convite-teste', 'Convite'),
  ('{I_OUTRO}',  'convite-outro', 'Outro');

-- O owner vê tudo; o supervisor não tem linha em user_scope, então não vê nada.
insert into app.tenant_member (tenant_id, user_id, role) values
  ('{I_TENANT}', '{I_OWNER}',      'owner'),
  ('{I_TENANT}', '{I_SUPERVISOR}', 'unit_supervisor');

insert into app.company (id, tenant_id, legal_name) values
  ('{I_COMPANY}', '{I_TENANT}', 'Empresa Convite LTDA');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('{I_UNIT}', '{I_TENANT}', '{I_COMPANY}', 'CV-1', 'Unidade Convite');
insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('{I_EMPLOYEE}', '{I_TENANT}', '{I_COMPANY}', '{I_UNIT}', 'Colab Convite Silva');
insert into app.employee_pii (employee_id, tenant_id, cpf, phone) values
  ('{I_EMPLOYEE}', '{I_TENANT}', '12345678901', '{I_PHONE}');
insert into app.contact (id, tenant_id, name, type, whatsapp) values
  ('{I_CONTACT}', '{I_TENANT}', 'Gestora Convite', 'person',         '+5511999990304'),
  ('{I_GROUP}',   '{I_TENANT}', 'Grupo da Unidade', 'whatsapp_group', '+5511999990305');

-- As quatro condições: o bot com identidade pública, um WhatsApp ativo (não
-- oficial: o gatilho não exige aprovação), e o template com nome e link.
insert into app.integration (tenant_id, provider, alias, config, active) values
  ('{I_TENANT}', 'telegram', 'telegram', '{"public_identity": "@ConviteBot"}', true),
  ('{I_TENANT}', 'z_api',    'z_api',    '{"instance_id": "X"}',               true);
insert into app.message_template (tenant_id, code, variables, body) values
  ('{I_TENANT}', 'telegram_invite', array['nome','link'],
   'Olá {{1}}, para receber seus avisos pelo Telegram abra {{2}}.');

-- Três convites anteriores do colaborador: um em aberto, um já usado, um vencido.
insert into app.messaging_invite (id, tenant_id, channel, employee_id, token_hash, expires_at, used_at) values
  ('{INV_ABERTO}',   '{I_TENANT}', 'telegram', '{I_EMPLOYEE}', '{HASH_ABERTO}',   now() + interval '3 days', null),
  ('{INV_JA_USADO}', '{I_TENANT}', 'telegram', '{I_EMPLOYEE}', '{HASH_JA_USADO}', now() + interval '3 days', now() - interval '1 day'),
  ('{INV_VENCIDO}',  '{I_TENANT}', 'telegram', '{I_EMPLOYEE}', '{HASH_VENCIDO}',  now() - interval '1 day',  null);

-- ---------------------------------------------------------------------------
-- Passo 2, como o usuário: o titular é visível a quem pede
-- ---------------------------------------------------------------------------
do $$
declare
  r record;
  n int;
begin
  set local role authenticated;
  set local request.jwt.claim.sub = '{I_OWNER}';
  select * into r from ({VISIBLE_EMPLOYEE}) x;
  perform pg_temp.assert_eq('owner: vê o colaborador', r.name, 'Colab Convite Silva');
  select * into r from ({VISIBLE_CONTACT}) x;
  perform pg_temp.assert_eq('owner: vê o responsável, com o type', r.name || '/' || r.type, 'Gestora Convite/person');
  select * into r from ({VISIBLE_GROUP}) x;
  perform pg_temp.assert_eq('owner: o grupo vem com o type (a rota é quem recusa)', r.type, 'whatsapp_group');
  reset role;

  set local role authenticated;
  set local request.jwt.claim.sub = '{I_SUPERVISOR}';
  select count(*) into n from ({VISIBLE_EMPLOYEE}) x;
  perform pg_temp.assert_eq('supervisor sem escopo: não vê o colaborador (404 da rota)', n::text, '0');
  select count(*) into n from ({VISIBLE_CONTACT}) x;
  perform pg_temp.assert_eq('supervisor: vê o responsável (contact_read é has_tenant; quem barra o convite é o passo 1, is_admin)', n::text, '1');
  reset role;
end $$;

-- ---------------------------------------------------------------------------
-- Passos 3 e 4: o número e as quatro condições, pelo tenant ligado
-- ---------------------------------------------------------------------------
do $$
declare
  r record;
  n int;
  chaves text;
begin
  select * into r from ({EMPLOYEE_PHONE}) x;
  perform pg_temp.assert_eq('o número do colaborador, como o RH digitou', r.phone, '{I_PHONE}');
  select string_agg(k, ',') into chaves from json_object_keys(row_to_json(r)) k;
  perform pg_temp.assert_eq('e só a coluna do número — nada mais da PII', chaves, 'phone');
  select * into r from ({CONTACT_PHONE}) x;
  perform pg_temp.assert_eq('o WhatsApp do responsável', r.phone, '+5511999990304');
  select count(*) into n from ({EMPLOYEE_PHONE_OUTRO}) x;
  perform pg_temp.assert_eq('ligado ao outro tenant: zero linhas', n::text, '0');

  select * into r from ({BOT_STATE}) x;
  perform pg_temp.assert_eq('o bot ativo com identidade pública', r.public_identity, '@ConviteBot');
  select * into r from ({PROVIDER}) x;
  perform pg_temp.assert_eq('o provedor de WhatsApp ativo', r.provider, 'z_api');
  select * into r from ({TEMPLATE}) x;
  perform pg_temp.assert_eq('o template telegram_invite com nome e link',
    array_to_string(r.variables, ','), 'nome,link');
end $$;

-- ---------------------------------------------------------------------------
-- Passo 5: o anterior em aberto expira; o novo entra só com o hash
-- ---------------------------------------------------------------------------
do $$
declare
  n int;
  novo record;
  anterior record;
begin
  execute $q$with x as ({EXPIRE_OUTRO}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('expirar ligado ao outro tenant: zero linhas', n::text, '0');

  execute $q$with x as ({EXPIRE_EMPLOYEE}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('expirar: exatamente o convite em aberto (1 linha)', n::text, '1');
  select * into anterior from app.messaging_invite where id = '{INV_ABERTO}';
  perform pg_temp.assert_eq('o em aberto agora está vencido', (anterior.expires_at <= now())::text, 'true');
  perform pg_temp.assert_eq('e continua não usado', (anterior.used_at is null)::text, 'true');
  select * into anterior from app.messaging_invite where id = '{INV_JA_USADO}';
  perform pg_temp.assert_eq('o já usado ficou como estava (validade intacta)', (anterior.expires_at > now())::text, 'true');
  select * into anterior from app.messaging_invite where id = '{INV_VENCIDO}';
  perform pg_temp.assert_eq('o vencido ficou como estava', (anterior.expires_at < now() - interval '23 hours')::text, 'true');
  perform pg_temp.assert_eq('nada foi apagado: os três continuam lá',
    (select count(*) from app.messaging_invite where employee_id = '{I_EMPLOYEE}')::text, '3');

  execute $q${INSERT_INVITE}$q$ into novo;
  perform pg_temp.assert_eq('o convite novo entrou', (novo.id is not null)::text, 'true');
  perform pg_temp.assert_eq('com validade de 7 dias (default da tabela)',
    (novo.expires_at between now() + interval '6 days 23 hours' and now() + interval '7 days 1 minute')::text, 'true');
  perform pg_temp.assert_eq('e ligado ao colaborador',
    (select employee_id::text from app.messaging_invite where id = novo.id), '{I_EMPLOYEE}');
  perform pg_temp.assert_eq('o que está na tabela é o hash',
    (select token_hash from app.messaging_invite where id = novo.id), '{HASH_NOVO}');
  perform pg_temp.assert_not_in('o token literal não está na tabela',
    (select string_agg(token_hash, ',') from app.messaging_invite), '{I_TOKEN}');
  perform pg_temp.assert_eq('agora há UM convite em aberto para o colaborador, e é o novo',
    (select string_agg(id::text, ',') from app.messaging_invite
      where employee_id = '{I_EMPLOYEE}' and used_at is null and expires_at > now()), novo.id::text);
end $$;

-- ---------------------------------------------------------------------------
-- A fila: o gatilho aceita o payload nome/link, recusa nomeado sem link
-- ---------------------------------------------------------------------------
do $$
declare
  n int;
  fila record;
  msg text;
  falhou boolean;
begin
  execute $q$with x as ({ENQUEUE}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('a linha da fila entrou (o gatilho aceitou)', n::text, '1');
  select * into fila from app.alert_queue where tenant_id = '{I_TENANT}';
  perform pg_temp.assert_eq('canal WhatsApp', fila.channel, 'whatsapp');
  perform pg_temp.assert_eq('o provedor ativo', fila.provider, 'z_api');
  perform pg_temp.assert_eq('o template do convite', fila.template_code, 'telegram_invite');
  perform pg_temp.assert_eq('o destino em E.164', fila.destination, '{I_E164}');
  perform pg_temp.assert_eq('sem regra e sem ciclo', (fila.rule_id is null and fila.report_cycle_id is null)::text, 'true');
  perform pg_temp.assert_eq('pendente para o sender', fila.status, 'pending');
  perform pg_temp.assert_eq('o payload tem exatamente nome e link',
    (select string_agg(k, ',' order by k) from jsonb_object_keys(fila.payload) k), 'link,nome');
  perform pg_temp.assert_eq('a chave de idempotência é do convite',
    fila.idempotency_key, 'telegram_invite:' || (select id from app.messaging_invite where token_hash = '{HASH_NOVO}'));

  execute $q$with x as ({ENQUEUE}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('a mesma chave de novo: 0 linhas (on conflict do nothing)', n::text, '0');
  perform pg_temp.assert_eq('e a fila continua com uma linha',
    (select count(*) from app.alert_queue where tenant_id = '{I_TENANT}')::text, '1');

  -- Sem `link` no payload: o gatilho recusa, nomeando a variável.
  falhou := false;
  begin
    execute $q${ENQUEUE_SEM_LINK}$q$;
  exception when raise_exception then
    falhou := true;
    get stacked diagnostics msg = message_text;
  end;
  perform pg_temp.assert_eq('payload sem link: o gatilho recusou', falhou::text, 'true');
  perform pg_temp.assert_eq('e nomeou a variável que falta', msg,
    'Payload não cobre as variáveis do template telegram_invite: link');

  -- Provedor oficial com o template em draft: o gatilho recusa também — é o
  -- `invite_refused` da rota, com esta frase.
  falhou := false;
  begin
    execute $q${ENQUEUE_META}$q$;
  exception when raise_exception then
    falhou := true;
    get stacked diagnostics msg = message_text;
  end;
  perform pg_temp.assert_eq('meta_cloud com template draft: o gatilho recusou', falhou::text, 'true');
  perform pg_temp.assert_eq('com a frase da aprovação', msg,
    'Template telegram_invite está draft e o provedor é meta_cloud.');
  perform pg_temp.assert_eq('as duas recusas não deixaram linha',
    (select count(*) from app.alert_queue where tenant_id = '{I_TENANT}')::text, '1');
end $$;

-- ---------------------------------------------------------------------------
-- A auditoria: o titular e o convite; não o hash, não o número
-- ---------------------------------------------------------------------------
do $$
declare
  trilha record;
begin
  execute $q${AUDIT_INVITE}$q$;
  select * into trilha from app.audit_log where tenant_id = '{I_TENANT}' and entity = 'messaging_invite';
  perform pg_temp.assert_eq('auditoria: insert de messaging_invite pelo owner',
    trilha.action || '/' || trilha.user_id::text, 'insert/{I_OWNER}');
  perform pg_temp.assert_eq('auditoria: o titular', trilha.depois ->> 'titular', 'employee');
  perform pg_temp.assert_eq('auditoria: o convite', trilha.depois ->> 'invite_id',
    (select id::text from app.messaging_invite where token_hash = '{HASH_NOVO}'));
  perform pg_temp.assert_not_in('auditoria: sem o hash', trilha.depois::text, '{HASH_NOVO}');
  perform pg_temp.assert_not_in('auditoria: sem o token', trilha.depois::text, '{I_TOKEN}');
  perform pg_temp.assert_not_in('auditoria: sem o número', trilha.depois::text, '9999');
end $$;

-- ---------------------------------------------------------------------------
-- A ficha: convite em aberto → vinculado → desvinculado → revogar de novo é 0
-- ---------------------------------------------------------------------------
do $$
declare
  ficha record;
  n int;
  chaves text;
  vigente record;
begin
  select * into ficha from ({LINK}) x;
  select string_agg(k, ',' order by k) into chaves from json_object_keys(row_to_json(ficha)) k;
  perform pg_temp.assert_eq('a ficha: só as três colunas (sem external_id)', chaves,
    'invite_open_until,last_revoked_at,opted_in_at');
  perform pg_temp.assert_eq('estado 1: não vinculado, nunca revogado',
    (ficha.opted_in_at is null and ficha.last_revoked_at is null)::text, 'true');
  perform pg_temp.assert_eq('estado 1: o convite em aberto é o novo (não o vencido)',
    ficha.invite_open_until::text,
    (select expires_at::text from app.messaging_invite where token_hash = '{HASH_NOVO}'));
  select * into ficha from ({LINK_OUTRO}) x;
  perform pg_temp.assert_eq('ligada ao outro tenant: tudo nulo',
    (ficha.opted_in_at is null and ficha.last_revoked_at is null and ficha.invite_open_until is null)::text, 'true');

  -- A pessoa clicou: o webhook consome o convite e insere a identidade.
  execute $q${CONSUME_NOVO}$q$;
  get diagnostics n = row_count;
  perform pg_temp.assert_eq('o /start consumiu o convite novo', n::text, '1');
  execute $q${INSERT_IDENTITY}$q$;
  select * into ficha from ({LINK}) x;
  perform pg_temp.assert_eq('estado 2: vinculado', (ficha.opted_in_at is not null)::text, 'true');
  perform pg_temp.assert_eq('estado 2: sem convite em aberto (foi usado)', (ficha.invite_open_until is null)::text, 'true');

  -- O administrador pede outro convite com a pessoa já vinculada (troca de
  -- aparelho): a ficha mostra os dois — vinculado E convite em aberto.
  execute $q${INSERT_INVITE_2}$q$;
  select * into ficha from ({LINK}) x;
  perform pg_temp.assert_eq('vinculado com convite em aberto: os dois aparecem',
    (ficha.opted_in_at is not null and ficha.invite_open_until is not null)::text, 'true');

  -- O administrador desvincula: a mesma instrução do webhook, com outra razão;
  -- e o convite em aberto expira junto — um link válido de quem foi
  -- desvinculado religaria a pessoa sem ninguém pedir.
  execute $q$with x as ({UNLINK}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('desvincular: a vigente revogada (1 linha)', n::text, '1');
  select * into vigente from app.messaging_identity where tenant_id = '{I_TENANT}' and employee_id = '{I_EMPLOYEE}';
  perform pg_temp.assert_eq('a linha FICA (nada é apagado)', (vigente.id is not null)::text, 'true');
  perform pg_temp.assert_eq('com revoked_at preenchido', (vigente.revoked_at is not null)::text, 'true');
  perform pg_temp.assert_eq('e a razão do administrador', vigente.revoked_reason, 'desvinculado pelo administrador');
  execute $q$with x as ({EXPIRE_EMPLOYEE}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('desvincular: o convite em aberto expirou junto (1 linha)', n::text, '1');
  select * into ficha from ({LINK}) x;
  perform pg_temp.assert_eq('estado 3: não vinculado', (ficha.opted_in_at is null)::text, 'true');
  perform pg_temp.assert_eq('estado 3: a última revogação é a do administrador',
    ficha.last_revoked_at::text, vigente.revoked_at::text);
  perform pg_temp.assert_eq('estado 3: sem convite em aberto', (ficha.invite_open_until is null)::text, 'true');

  -- Revogar de novo: 0 linhas — é o 409 da rota.
  execute $q$with x as ({UNLINK}) select count(*) from x$q$ into n;
  perform pg_temp.assert_eq('revogar sem vigente: 0 linhas (409 not_linked)', n::text, '0');

  -- E um convite novo depois de desvinculado reabre a ficha: a revogação
  -- continua na história, e o convite em aberto aparece ao lado dela.
  execute $q${INSERT_INVITE_3}$q$;
  select * into ficha from ({LINK}) x;
  perform pg_temp.assert_eq('estado 4: revogado E com convite em aberto',
    (ficha.opted_in_at is null and ficha.last_revoked_at is not null and ficha.invite_open_until is not null)::text, 'true');
  perform pg_temp.assert_eq('seis convites na história do colaborador, um em aberto, nenhum apagado',
    (select count(*) || '/' || count(*) filter (where used_at is null and expires_at > now())
       from app.messaging_invite where employee_id = '{I_EMPLOYEE}'), '6/1');
end $$;

rollback;
"""

CENARIO_ROTEAMENTO = """
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
    raise exception 'FALHA [%]: o valor apareceu', rotulo;
  end if;
  raise notice '  ok  %', rotulo;
end $$;

insert into auth.users (id, email) values
  ('{R_OWNER}',       'owner@rota'),
  ('{R_OUTRO_OWNER}', 'owner@rota-outro');
insert into app.tenant (id, slug, name) values
  ('{R_TENANT}', 'rota-teste', 'Rota'),
  ('{R_OUTRO}',  'rota-outro', 'Outro');
insert into app.tenant_member (tenant_id, user_id, role) values
  ('{R_TENANT}', '{R_OWNER}',       'owner'),
  ('{R_OUTRO}',  '{R_OUTRO_OWNER}', 'owner');
insert into app.company (id, tenant_id, legal_name) values
  ('{R_COMPANY}', '{R_TENANT}', 'Empresa Rota LTDA');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('{R_UNIT}', '{R_TENANT}', '{R_COMPANY}', 'RT-1', 'Unidade Rota');

-- Quatro responsáveis: aderiu (vigente), revogou, nunca aderiu, e um que
-- aderiu mas NÃO tem número de WhatsApp — o par do "sem para onde ir".
insert into app.contact (id, tenant_id, name, type, whatsapp) values
  ('{R_ADERIU}',     '{R_TENANT}', 'Gestora Aderiu',     'person', '+5511999990401'),
  ('{R_REVOGOU}',    '{R_TENANT}', 'Gestor Revogou',     'person', '+5511999990402'),
  ('{R_SEM}',        '{R_TENANT}', 'Gestora Sem Adesao', 'person', '+5511999990403'),
  ('{R_SEM_NUMERO}', '{R_TENANT}', 'Gestor Sem Numero',  'person', null);
insert into app.messaging_identity (tenant_id, channel, contact_id, external_id, revoked_at, revoked_reason, opted_in_at) values
  ('{R_TENANT}', 'telegram', '{R_ADERIU}',     '{R_CHAT_ADERIU}',     null, null, now()),
  ('{R_TENANT}', 'telegram', '{R_REVOGOU}',    '{R_CHAT_REVOGOU}',    now() - interval '1 day', 'desvinculado pelo administrador', now() - interval '2 days'),
  ('{R_TENANT}', 'telegram', '{R_SEM_NUMERO}', '{R_CHAT_SEM_NUMERO}', null, null, now()),
  -- ⛔ O chat reatribuído (S26 da revisão): o MESMO chat_id de quem aderiu já
  --    foi de outro contato, e está revogado. O titular tem de ser quem o tem
  --    VIGENTE — com a ordem invertida, a mensagem iria para o WhatsApp errado.
  ('{R_TENANT}', 'telegram', '{R_SEM}',        '{R_CHAT_ADERIU}',     now() - interval '30 days', 'novo /start', now() - interval '60 days');

-- Bot ativo e WhatsApp ativo (z_api: não oficial, o gatilho não exige aprovação).
-- Mais uma de canal DESLIGADA e uma que não é de canal (secullum, como em
-- produção): nenhuma das duas pode chegar à fábrica (S24a/S45 da revisão).
insert into app.integration (id, tenant_id, provider, alias, config, active) values
  ('{R_BOT}',            '{R_TENANT}', 'telegram', 'telegram', '{"public_identity": "@RotaBot"}', true),
  ('{R_ZAPI}',           '{R_TENANT}', 'z_api',    'z_api',    '{"instance_id": "X"}',            true),
  ('{R_UAZAPI_INATIVA}', '{R_TENANT}', 'uazapi',   'uazapi',   '{"base_url": "https://x"}',       false),
  ('{R_SECULLUM}',       '{R_TENANT}', 'secullum', 'secullum', '{}',                              true);
insert into app.message_template (tenant_id, code, variables, body, language, meta_template_name) values
  ('{R_TENANT}', 'deviation_summary', array['unit','link'],
   'FastPark: {{1}} — {{2}}', 'pt_BR', 'fastpark_resumo'),
  ('{R_TENANT}', 'telegram_invite', array['nome','link'],
   'Olá {{1}}, abra {{2}}.', 'pt_BR', null);

-- A regra agregada, por mensageria, para os quatro.
insert into app.alert_rule (id, tenant_id, name, content, channel, active, template_code) values
  ('{R_RULE}', '{R_TENANT}', 'Resumo por mensageria', 'aggregate', 'whatsapp', true, 'deviation_summary');
insert into app.alert_rule_target (rule_id, contact_id) values
  ('{R_RULE}', '{R_ADERIU}'), ('{R_RULE}', '{R_REVOGOU}'), ('{R_RULE}', '{R_SEM}'), ('{R_RULE}', '{R_SEM_NUMERO}');

-- ---------------------------------------------------------------------------
-- 1. As duas entradas de `route`, pela `_TARGETS_SQL` — e o bot PRONTO
-- ---------------------------------------------------------------------------
-- Sem linha de saúde: o bot está ativo e NÃO está pronto (fail-closed, o
-- mesmo `coalesce(..., false)` da fn_channel_readiness).
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('bot ativo SEM medição de saúde: telegram_ready = false em todas',
    (select count(*) from alvo where not telegram_ready)::text, '4');
  perform pg_temp.assert_eq('e o external_id de quem aderiu vem mesmo assim (route é quem nega)',
    (select telegram_external_id from alvo where contact_id = '{R_ADERIU}'), '{R_CHAT_ADERIU}');
end $$;
drop table alvo;

-- O vigia (ou a conexão pelo painel) mede `connected`: agora está pronto.
select app.fn_record_channel_health('{R_BOT}', 'connected', 'ensaio');
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('_TARGETS_SQL: a regra alcança os 4 contatos', (select count(*) from alvo)::text, '4');
  perform pg_temp.assert_eq('quem aderiu traz o external_id',
    (select telegram_external_id from alvo where contact_id = '{R_ADERIU}'), '{R_CHAT_ADERIU}');
  perform pg_temp.assert_eq('e telegram_ready = true (bot ativo E connected)',
    (select telegram_ready::text from alvo where contact_id = '{R_ADERIU}'), 'true');
  perform pg_temp.assert_eq('quem revogou NÃO traz external_id (só a vigente conta)',
    (select coalesce(telegram_external_id, 'nulo') from alvo where contact_id = '{R_REVOGOU}'), 'nulo');
  perform pg_temp.assert_eq('quem nunca aderiu tampouco',
    (select coalesce(telegram_external_id, 'nulo') from alvo where contact_id = '{R_SEM}'), 'nulo');
  perform pg_temp.assert_eq('e o número continua vindo para todos que o têm',
    (select count(*) from alvo where whatsapp is not null)::text, '3');
end $$;
drop table alvo;

-- O vigia mede `disconnected`: a identidade continua, `telegram_ready` cai —
-- quem decide é `route`, e ele exige os dois (o par do falso verde).
select app.fn_record_channel_health('{R_BOT}', 'disconnected', 'webhook ausente');
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('bot ativo mas disconnected: telegram_ready = false em todas as linhas',
    (select count(*) from alvo where not telegram_ready)::text, '4');
  perform pg_temp.assert_eq('e o external_id de quem aderiu CONTINUA vindo (route é quem nega)',
    (select telegram_external_id from alvo where contact_id = '{R_ADERIU}'), '{R_CHAT_ADERIU}');
end $$;
drop table alvo;

-- `unknown` (token ausente, getWebhookInfo recusado) também não é pronto: só
-- `connected` é.
select app.fn_record_channel_health('{R_BOT}', 'unknown', 'getWebhookInfo: unauthorized');
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('saúde unknown: telegram_ready = false em todas as linhas',
    (select count(*) from alvo where not telegram_ready)::text, '4');
end $$;
drop table alvo;

-- A saúde é POR INTEGRAÇÃO: um `connected` de outra integração do tenant não
-- empresta prontidão ao bot que está `disconnected`.
select app.fn_record_channel_health('{R_BOT}', 'disconnected', 'webhook ausente');
select app.fn_record_channel_health('{R_ZAPI}', 'connected', 'ensaio');
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('saúde connected de OUTRA integração não conta para o bot',
    (select count(*) from alvo where not telegram_ready)::text, '4');
end $$;
drop table alvo;
select app.fn_record_channel_health('{R_ZAPI}', 'disconnected', 'ensaio: devolvido');
select app.fn_record_channel_health('{R_BOT}', 'connected', 'ensaio');

-- Bot desligado, mesmo com a saúde em `connected`: não pronto.
update app.integration set active = false where id = '{R_BOT}';
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('bot desligado (saúde connected): telegram_ready = false em todas',
    (select count(*) from alvo where not telegram_ready)::text, '4');
end $$;
drop table alvo;
update app.integration set active = true where id = '{R_BOT}';
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('religado: pronto de novo',
    (select telegram_ready::text from alvo where contact_id = '{R_ADERIU}'), 'true');
end $$;
drop table alvo;

do $$ begin
  perform pg_temp.assert_eq('ligada ao OUTRO tenant, _TARGETS_SQL é zero linhas',
    (select count(*) from ({TARGETS_OUTRO}) o)::text, '0');
end $$;

-- ---------------------------------------------------------------------------
-- 2. A fila: o check novo, a espera, a reserva (com a presa) e o template
-- ---------------------------------------------------------------------------
insert into app.alert_queue
  (id, tenant_id, rule_id, channel, destination, payload, idempotency_key, template_code, provider,
   status, attempts, next_attempt_at, scheduled_for) values
  ('{Q_TELEGRAM}', '{R_TENANT}', '{R_RULE}', 'telegram', '{R_CHAT_ADERIU}',
   '{"unit": "Rota", "link": "https://app.x/dashboard?un=1"}', 'k-telegram', 'deviation_summary', 'telegram',
   'pending', 0, now() - interval '1 minute', now() - interval '1 minute'),
  ('{Q_WHATSAPP}', '{R_TENANT}', '{R_RULE}', 'whatsapp', '+5511999990403',
   '{"unit": "Rota", "link": "https://app.x/dashboard?un=1"}', 'k-whatsapp', 'deviation_summary', 'z_api',
   'pending', 0, now() - interval '1 minute', now() - interval '1 minute'),
  ('{Q_INVITE}', '{R_TENANT}', null, 'whatsapp', '+5511999990403',
   '{"nome": "Gestora", "link": "{R_INVITE_LINK}"}', 'k-invite', 'telegram_invite', 'z_api',
   'pending', 0, now() - interval '1 minute', now() - interval '1 minute'),
  ('{Q_PRESA}', '{R_TENANT}', '{R_RULE}', 'whatsapp', '+5511999990403',
   '{"unit": "Rota", "link": "https://app.x/dashboard?un=1"}', 'k-presa', 'deviation_summary', 'z_api',
   'sending', 1, now() - interval '11 minutes', now() - interval '1 hour'),
  ('{Q_FRESCA}', '{R_TENANT}', '{R_RULE}', 'whatsapp', '+5511999990403',
   '{"unit": "Rota", "link": "https://app.x/dashboard?un=1"}', 'k-fresca', 'deviation_summary', 'z_api',
   'sending', 1, now() - interval '2 minutes', now() - interval '1 hour'),
  ('{Q_FUTURA}', '{R_TENANT}', '{R_RULE}', 'whatsapp', '+5511999990403',
   '{"unit": "Rota", "link": "https://app.x/dashboard?un=1"}', 'k-futura', 'deviation_summary', 'z_api',
   'pending', 0, now() - interval '1 minute', now() + interval '1 hour');
do $$ begin
  perform pg_temp.assert_eq('a linha com channel = telegram passou no check novo',
    (select count(*) from app.alert_queue where id = '{Q_TELEGRAM}' and channel = 'telegram')::text, '1');
  perform pg_temp.assert_eq('_WAITING_SQL: 3 esperam (pending vencidas; a presa e a futura não)',
    (select waiting from ({WAITING}) w)::text, '3');
end $$;

create temp table reservadas (id uuid, previous_status text);
with r as ({CLAIM}) insert into reservadas select id, previous_status from r;
create temp table reservadas2 (id uuid);
with r as ({CLAIM}) insert into reservadas2 select id from r;
do $$ begin
  perform pg_temp.assert_eq('_CLAIM_SQL: reservou 4 — as 3 pending vencidas e a sending PRESA',
    (select count(*) from reservadas)::text, '4');
  perform pg_temp.assert_eq('a presa vem com previous_status = sending',
    (select previous_status from reservadas where id = '{Q_PRESA}'), 'sending');
  perform pg_temp.assert_eq('as outras três vêm de pending',
    (select count(*) from reservadas where previous_status = 'pending')::text, '3');
  perform pg_temp.assert_eq('a sending FRESCA não foi tomada',
    (select count(*) from reservadas where id = '{Q_FRESCA}')::text, '0');
  perform pg_temp.assert_eq('nem a agendada para o futuro',
    (select count(*) from reservadas where id = '{Q_FUTURA}')::text, '0');
  perform pg_temp.assert_eq('as 4 estão sending, com a reserva carimbada em next_attempt_at',
    (select count(*) from app.alert_queue
      where id in (select id from reservadas) and status = 'sending'
        and next_attempt_at > now() - interval '5 seconds')::text, '4');
  perform pg_temp.assert_eq('e a segunda reserva, logo em seguida, não pega nada (skip do sending fresco)',
    (select count(*) from reservadas2)::text, '0');
end $$;

do $$ begin
  perform pg_temp.assert_eq('_TEMPLATE_SQL traz os quatro campos do template',
    (select array_to_string(variables, ',') || '|' || body || '|' || language || '|' || meta_template_name
       from ({TEMPLATE}) t), 'unit,link|FastPark: {{1}} — {{2}}|pt_BR|fastpark_resumo');
  perform pg_temp.assert_eq('_INTEGRATIONS_SQL: as 2 integrações de canal ATIVAS (bot e z_api) — a uazapi desligada e a secullum ficam fora',
    (select string_agg(provider, ',' order by provider) from ({INTEGRATIONS}) i), 'telegram,z_api');
  perform pg_temp.assert_eq('(o anti-vácuo: o tenant tem 4 integrações na tabela)',
    (select count(*) from app.integration where tenant_id = '{R_TENANT}')::text, '4');
  perform pg_temp.assert_eq('e o config vem inteiro (a fábrica escolhe o que ler)',
    (select config ->> 'public_identity' from ({INTEGRATIONS}) i where id = '{R_BOT}'), '@RotaBot');
  perform pg_temp.assert_eq('ligada ao outro tenant: zero integrações',
    (select count(*) from ({INTEGRATIONS_OUTRO}) i)::text, '0');
end $$;

-- ---------------------------------------------------------------------------
-- 3. O scrub, contra o gatilho de verdade
-- ---------------------------------------------------------------------------
{MARK_SENT_INVITE};
{MARK_SENT_WHATSAPP};
do $$ begin
  perform pg_temp.assert_eq('o convite entregue está sent',
    (select status from app.alert_queue where id = '{Q_INVITE}'), 'sent');
  perform pg_temp.assert_eq('e o payload dele NÃO tem link (o gatilho deixou o terminal passar)',
    (select (payload ? 'link')::text from app.alert_queue where id = '{Q_INVITE}'), 'false');
  perform pg_temp.assert_eq('mas ainda tem nome',
    (select payload ->> 'nome' from app.alert_queue where id = '{Q_INVITE}'), 'Gestora');
  perform pg_temp.assert_not_in('o token do convite não está mais na fila',
    (select string_agg(payload::text, ' ') from app.alert_queue), 'token-que-nao-pode-ficar-na-fila');
  perform pg_temp.assert_eq('o alerta entregue MANTÉM o link do painel',
    (select payload ->> 'link' from app.alert_queue where id = '{Q_WHATSAPP}'), 'https://app.x/dashboard?un=1');
  -- `_WAITING_SQL` depois das marcas: as duas `sent` e as duas `sending` não
  -- contam, a futura tampouco — 3 virou 0 (S10b da revisão).
  perform pg_temp.assert_eq('_WAITING_SQL depois das marcas: 0 (sent, sending e futura não contam)',
    (select waiting from ({WAITING}) w)::text, '0');
end $$;

-- O negativo do gatilho numa `sending`: a abertura é só para sent/discarded.
do $$
declare v_recusou boolean := false;
begin
  begin
    update app.alert_queue set payload = payload - 'link' where id = '{Q_PRESA}';
  exception when raise_exception then v_recusou := true; end;
  perform pg_temp.assert_eq('o gatilho RECUSA payload - link numa linha sending',
    v_recusou::text, 'true');
end $$;

-- A quinta falha descarta e tira o link; a primeira devolve e o mantém.
insert into app.alert_queue
  (id, tenant_id, rule_id, channel, destination, payload, idempotency_key, template_code, provider, status, attempts) values
  ('{Q_INVITE_5}', '{R_TENANT}', null, 'whatsapp', '+5511999990403',
   '{"nome": "Gestora", "link": "{R_INVITE_LINK}"}', 'k-invite-5', 'telegram_invite', 'z_api', 'sending', 4),
  ('{Q_INVITE_1}', '{R_TENANT}', null, 'whatsapp', '+5511999990403',
   '{"nome": "Gestora", "link": "{R_INVITE_LINK}"}', 'k-invite-1', 'telegram_invite', 'z_api', 'sending', 0);
create temp table marcas (queue_id uuid, status text);
with r as ({MARK_FAILED_5}) insert into marcas select '{Q_INVITE_5}', status from r;
with r as ({MARK_FAILED_1}) insert into marcas select '{Q_INVITE_1}', status from r;
do $$ begin
  perform pg_temp.assert_eq('_MARK_FAILED_SQL na quinta tentativa devolve discarded',
    (select status from marcas where queue_id = '{Q_INVITE_5}'), 'discarded');
  perform pg_temp.assert_eq('e o convite descartado perdeu o link',
    (select (payload ? 'link')::text from app.alert_queue where id = '{Q_INVITE_5}'), 'false');
  perform pg_temp.assert_eq('na primeira devolve failed',
    (select status from marcas where queue_id = '{Q_INVITE_1}'), 'failed');
  perform pg_temp.assert_eq('e o convite que volta para a fila MANTÉM o link (a próxima tentativa precisa dele)',
    (select payload ->> 'link' from app.alert_queue where id = '{Q_INVITE_1}'), '{R_INVITE_LINK}');
  perform pg_temp.assert_eq('com o backoff de 1 minuto',
    (select (next_attempt_at between now() + interval '50 seconds' and now() + interval '70 seconds')::text
       from app.alert_queue where id = '{Q_INVITE_1}'), 'true');
end $$;

-- O negativo: numa linha que NÃO é terminal, o gatilho ainda recusa o scrub.
do $$
declare v_recusou boolean := false;
begin
  begin
    update app.alert_queue set payload = payload - 'link' where id = '{Q_INVITE_1}';
  exception when raise_exception then v_recusou := true; end;
  perform pg_temp.assert_eq('o gatilho RECUSA payload - link numa linha failed (a abertura é só para sent/discarded)',
    v_recusou::text, 'true');
end $$;

-- ---------------------------------------------------------------------------
-- 4. `blocked`, passo a passo
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('_IDENTITY_HOLDER_SQL: o chat de quem aderiu aponta quem o tem VIGENTE (não o revogado de outro contato)',
    (select contact_id::text from ({HOLDER_ADERIU}) h), '{R_ADERIU}');
  perform pg_temp.assert_eq('(o anti-vácuo: esse chat_id tem 2 linhas, uma revogada de outro contato)',
    (select count(*) from app.messaging_identity where external_id = '{R_CHAT_ADERIU}')::text, '2');
  perform pg_temp.assert_eq('o chat REVOGADO ainda diz quem era (para o re-roteamento)',
    (select contact_id::text from ({HOLDER_REVOGOU}) h), '{R_REVOGOU}');
  perform pg_temp.assert_eq('um chat inventado é zero linhas',
    (select count(*) from ({HOLDER_INVENTADO}) h)::text, '0');
  perform pg_temp.assert_eq('e ligado ao outro tenant, o chat de quem aderiu é zero',
    (select count(*) from ({HOLDER_OUTRO}) h)::text, '0');
end $$;

-- O provedor de Telegram respondeu blocked para Q_TELEGRAM (que está sending):
-- (c1) o log e o estacionamento; (c2) a revogação, a auditoria, o WhatsApp
-- ativo e o re-roteamento.
{LOG_BLOCKED};
{PARK_TELEGRAM};
do $$ begin
  perform pg_temp.assert_eq('_PARK_SQL: failed, tentativa contada, horário intocado (a reserva)',
    (select status || '/' || attempts || '/'
         || (next_attempt_at between now() - interval '5 seconds' and now())::text
       from app.alert_queue where id = '{Q_TELEGRAM}'), 'failed/1/true');
end $$;
create temp table revogadas (id uuid);
with r as ({REVOKE_ADERIU}) insert into revogadas select id from r;
do $$
declare v_id text; v_depois text;
begin
  perform pg_temp.assert_eq('_LOG_SQL gravou a tentativa de Telegram como failed/blocked',
    (select count(*) from app.alert_sent
      where queue_id = '{Q_TELEGRAM}' and channel = 'telegram' and provider = 'telegram'
        and status = 'failed' and error = 'blocked')::text, '1');
  perform pg_temp.assert_not_in('e sem o chat_id em claro (só o hash)',
    (select string_agg(destination_hash, ' ') from app.alert_sent where queue_id = '{Q_TELEGRAM}'), '{R_CHAT_ADERIU}');
  perform pg_temp.assert_eq('_REVOKE_PREVIOUS_SQL (do webhook) revogou a vigente de quem aderiu: 1 linha',
    (select count(*) from revogadas)::text, '1');
  perform pg_temp.assert_eq('com a razão',
    (select revoked_reason from app.messaging_identity where contact_id = '{R_ADERIU}'), 'bloqueou o bot');
  perform pg_temp.assert_eq('e nada foi apagado',
    (select count(*) from app.messaging_identity where tenant_id = '{R_TENANT}')::text, '4');
  select id::text into v_id from revogadas;
  execute replace($q${AUDIT}$q$, '%(entity_id)s', quote_literal(v_id));
  select depois::text into v_depois from app.audit_log
   where tenant_id = '{R_TENANT}' and entity = 'messaging_identity' and entity_id = v_id;
  perform pg_temp.assert_eq('a auditoria leva canal e razão',
    (select depois ->> 'reason' from app.audit_log where entity_id = v_id), 'bloqueou o bot');
  perform pg_temp.assert_not_in('e NÃO o chat_id', v_depois, '{R_CHAT_ADERIU}');
  perform pg_temp.assert_eq('e sem pessoa autenticada (user_id nulo)',
    (select (user_id is null)::text from app.audit_log where entity_id = v_id), 'true');
  perform pg_temp.assert_eq('_PROVIDER_SQL: o WhatsApp ativo é z_api',
    (select provider from ({PROVIDER}) p), 'z_api');
end $$;
drop table revogadas;

create temp table reroteadas (id uuid);
with r as ({REROUTE_ADERIU}) insert into reroteadas select id from r;
do $$ begin
  perform pg_temp.assert_eq('_REROUTE_SQL: a MESMA linha foi re-roteada (1 linha)',
    (select count(*) from reroteadas)::text, '1');
  perform pg_temp.assert_eq('agora é whatsapp / z_api, para o número do contato',
    (select channel || '/' || provider || '/' || destination from app.alert_queue where id = '{Q_TELEGRAM}'),
    'whatsapp/z_api/+5511999990401');
  perform pg_temp.assert_eq('failed, devida já, com as tentativas ZERADAS (as de Telegram eram do outro canal)',
    (select status || '/' || attempts || '/' || (next_attempt_at <= now())::text
       from app.alert_queue where id = '{Q_TELEGRAM}'), 'failed/0/true');
  perform pg_temp.assert_eq('e com a mesma chave de idempotência (a rota é atributo)',
    (select idempotency_key from app.alert_queue where id = '{Q_TELEGRAM}'), 'k-telegram');
end $$;
create temp table reservadas3 (id uuid);
with r as ({CLAIM}) insert into reservadas3 select id from r;
do $$ begin
  perform pg_temp.assert_eq('a próxima reserva a pega de volta (o próximo lote entrega)',
    (select count(*) from reservadas3 where id = '{Q_TELEGRAM}')::text, '1');
end $$;

-- O contato sem número: o re-roteamento devolve zero e a linha é descartada.
insert into app.alert_queue
  (id, tenant_id, rule_id, channel, destination, payload, idempotency_key, template_code, provider, status, attempts) values
  ('{Q_SEM_NUMERO}', '{R_TENANT}', '{R_RULE}', 'telegram', '{R_CHAT_SEM_NUMERO}',
   '{"unit": "Rota", "link": "https://app.x/dashboard?un=1"}', 'k-sem-numero', 'deviation_summary', 'telegram', 'sending', 0);
{PARK_SEM_NUMERO};
create temp table reroteadas2 (id uuid);
with r as ({REROUTE_SEM_NUMERO}) insert into reroteadas2 select id from r;
do $$ begin
  perform pg_temp.assert_eq('_REROUTE_SQL para o contato SEM número: zero linhas',
    (select count(*) from reroteadas2)::text, '0');
  perform pg_temp.assert_eq('a linha continua telegram, estacionada (nada mais mudou nela)',
    (select channel || '/' || status || '/' || attempts from app.alert_queue where id = '{Q_SEM_NUMERO}'), 'telegram/failed/1');
end $$;
{DISCARD_SEM_NUMERO};
do $$ begin
  perform pg_temp.assert_eq('_DISCARD_SQL: descartada, e a tentativa (contada no PARK) não conta de novo',
    (select status || '/' || attempts from app.alert_queue where id = '{Q_SEM_NUMERO}'), 'discarded/1');
  perform pg_temp.assert_eq('e o alerta descartado MANTÉM o link (o scrub é só do convite)',
    (select (payload ? 'link')::text from app.alert_queue where id = '{Q_SEM_NUMERO}'), 'true');
end $$;

-- ---------------------------------------------------------------------------
-- 4b. A re-rota RECUSADA pelo gatilho — o ALTO do ciclo 1, contra o gatilho real
-- ---------------------------------------------------------------------------
-- O tenant troca de z_api para meta_cloud (oficial) com o template em `draft`.
-- Uma linha de Telegram bloqueada é estacionada em (c1); a re-rota de (c2) é
-- recusada pelo gatilho ("Template … está draft e o provedor é meta_cloud"),
-- desfeita, e a linha vai para `_DISCARD_SQL` com o motivo no log. As outras
-- linhas do lote (Q_WHATSAPP, Q_INVITE) continuam `sent`: nada é reentregue.
update app.integration set active = false where id = '{R_ZAPI}';
insert into app.integration (id, tenant_id, provider, alias, config, active) values
  ('{R_META}', '{R_TENANT}', 'meta_cloud', 'meta_cloud', '{"phone_number_id": "1", "waba_id": "2"}', true);
insert into app.alert_queue
  (id, tenant_id, rule_id, channel, destination, payload, idempotency_key, template_code, provider, status, attempts) values
  ('{Q_RECUSADA}', '{R_TENANT}', '{R_RULE}', 'telegram', '{R_CHAT_ADERIU}',
   '{"unit": "Rota", "link": "https://app.x/dashboard?un=1"}', 'k-recusada', 'deviation_summary', 'telegram', 'sending', 2);
{PARK_RECUSADA};
do $$
declare v_recusou boolean := false; v_msg text := '';
begin
  perform pg_temp.assert_eq('_PROVIDER_SQL agora devolve meta_cloud',
    (select provider from ({PROVIDER}) p), 'meta_cloud');
  perform pg_temp.assert_eq('o template está draft',
    (select meta_status from app.message_template where tenant_id = '{R_TENANT}' and code = 'deviation_summary'), 'draft');
  begin
    execute $q$with r as ({REROUTE_META}) select id from r$q$;
  exception when raise_exception then
    v_recusou := true;
    get stacked diagnostics v_msg = message_text;
  end;
  perform pg_temp.assert_eq('o gatilho RECUSA a re-rota para meta_cloud com template draft', v_recusou::text, 'true');
  perform pg_temp.assert_eq('e a frase nomeia o template e o provedor, sem payload',
    v_msg, 'Template deviation_summary está draft e o provedor é meta_cloud.');
  perform pg_temp.assert_not_in('(sem o link)', v_msg, 'app.x');
  perform pg_temp.assert_eq('a linha ficou como (c1) a deixou: telegram, failed, estacionada',
    (select channel || '/' || provider || '/' || status || '/' || attempts from app.alert_queue where id = '{Q_RECUSADA}'),
    'telegram/telegram/failed/3');
end $$;
{LOG_REFUSED};
{DISCARD_RECUSADA};
do $$ begin
  perform pg_temp.assert_eq('a recusada foi descartada',
    (select status from app.alert_queue where id = '{Q_RECUSADA}'), 'discarded');
  perform pg_temp.assert_eq('com o motivo no log, pelo canal que recusou (whatsapp/meta_cloud/failed)',
    (select channel || '/' || provider || '/' || status from app.alert_sent
      where queue_id = '{Q_RECUSADA}' and error like 'reroute_refused: %'), 'whatsapp/meta_cloud/failed');
  perform pg_temp.assert_eq('as outras linhas do lote continuam entregues (nada a reentregar)',
    (select count(*) from app.alert_queue where id in ('{Q_WHATSAPP}', '{Q_INVITE}') and status = 'sent')::text, '2');
  -- As `sending` do tenant são só as 3 reservadas antes (presa, fresca e a
  -- re-roteada que a terceira reserva pegou): a recusa não deixou nenhuma.
  perform pg_temp.assert_eq('e nenhuma linha ficou sending por causa da recusa',
    (select string_agg(id::text, ',' order by id) from app.alert_queue
      where tenant_id = '{R_TENANT}' and status = 'sending'),
    '{Q_TELEGRAM}' || ',' || '{Q_PRESA}' || ',' || '{Q_FRESCA}');
end $$;
update app.integration set active = false where id = '{R_META}';
update app.integration set active = true where id = '{R_ZAPI}';

-- Depois da revogação, `_TARGETS_SQL` já não traz o chat: o próximo ciclo vai por WhatsApp.
create temp table alvo as {TARGETS};
do $$ begin
  perform pg_temp.assert_eq('depois do blocked, quem aderiu já não traz external_id (§8 degrada sozinho)',
    (select coalesce(telegram_external_id, 'nulo') from alvo where contact_id = '{R_ADERIU}'), 'nulo');
end $$;
drop table alvo;

-- ---------------------------------------------------------------------------
-- 5. `alert_sent` com os quatro provedores, e o relatório por canal
-- ---------------------------------------------------------------------------
{LOG_META};
{LOG_ZAPI};
{LOG_UAZAPI};
{LOG_OUTRO};
do $$ begin
  perform pg_temp.assert_eq('alert_sent aceita os quatro provedores de canal',
    (select count(distinct provider) from app.alert_sent where tenant_id = '{R_TENANT}')::text, '4');
end $$;

set local role authenticated;
set local request.jwt.claims = '{"sub": "{R_OWNER}", "role": "authenticated"}';
set local request.jwt.claim.sub = '{R_OWNER}';
do $$ begin
  perform pg_temp.assert_eq('fn_delivery_by_channel (owner): 4 linhas desta semana, uma por canal/provedor',
    (select count(*) from public.fn_delivery_by_channel())::text, '4');
  perform pg_temp.assert_eq('telegram: 0 sent, 1 failed (o blocked)',
    (select sent || '/' || failed from public.fn_delivery_by_channel() where provider = 'telegram'), '0/1');
  perform pg_temp.assert_eq('meta_cloud: 1 sent, 1 failed (a re-rota recusada aparece como falha de WhatsApp)',
    (select sent || '/' || failed from public.fn_delivery_by_channel() where provider = 'meta_cloud'), '1/1');
  perform pg_temp.assert_eq('z_api: 1 sent, 0 failed',
    (select sent || '/' || failed from public.fn_delivery_by_channel() where provider = 'z_api'), '1/0');
  perform pg_temp.assert_eq('todas desta semana',
    (select count(*) from public.fn_delivery_by_channel() where week_start = date_trunc('week', now())::date)::text, '4');
  perform pg_temp.assert_eq('e nenhuma do outro tenant (uazapi de lá não entra na contagem daqui)',
    (select coalesce(sum(sent + failed), 0) from public.fn_delivery_by_channel() where provider = 'uazapi')::text, '1');
end $$;
set local request.jwt.claims = '{"sub": "{R_OUTRO_OWNER}", "role": "authenticated"}';
set local request.jwt.claim.sub = '{R_OUTRO_OWNER}';
do $$ begin
  perform pg_temp.assert_eq('o owner do outro tenant vê só a linha dele (uazapi, 1)',
    (select count(*) from public.fn_delivery_by_channel())::text, '1');
  perform pg_temp.assert_eq('e é uazapi/1',
    (select provider || '/' || sent from public.fn_delivery_by_channel()), 'uazapi/1');
end $$;
reset role;

rollback;
"""


def webhook(webhook_sql: dict[str, str], tenant_sql: dict[str, str]) -> str:
    """O cenário do webhook, com o SQL real de `webhooks.py` e `tenant.py`."""

    def resolve(path_token: str) -> str:
        return ligar(tenant_sql["_WEBHOOK_INTEGRATION_SQL"], provider="telegram", path_token=path_token)

    def invite(tenant: str, token_hash: str) -> str:
        return ligar(webhook_sql["_INVITE_SQL"], tenant_id=tenant, channel="telegram", token_hash=token_hash)

    def consume(invite_id: str) -> str:
        return ligar(webhook_sql["_CONSUME_INVITE_SQL"], tenant_id=W_TENANT, invite_id=invite_id)

    def holder(sql: str, employee_id: str | None, contact_id: str | None) -> str:
        return sql.replace("%(employee_id)s", "null" if employee_id is None else f"'{employee_id}'").replace(
            "%(contact_id)s", "null" if contact_id is None else f"'{contact_id}'"
        )

    def revoke(employee_id: str | None, contact_id: str | None) -> str:
        return holder(
            ligar(webhook_sql["_REVOKE_PREVIOUS_SQL"], tenant_id=W_TENANT, channel="telegram", reason="novo /start"),
            employee_id,
            contact_id,
        )

    def insert(employee_id: str | None, contact_id: str | None, chat_id: str) -> str:
        return holder(
            ligar(webhook_sql["_INSERT_IDENTITY_SQL"], tenant_id=W_TENANT, channel="telegram", external_id=chat_id),
            employee_id,
            contact_id,
        )

    nova = (
        "(select id::text from app.messaging_identity where tenant_id = '" + W_TENANT
        + "' and external_id = '" + W_CHAT1 + "' and revoked_at is null)"
    )
    substituicoes = {
        "{RESOLVE}": resolve(W_PATH),
        "{RESOLVE_OUTRO}": resolve(W_PATH_OUTRO),
        "{RESOLVE_INVENTADO}": resolve("cauda-que-ninguem-registrou-0000"),
        "{RESOLVE_INATIVO}": resolve(W_PATH_INATIVO),
        "{RESOLVE_ANTIGO}": resolve(W_PATH_ANTIGO),
        "{INVITE_VALIDO}": invite(W_TENANT, HASH_VALIDO),
        "{INVITE_EXPIRADO}": invite(W_TENANT, HASH_EXPIRADO),
        "{INVITE_USADO}": invite(W_TENANT, HASH_USADO),
        "{INVITE_SEGUNDO}": invite(W_TENANT, HASH_SEGUNDO),
        "{INVITE_INVENTADO}": invite(W_TENANT, HASH_INVENTADO),
        "{INVITE_OUTRO_LIGADO_A_ESTE}": invite(W_TENANT, HASH_OUTRO),
        "{INVITE_OUTRO}": invite(W_OUTRO, HASH_OUTRO),
        "{CONSUME_VALIDO}": consume(INV_VALIDO),
        "{CONSUME_GESTOR}": consume(INV_GESTOR),
        "{CONSUME_SEGUNDO}": consume(INV_SEGUNDO),
        "{REVOKE_EMPLOYEE}": revoke(W_EMPLOYEE, None),
        "{REVOKE_CONTACT}": revoke(None, W_CONTACT),
        "{INSERT_EMPLOYEE_CHAT1}": insert(W_EMPLOYEE, None, W_CHAT1),
        "{INSERT_EMPLOYEE_CHAT2}": insert(W_EMPLOYEE, None, W_CHAT2),
        "{INSERT_CONTACT_CHAT1}": insert(None, W_CONTACT, W_CHAT1),
        "{AUDIT_EMPLOYEE_CHAT1}": ligar(
            webhook_sql["_AUDIT_SQL"],
            tenant_id=W_TENANT,
            depois='{"channel": "telegram", "invite_id": "' + INV_VALIDO + '"}',
        ).replace("%(entity_id)s", nova),
    }
    script = CENARIO_WEBHOOK
    for marcador, texto in substituicoes.items():
        script = script.replace(marcador, texto)
    for nome, valor in {
        "{W_TENANT}": W_TENANT,
        "{W_OUTRO}": W_OUTRO,
        "{W_INATIVO}": W_INATIVO,
        "{W_COMPANY}": W_COMPANY,
        "{W_UNIT}": W_UNIT,
        "{W_EMPLOYEE}": W_EMPLOYEE,
        "{W_CONTACT}": W_CONTACT,
        "{W_OUTRO_CONTACT}": W_OUTRO_CONTACT,
        "{W_PATH}": W_PATH,
        "{W_PATH_OUTRO}": W_PATH_OUTRO,
        "{W_PATH_INATIVO}": W_PATH_INATIVO,
        "{W_PATH_ANTIGO}": W_PATH_ANTIGO,
        "{INV_VALIDO}": INV_VALIDO,
        "{INV_EXPIRADO}": INV_EXPIRADO,
        "{INV_USADO}": INV_USADO,
        "{INV_GESTOR}": INV_GESTOR,
        "{INV_SEGUNDO}": INV_SEGUNDO,
        "{INV_OUTRO}": INV_OUTRO,
        "{HASH_VALIDO}": HASH_VALIDO,
        "{HASH_EXPIRADO}": HASH_EXPIRADO,
        "{HASH_USADO}": HASH_USADO,
        "{HASH_GESTOR}": HASH_GESTOR,
        "{HASH_SEGUNDO}": HASH_SEGUNDO,
        "{HASH_OUTRO}": HASH_OUTRO,
        "{W_CHAT1}": W_CHAT1,
        "{W_CHAT2}": W_CHAT2,
    }.items():
        script = script.replace(nome, valor)
    return script


def convite(fixas: dict[str, str], outbox_sql: dict[str, str], webhook_sql: dict[str, str]) -> str:
    """O cenário do convite, com o SQL real de `canais.py`, `outbox.py` e
    `webhooks.py` ligado aos valores."""
    novo = "(select id from app.messaging_invite where token_hash = '" + HASH_NOVO + "')"

    def holder(sql: str, employee_id: str | None, contact_id: str | None) -> str:
        return sql.replace("%(employee_id)s", "null" if employee_id is None else f"'{employee_id}'").replace(
            "%(contact_id)s", "null" if contact_id is None else f"'{contact_id}'"
        )

    def expire(tenant: str) -> str:
        return holder(
            ligar(fixas["_EXPIRE_OPEN_INVITES_SQL"], tenant_id=tenant, channel="telegram"), I_EMPLOYEE, None
        )

    def insert_invite(token_hash: str) -> str:
        return holder(
            ligar(fixas["_INSERT_INVITE_SQL"], tenant_id=I_TENANT, channel="telegram", token_hash=token_hash),
            I_EMPLOYEE,
            None,
        )

    def enqueue(payload: str, provider: str, key: str) -> str:
        sql = ligar(
            outbox_sql["_ENQUEUE_SQL"],
            tenant_id=I_TENANT,
            channel="whatsapp",
            destination=I_E164,
            payload=payload,
            template_code="telegram_invite",
            provider=provider,
        )
        return (
            sql.replace("%(rule_id)s", "null")
            .replace("%(cycle_id)s", "null")
            .replace("%(idempotency_key)s", key)
        )

    def link(tenant: str) -> str:
        return ligar(fixas["_LINK_SQL"], tenant_id=tenant, channel="telegram", employee_id=I_EMPLOYEE)

    payload_ok = '{"nome": "Colab", "link": "' + I_LINK + '"}'
    substituicoes = {
        "{VISIBLE_EMPLOYEE}": ligar(fixas["_VISIBLE_EMPLOYEE_SQL"], tenant_id=I_TENANT, employee_id=I_EMPLOYEE),
        "{VISIBLE_CONTACT}": ligar(fixas["_VISIBLE_CONTACT_SQL"], tenant_id=I_TENANT, contact_id=I_CONTACT),
        "{VISIBLE_GROUP}": ligar(fixas["_VISIBLE_CONTACT_SQL"], tenant_id=I_TENANT, contact_id=I_GROUP),
        "{EMPLOYEE_PHONE}": ligar(fixas["_EMPLOYEE_PHONE_SQL"], tenant_id=I_TENANT, employee_id=I_EMPLOYEE),
        "{EMPLOYEE_PHONE_OUTRO}": ligar(fixas["_EMPLOYEE_PHONE_SQL"], tenant_id=I_OUTRO, employee_id=I_EMPLOYEE),
        "{CONTACT_PHONE}": ligar(fixas["_CONTACT_PHONE_SQL"], tenant_id=I_TENANT, contact_id=I_CONTACT),
        "{BOT_STATE}": ligar(fixas["_TELEGRAM_STATE_SQL"], tenant_id=I_TENANT, provider="telegram"),
        "{PROVIDER}": ligar(outbox_sql["_PROVIDER_SQL"], tenant_id=I_TENANT),
        "{TEMPLATE}": ligar(outbox_sql["_TEMPLATE_SQL"], tenant_id=I_TENANT, code="telegram_invite"),
        "{EXPIRE_EMPLOYEE}": expire(I_TENANT),
        "{EXPIRE_OUTRO}": expire(I_OUTRO),
        "{INSERT_INVITE}": insert_invite(HASH_NOVO),
        "{INSERT_INVITE_2}": insert_invite(HASH_NOVO_2),
        "{INSERT_INVITE_3}": insert_invite(HASH_NOVO_3),
        "{ENQUEUE}": enqueue(payload_ok, "z_api", "'telegram_invite:' || " + novo),
        "{ENQUEUE_SEM_LINK}": enqueue('{"nome": "Colab"}', "z_api", "'telegram_invite:sem-link'"),
        "{ENQUEUE_META}": enqueue(payload_ok, "meta_cloud", "'telegram_invite:meta'"),
        "{AUDIT_INVITE}": ligar(
            fixas["_ADHESION_AUDIT_SQL"],
            tenant_id=I_TENANT,
            user_id=I_OWNER,
            action="insert",
            entity="messaging_invite",
        )
        .replace("%(entity_id)s", novo + "::text")
        .replace("%(depois)s", "jsonb_build_object('titular', 'employee', 'invite_id', " + novo + "::text)"),
        "{LINK}": link(I_TENANT),
        "{LINK_OUTRO}": link(I_OUTRO),
        "{CONSUME_NOVO}": ligar(webhook_sql["_CONSUME_INVITE_SQL"], tenant_id=I_TENANT).replace(
            "%(invite_id)s", novo
        ),
        "{INSERT_IDENTITY}": holder(
            ligar(webhook_sql["_INSERT_IDENTITY_SQL"], tenant_id=I_TENANT, channel="telegram", external_id=I_CHAT),
            I_EMPLOYEE,
            None,
        ),
        "{UNLINK}": holder(
            ligar(
                webhook_sql["_REVOKE_PREVIOUS_SQL"],
                tenant_id=I_TENANT,
                channel="telegram",
                reason="desvinculado pelo administrador",
            ),
            I_EMPLOYEE,
            None,
        ),
    }
    script = CENARIO_CONVITE
    for marcador, texto in substituicoes.items():
        script = script.replace(marcador, texto)
    for nome, valor in {
        "{I_TENANT}": I_TENANT,
        "{I_OUTRO}": I_OUTRO,
        "{I_OWNER}": I_OWNER,
        "{I_SUPERVISOR}": I_SUPERVISOR,
        "{I_COMPANY}": I_COMPANY,
        "{I_UNIT}": I_UNIT,
        "{I_EMPLOYEE}": I_EMPLOYEE,
        "{I_CONTACT}": I_CONTACT,
        "{I_GROUP}": I_GROUP,
        "{INV_ABERTO}": INV_ABERTO,
        "{INV_JA_USADO}": INV_JA_USADO,
        "{INV_VENCIDO}": INV_VENCIDO,
        "{HASH_ABERTO}": HASH_ABERTO,
        "{HASH_JA_USADO}": HASH_JA_USADO,
        "{HASH_VENCIDO}": HASH_VENCIDO,
        "{HASH_NOVO}": HASH_NOVO,
        "{I_PHONE}": I_PHONE,
        "{I_E164}": I_E164,
        "{I_TOKEN}": I_TOKEN,
    }.items():
        script = script.replace(nome, valor)
    return script


def telegram_bot(
    fixas: dict[str, str], fixas_tg: dict[str, str], cofre: dict[str, str], saude: dict[str, str]
) -> str:
    """O cenário do bot, com as duas renderizações, o SQL real do cofre e a
    porta única da saúde (`saude.py`, compartilhada com o vigia)."""
    v_meta = "(select id from app.integration where tenant_id = '{B_TENANT}' and provider = 'meta_cloud')"
    v_bot = "(select id from app.integration where tenant_id = '{B_TENANT}' and provider = 'telegram')"

    def cria(integracao: str, key: str) -> str:
        return ligar(
            cofre["_CREATE_SQL"], tenant_id=B_TENANT, key=key, value=VALOR, description=DESCRICAO
        ).replace("%(integration_id)s", integracao)

    def medicao(tenant: str, status: str, detail: str) -> str:
        return ligar(saude["RECORD_HEALTH_SQL"], tenant_id=tenant, status=status, detail=detail).replace(
            "%(integration_id)s", v_bot
        )

    patch = '{"webhook_path_token": "' + B_PATH_TOKEN + '", "webhook_url": "' + B_WEBHOOK_URL + '"}'
    substituicoes = {
        "{READINESS}": ligar(fixas["_READINESS_SQL"], tenant_id=B_TENANT),
        "{READINESS_OUTRO}": ligar(fixas["_READINESS_SQL"], tenant_id=B_OUTRO),
        "{STATE}": ligar(fixas["_TELEGRAM_STATE_SQL"], tenant_id=B_TENANT, provider="telegram"),
        "{STATE_OUTRO}": ligar(fixas["_TELEGRAM_STATE_SQL"], tenant_id=B_OUTRO, provider="telegram"),
        "{WEBHOOK_PATCH}": ligar(fixas["_TELEGRAM_WEBHOOK_SQL"], tenant_id=B_TENANT, patch=patch).replace(
            "%(integration_id)s", v_bot
        ),
        "{HEALTH_CONNECTED}": medicao(B_TENANT, "connected", "webhook registrado"),
        "{HEALTH_DISCONNECTED}": medicao(B_TENANT, "disconnected", "setWebhook recusado: unauthorized"),
        "{HEALTH_DISCONNECTED_OUTRO}": medicao(B_OUTRO, "disconnected", "nao deveria gravar"),
        "{STATUS_WHATSAPP}": ligar(fixas["_CREDENTIAL_STATUS_SQL"], tenant_id=B_TENANT),
        "{STATUS_TELEGRAM}": ligar(fixas_tg["_CREDENTIAL_STATUS_SQL"], tenant_id=B_TENANT),
        "{DEACTIVATE_WHATSAPP}": ligar(fixas["_DEACTIVATE_SQL"], tenant_id=B_TENANT),
        "{DEACTIVATE_TELEGRAM}": ligar(fixas_tg["_DEACTIVATE_SQL"], tenant_id=B_TENANT),
        "{UPSERT_BOT}": ligar(
            fixas["_UPSERT_INTEGRATION_SQL"],
            tenant_id=B_TENANT,
            provider="telegram",
            config='{"public_identity": "@FastParkAlertasBot"}',
        ),
        "{CREATE_META_TOKEN}": cria(v_meta, "token"),
        "{CREATE_BOT_TOKEN}": cria(v_bot, "bot_token"),
    }
    script = CENARIO_TELEGRAM
    for marcador, texto in substituicoes.items():
        script = script.replace(marcador, texto)
    for nome, valor in {
        "{B_TENANT}": B_TENANT,
        "{B_OUTRO}": B_OUTRO,
        "{B_OWNER}": B_OWNER,
        "{B_PATH_TOKEN}": B_PATH_TOKEN,
        "{B_WEBHOOK_URL}": B_WEBHOOK_URL,
    }.items():
        script = script.replace(nome, valor)
    return script


def templates(fixas: dict[str, str]) -> str:
    """O cenário dos templates, com o SQL real de `canais.py` ligado aos valores."""
    corpo_ok = "FastPark: {{1}} com {{2}} ocorrencias."
    id_a = "(select id from app.message_template where tenant_id = '{T_TENANT}' and code = 'deviation_summary')"
    id_b = "(select id from app.message_template where tenant_id = '{T_OUTRO}')"

    def upsert(code: str, body: str, name: str | None, active: str = "true") -> str:
        return (
            ligar(
                fixas["_TEMPLATE_UPSERT_SQL"],
                tenant_id=T_TENANT,
                code=code,
                category="utility",
                language="pt_BR",
                body=body,
            )
            .replace("%(variables)s", "array['unit','occurrences']")
            .replace("%(meta_template_name)s", "null" if name is None else f"'{name}'")
            .replace("%(active)s", active)
        )

    def sync(ids: str, names: str, statuses: str, rejections: str) -> str:
        return (
            ligar(fixas["_SYNC_TEMPLATES_SQL"], tenant_id=T_TENANT)
            .replace("%(ids)s", ids)
            .replace("%(names)s", names)
            .replace("%(statuses)s", statuses)
            .replace("%(rejections)s", rejections)
        )

    def audit(action: str, entity_id: str, depois: str) -> str:
        return (
            ligar(
                fixas["_TEMPLATE_AUDIT_SQL"],
                tenant_id=T_TENANT,
                user_id=T_OWNER,
                action=action,
                depois=depois,
            )
            .replace("%(entity_id)s", entity_id)
            .replace("%(antes)s", "null")
        )

    substituicoes = {
        "{OFFICIAL}": ligar(fixas["_OFFICIAL_INTEGRATION_SQL"], tenant_id=T_TENANT, provider="meta_cloud"),
        "{OFFICIAL_OUTRO}": ligar(fixas["_OFFICIAL_INTEGRATION_SQL"], tenant_id=T_OUTRO, provider="meta_cloud"),
        "{TEMPLATES}": ligar(fixas["_TEMPLATES_SQL"], tenant_id=T_TENANT),
        "{TEMPLATES_OUTRO}": ligar(fixas["_TEMPLATES_SQL"], tenant_id=T_OUTRO),
        "{NAMED}": ligar(fixas["_NAMED_TEMPLATES_SQL"], tenant_id=T_TENANT),
        "{UPSERT_V1}": upsert("deviation_summary", corpo_ok, "deviation_summary_v1"),
        "{UPSERT_V2}": upsert("deviation_summary", corpo_ok, "deviation_summary_v2"),
        "{UPSERT_SEM_NOME}": upsert("deviation_summary", corpo_ok, None),
        "{UPSERT_SEM_2}": upsert("deviation_summary", "so {{1}}", "deviation_summary_v1"),
        "{UPSERT_INATIVO}": upsert("deviation_inactive", corpo_ok, "inactive_v1", active="false"),
        "{SYNC_APPROVED}": sync(
            f"array[{id_a}]::uuid[]", "array['deviation_summary_v1']", "array['approved']", "array[null]"
        ),
        "{SYNC_REJECTED}": sync(
            f"array[{id_a}]::uuid[]",
            "array['deviation_summary_v1']",
            "array['rejected']",
            "array['INVALID_FORMAT']",
        ),
        # O mesmo status, só a razão indo de valor para nulo: é o caso que separa
        # `is distinct from` de `<>` — com `<>`, nulo nunca é "diferente".
        "{SYNC_REJECTED_SEM_RAZAO}": sync(
            f"array[{id_a}]::uuid[]", "array['deviation_summary_v1']", "array['rejected']", "array[null]"
        ),
        # O veredito da WABA sobre o nome velho, chegando depois de um PUT que
        # renomeou: o nome está na chave do update, e nada é gravado.
        "{SYNC_NOME_VELHO}": sync(
            f"array[{id_a}]::uuid[]", "array['deviation_summary_v1']", "array['approved']", "array[null]"
        ),
        "{SYNC_CROSS}": sync(
            f"array[{id_a}, {id_b}]::uuid[]",
            "array['deviation_summary_v1','outro_v1']",
            "array['pending','pending']",
            "array[null,null]",
        ),
        "{AUDIT_SYNC}": audit(
            "update", "null", '{"updated": ["deviation_summary"], "unmatched": [], "meta_total": 1}'
        ),
        "{AUDIT_INSERT}": audit("insert", id_a + "::text", '{"code": "deviation_summary"}'),
    }
    script = CENARIO_TEMPLATES
    for marcador, texto in substituicoes.items():
        script = script.replace(marcador, texto)
    for nome, valor in {
        "{T_TENANT}": T_TENANT,
        "{T_OUTRO}": T_OUTRO,
        "{T_OWNER}": T_OWNER,
        "{T_OUTRO_OWNER}": T_OUTRO_OWNER,
        "{T_WABA}": T_WABA,
    }.items():
        script = script.replace(nome, valor)
    return script


def roteamento(outbox_sql: dict[str, str], sender_sql: dict[str, str], webhook_sql: dict[str, str]) -> str:
    """O cenário do roteamento e do sender, com o SQL real de `outbox.py`,
    `sender.py` e `webhooks.py` ligado aos valores."""

    def nulls(sql: str, *nomes: str) -> str:
        for nome in nomes:
            sql = sql.replace(f"%({nome})s", "null")
        return sql

    def targets(tenant: str) -> str:
        return ligar(
            outbox_sql["_TARGETS_SQL"],
            tenant_id=tenant,
            unit_id=R_UNIT,
            telegram_channel="telegram",
            telegram_providers="{telegram}",
            telegram_health="connected",
        )

    def park(queue_id: str) -> str:
        return ligar(sender_sql["_PARK_SQL"], tenant_id=R_TENANT, queue_id=queue_id)

    def claim() -> str:
        return ligar(sender_sql["_CLAIM_SQL"], tenant_id=R_TENANT, batch="50", stuck_minutes="10")

    def mark_sent(queue_id: str) -> str:
        return ligar(sender_sql["_MARK_SENT_SQL"], tenant_id=R_TENANT, queue_id=queue_id)

    def mark_failed(queue_id: str, wait: str) -> str:
        return ligar(
            sender_sql["_MARK_FAILED_SQL"],
            tenant_id=R_TENANT,
            queue_id=queue_id,
            max_attempts="5",
            wait_minutes=wait,
        )

    def holder(tenant: str, chat: str) -> str:
        return ligar(
            sender_sql["_IDENTITY_HOLDER_SQL"], tenant_id=tenant, channel="telegram", external_id=chat
        )

    def reroute(queue_id: str, contact_id: str, provider: str = "z_api") -> str:
        return ligar(
            sender_sql["_REROUTE_SQL"],
            tenant_id=R_TENANT,
            queue_id=queue_id,
            contact_id=contact_id,
            channel="whatsapp",
            provider=provider,
        )

    def log(
        tenant: str, queue_id: str | None, channel: str, provider: str, status: str, error: str | None
    ) -> str:
        sql = ligar(
            sender_sql["_LOG_SQL"],
            tenant_id=tenant,
            channel=channel,
            provider=provider,
            destination_hash="f" * 64,
            provider_message_id="m-1",
            status=status,
        )
        sql = sql.replace("%(queue_id)s", "null" if queue_id is None else f"'{queue_id}'")
        sql = sql.replace("%(error)s", "null" if error is None else f"'{error}'")
        return nulls(sql, "rule_id", "cost_cents")

    revoke = ligar(
        webhook_sql["_REVOKE_PREVIOUS_SQL"],
        tenant_id=R_TENANT,
        channel="telegram",
        reason="bloqueou o bot",
        contact_id=R_ADERIU,
    )
    revoke = nulls(revoke, "employee_id")
    audit = ligar(
        sender_sql["_AUDIT_SQL"],
        tenant_id=R_TENANT,
        depois='{"channel": "telegram", "reason": "bloqueou o bot"}',
    )
    substituicoes = {
        "{TARGETS_OUTRO}": targets(R_OUTRO),
        "{TARGETS}": targets(R_TENANT),
        "{WAITING}": ligar(sender_sql["_WAITING_SQL"], tenant_id=R_TENANT),
        "{CLAIM}": claim(),
        "{TEMPLATE}": ligar(sender_sql["_TEMPLATE_SQL"], tenant_id=R_TENANT, code="deviation_summary"),
        "{INTEGRATIONS_OUTRO}": ligar(
            sender_sql["_INTEGRATIONS_SQL"], tenant_id=R_OUTRO, providers="{" + provider_list_plain() + "}"
        ),
        "{INTEGRATIONS}": ligar(
            sender_sql["_INTEGRATIONS_SQL"], tenant_id=R_TENANT, providers="{" + provider_list_plain() + "}"
        ),
        "{MARK_SENT_INVITE}": mark_sent(Q_INVITE),
        "{MARK_SENT_WHATSAPP}": mark_sent(Q_WHATSAPP),
        "{MARK_FAILED_5}": mark_failed(Q_INVITE_5, "360"),
        "{MARK_FAILED_1}": mark_failed(Q_INVITE_1, "1"),
        "{HOLDER_ADERIU}": holder(R_TENANT, R_CHAT_ADERIU),
        "{HOLDER_REVOGOU}": holder(R_TENANT, R_CHAT_REVOGOU),
        "{HOLDER_INVENTADO}": holder(R_TENANT, "000000000000"),
        "{HOLDER_OUTRO}": holder(R_OUTRO, R_CHAT_ADERIU),
        "{LOG_BLOCKED}": log(R_TENANT, Q_TELEGRAM, "telegram", "telegram", "failed", "blocked"),
        "{PARK_TELEGRAM}": park(Q_TELEGRAM),
        "{PARK_SEM_NUMERO}": park(Q_SEM_NUMERO),
        "{PARK_RECUSADA}": park(Q_RECUSADA),
        "{REROUTE_META}": reroute(Q_RECUSADA, R_ADERIU, "meta_cloud"),
        "{LOG_REFUSED}": log(
            R_TENANT, Q_RECUSADA, "whatsapp", "meta_cloud", "failed",
            "reroute_refused: Template deviation_summary está draft e o provedor é meta_cloud.",
        ),
        "{DISCARD_RECUSADA}": ligar(sender_sql["_DISCARD_SQL"], tenant_id=R_TENANT, queue_id=Q_RECUSADA),
        "{REVOKE_ADERIU}": revoke,
        "{AUDIT}": audit,
        "{PROVIDER}": ligar(outbox_sql["_PROVIDER_SQL"], tenant_id=R_TENANT),
        "{REROUTE_ADERIU}": reroute(Q_TELEGRAM, R_ADERIU),
        "{REROUTE_SEM_NUMERO}": reroute(Q_SEM_NUMERO, R_SEM_NUMERO),
        "{DISCARD_SEM_NUMERO}": ligar(sender_sql["_DISCARD_SQL"], tenant_id=R_TENANT, queue_id=Q_SEM_NUMERO),
        "{LOG_META}": log(R_TENANT, None, "whatsapp", "meta_cloud", "sent", None),
        "{LOG_ZAPI}": log(R_TENANT, Q_WHATSAPP, "whatsapp", "z_api", "sent", None),
        "{LOG_UAZAPI}": log(R_TENANT, None, "whatsapp", "uazapi", "sent", None),
        "{LOG_OUTRO}": log(R_OUTRO, None, "whatsapp", "uazapi", "sent", None),
    }
    script = CENARIO_ROTEAMENTO
    for marcador, texto in substituicoes.items():
        script = script.replace(marcador, texto)
    for nome, valor in {
        "{R_TENANT}": R_TENANT,
        "{R_OUTRO}": R_OUTRO,
        "{R_OWNER}": R_OWNER,
        "{R_OUTRO_OWNER}": R_OUTRO_OWNER,
        "{R_COMPANY}": R_COMPANY,
        "{R_UNIT}": R_UNIT,
        "{R_RULE}": R_RULE,
        "{R_ADERIU}": R_ADERIU,
        "{R_REVOGOU}": R_REVOGOU,
        "{R_SEM}": R_SEM,
        "{R_SEM_NUMERO}": R_SEM_NUMERO,
        "{R_BOT}": R_BOT,
        "{R_ZAPI}": R_ZAPI,
        "{R_CHAT_ADERIU}": R_CHAT_ADERIU,
        "{R_CHAT_REVOGOU}": R_CHAT_REVOGOU,
        "{R_CHAT_SEM_NUMERO}": R_CHAT_SEM_NUMERO,
        "{Q_TELEGRAM}": Q_TELEGRAM,
        "{Q_WHATSAPP}": Q_WHATSAPP,
        "{Q_INVITE}": Q_INVITE,
        "{Q_PRESA}": Q_PRESA,
        "{Q_FRESCA}": Q_FRESCA,
        "{Q_FUTURA}": Q_FUTURA,
        "{Q_INVITE_5}": Q_INVITE_5,
        "{Q_INVITE_1}": Q_INVITE_1,
        "{Q_SEM_NUMERO}": Q_SEM_NUMERO,
        "{Q_RECUSADA}": Q_RECUSADA,
        "{R_META}": R_META,
        "{R_UAZAPI_INATIVA}": R_UAZAPI_INATIVA,
        "{R_SECULLUM}": R_SECULLUM,
        "{R_INVITE_LINK}": R_INVITE_LINK,
    }.items():
        script = script.replace(nome, valor)
    return script


def provider_list_plain() -> str:
    """`meta_cloud,z_api,uazapi,telegram` — o array de `CHANNEL_PROVIDERS` como o
    driver o renderiza para `%(providers)s`."""
    return ",".join(_capacidades().CHANNEL_PROVIDERS)


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
    fixas_tg = instrucoes(channel="telegram")
    cofre = instrucoes(COFRE)
    saude = instrucoes(SAUDE)
    webhook_sql = instrucoes(WEBHOOK)
    # As três de `outbox.py` que a rota do convite importa. `_TARGETS_SQL` fica
    # com o `93`. O `{whatsapp_providers}` é renderizado como o módulo o renderiza.
    outbox_sql = {
        nome: sql.replace("{whatsapp_providers}", whatsapp_providers())
        for nome, sql in instrucoes(OUTBOX).items()
        if nome in ("_PROVIDER_SQL", "_TEMPLATE_SQL", "_ENQUEUE_SQL")
    }
    # O C5: `_TARGETS_SQL` do outbox (que o `93` só compila) e as doze do sender.
    outbox_rota = {
        nome: sql.replace("{whatsapp_providers}", whatsapp_providers())
        for nome, sql in instrucoes(OUTBOX).items()
        if nome in ("_TARGETS_SQL", "_PROVIDER_SQL")
    }
    sender_sql = instrucoes(SENDER)
    # Só a do webhook: as outras três de `tenant.py` são o bootstrap e o
    # `set_config`, que nenhum cenário daqui executa.
    tenant_sql = {
        nome: sql for nome, sql in instrucoes(TENANT_PY).items() if nome == "_WEBHOOK_INTEGRATION_SQL"
    }
    esperadas = {
        "_READINESS_SQL",
        "_BLOCKED_SQL",
        "_TELEGRAM_STATE_SQL",
        "_PERMISSION_SQL",
        "_CREDENTIAL_STATUS_SQL",
        "_DEACTIVATE_SQL",
        "_UPSERT_INTEGRATION_SQL",
        "_AUDIT_SQL",
        "_TELEGRAM_WEBHOOK_SQL",
        "_TEMPLATES_SQL",
        "_TEMPLATE_UPSERT_SQL",
        "_OFFICIAL_INTEGRATION_SQL",
        "_NAMED_TEMPLATES_SQL",
        "_SYNC_TEMPLATES_SQL",
        "_TEMPLATE_AUDIT_SQL",
        "_VISIBLE_EMPLOYEE_SQL",
        "_VISIBLE_CONTACT_SQL",
        "_EMPLOYEE_PHONE_SQL",
        "_CONTACT_PHONE_SQL",
        "_EXPIRE_OPEN_INVITES_SQL",
        "_INSERT_INVITE_SQL",
        "_ADHESION_AUDIT_SQL",
        "_LINK_SQL",
    }
    if set(fixas) != esperadas:
        print(f"  ✖ esperava as instruções {sorted(esperadas)} em canais.py, achei {sorted(fixas)}")
        sys.exit(1)
    esperadas_cofre = {"_UPDATE_SQL", "_CREATE_SQL", "_READ_SQL"}
    if set(cofre) != esperadas_cofre:
        print(f"  ✖ esperava {sorted(esperadas_cofre)} em vault.py, achei {sorted(cofre)}")
        sys.exit(1)
    if set(saude) != {"RECORD_HEALTH_SQL"}:
        print(f"  ✖ esperava RECORD_HEALTH_SQL em saude.py, achei {sorted(saude)}")
        sys.exit(1)
    esperadas_webhook = {
        "_INVITE_SQL",
        "_CONSUME_INVITE_SQL",
        "_REVOKE_PREVIOUS_SQL",
        "_INSERT_IDENTITY_SQL",
        "_AUDIT_SQL",
    }
    if set(webhook_sql) != esperadas_webhook:
        print(f"  ✖ esperava {sorted(esperadas_webhook)} em webhooks.py, achei {sorted(webhook_sql)}")
        sys.exit(1)
    if set(tenant_sql) != {"_WEBHOOK_INTEGRATION_SQL"}:
        print("  ✖ _WEBHOOK_INTEGRATION_SQL não está em tenant.py")
        sys.exit(1)
    if set(outbox_sql) != {"_PROVIDER_SQL", "_TEMPLATE_SQL", "_ENQUEUE_SQL"}:
        print(f"  ✖ esperava as três instruções do convite em outbox.py, achei {sorted(outbox_sql)}")
        sys.exit(1)
    esperadas_sender = {
        "_GATE_SQL",
        "_WAITING_SQL",
        "_CLAIM_SQL",
        "_TEMPLATE_SQL",
        "_INTEGRATIONS_SQL",
        "_MARK_SENT_SQL",
        "_MARK_FAILED_SQL",
        "_PARK_SQL",
        "_DISCARD_SQL",
        "_IDENTITY_HOLDER_SQL",
        "_AUDIT_SQL",
        "_REROUTE_SQL",
        "_LOG_SQL",
    }
    if set(sender_sql) != esperadas_sender:
        print(f"  ✖ esperava {sorted(esperadas_sender)} em sender.py, achei {sorted(sender_sql)}")
        sys.exit(1)
    if set(outbox_rota) != {"_TARGETS_SQL", "_PROVIDER_SQL"}:
        print("  ✖ _TARGETS_SQL ou _PROVIDER_SQL não está em outbox.py")
        sys.exit(1)
    # ⛔ O titular pelo chat_id não seleciona o chat_id; o log não guarda destino.
    if "external_id" in sender_sql["_IDENTITY_HOLDER_SQL"].split("from")[0]:
        print("  ✖ _IDENTITY_HOLDER_SQL seleciona external_id")
        sys.exit(1)
    # ⛔ O chat_id nunca sai (SPEC-CANAIS §3.2): a ficha não seleciona a coluna.
    if "external_id" in fixas["_LINK_SQL"]:
        print("  ✖ _LINK_SQL seleciona external_id — o chat_id não sai por rota nenhuma")
        sys.exit(1)
    # As duas que existem por canal: a renderização do bot também tem de compilar.
    por_canal = {nome: fixas_tg[nome] for nome in ("_CREDENTIAL_STATUS_SQL", "_DEACTIVATE_SQL")}
    if any("{channel_providers}" in sql for sql in (*fixas.values(), *fixas_tg.values())):
        print("  ✖ sobrou um `{channel_providers}` sem renderizar")
        sys.exit(1)

    problemas: list[str] = []
    for origem, lote in (
        ("canais.py", fixas),
        ("canais.py[telegram]", por_canal),
        ("vault.py", cofre),
        ("saude.py", saude),
        ("webhooks.py", webhook_sql),
        ("tenant.py", tenant_sql),
        ("outbox.py", outbox_sql),
    ):
        for nome, sql in lote.items():
            r = psql(["-c", f"prepare p as {posicionar(sql)}"])
            if r.returncode != 0:
                # `stderr` vazio é o psql que nem subiu (wrapper sem Docker):
                # a primeira linha de qualquer saída é melhor que um IndexError.
                saida = (r.stderr.strip() or r.stdout.strip() or "(sem saída)").splitlines()[0]
                problemas.append(f"{origem}:{nome} não compila: {saida}")
    if problemas:
        for p in problemas:
            print(f"  ✖ {p}")
        sys.exit(1)
    print(
        f"  instruções fixas compiladas: {len(fixas)} de canais.py "
        f"(+{len(por_canal)} na renderização do bot), {len(cofre)} de vault.py, "
        f"{len(saude)} de saude.py, {len(webhook_sql)} de webhooks.py, {len(tenant_sql)} de tenant.py, "
        f"{len(outbox_sql)} de outbox.py"
    )

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

    print("\n--- os templates, contra o gatilho, o upsert e a policy de verdade")
    rodar(templates(fixas))

    print("\n--- o bot, com os dois canais ativos lado a lado")
    rodar(telegram_bot(fixas, fixas_tg, cofre, saude))

    print("\n--- o webhook /start: resolução por path_token, convite, identidade e auditoria")
    rodar(webhook(webhook_sql, tenant_sql))

    print("\n--- o convite de adesão: titular, número, as quatro condições, a fila pelo gatilho, a ficha")
    rodar(convite(fixas, outbox_sql, webhook_sql))

    print("\n--- o roteamento e o sender: as entradas de route, a reserva, o scrub, o blocked, o relatório")
    rodar(roteamento(outbox_rota, sender_sql, webhook_sql))

    print("\n================================================")
    print(" CONEXÕES, CREDENCIAL, TEMPLATES, BOT, WEBHOOK, CONVITE E ROTEAMENTO: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
