#!/usr/bin/env bash
# Prova a fronteira de segurança por HTTP, contra o PostgREST de verdade.
#
#   SUPABASE_PUBLISHABLE_KEY=sb_publishable_... \
#   SUPABASE_SECRET_KEY=sb_secret_... \
#   scripts/provar_postgrest.sh wbzaqjlfpqteesehapnn
#
# As suítes 97/98/99 provam a RLS dentro do banco, com `set local role`. Isto
# prova o caminho que o navegador realmente percorre: Kong, a chave de API, o
# GoTrue emitindo o JWT, o PostgREST resolvendo o role e a view rodando como o
# usuário. Um `security_invoker` esquecido, um schema exposto por engano ou um
# grant largo demais só aparecem aqui.
#
# ⚠️ ESCREVE no projeto: cria quatro usuários no Auth e o cenário de dois tenants
#    da suíte 98, e derruba os dois no fim. Não rode contra produção.
#
# O cenário NÃO é digitado aqui — é extraído de scripts/98_teste_isolamento_tenant.sql,
# para não existirem duas versões dele que possam divergir.
set -uo pipefail
REF="${1:?uso: $0 <project-ref>}"
: "${SUPABASE_PUBLISHABLE_KEY:?defina SUPABASE_PUBLISHABLE_KEY}"
: "${SUPABASE_SECRET_KEY:?defina SUPABASE_SECRET_KEY}"
cd "$(dirname "$0")/.."

[ "$REF" = "nklobmlxyidqxarzisph" ] && { echo "recusa: esse é o projeto de produção"; exit 2; }

URL="https://$REF.supabase.co"
PUB="$SUPABASE_PUBLISHABLE_KEY"
SEC="$SUPABASE_SECRET_KEY"
SENHA="ensaio-postgrest-9f2"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
falhou=0

passo() { printf '\n=== %s\n' "$1"; }
ok()    { printf '  ok    %-54s %s\n' "$1" "${2:-}"; }
falha() { printf '  FALHA %-54s %s\n' "$1" "$2"; falhou=1; }
verifica() { [ "$2" = "$3" ] && ok "$1" "$3" || falha "$1" "esperado [$2], obtido [$3]"; }

codigo() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
# quantas linhas o PostgREST devolveu, ou 'erro' se não foi um array
linhas() { curl -s "$@" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(len(d) if isinstance(d, list) else "erro")
except Exception:
    print("erro")'; }
# os valores de uma coluna, ordenados e unidos por vírgula
valores() { local col="$1"; shift; curl -s "$@" | python3 -c "import json,sys
try:
    d = json.load(sys.stdin)
    print(','.join(sorted(str(r.get('$col')) for r in d)) if isinstance(d, list) else 'erro')
except Exception:
    print('erro')"; }

anon()  { curl -s "$@" -H "apikey: $PUB"; }
como()  { local tok="$1"; shift; curl -s "$@" -H "apikey: $PUB" -H "Authorization: Bearer $tok"; }

# ---------------------------------------------------------------------------
USUARIOS="11111111-1111-1111-1111-111111111111:owner.a@teste.local
22222222-2222-2222-2222-222222222222:supervisor.a@teste.local
33333333-3333-3333-3333-333333333333:dp.a@teste.local
44444444-4444-4444-4444-444444444444:owner.b@teste.local"

derrubar() {
  while IFS=: read -r id _; do
    curl -s -o /dev/null -X DELETE "$URL/auth/v1/admin/users/$id" \
      -H "apikey: $SEC" -H "Authorization: Bearer $SEC"
  done <<< "$USUARIOS"
  ./scripts/sb_sql.sh "$REF" "
    delete from app.deviation_event      where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.employee_pii         where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.employee             where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.user_scope           where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.unit                 where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.company              where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.tenant_member        where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.domain_permission    where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.deviation_type_config where tenant_id in (select id from app.tenant where slug in ('tenant-a','tenant-b'));
    delete from app.tenant               where slug in ('tenant-a','tenant-b');" >/dev/null 2>&1
}

passo "1. limpando resíduo de execução anterior"
derrubar; echo "  feito"

passo "2. criando os quatro usuários no Auth de verdade"
while IFS=: read -r id email; do
  resp=$(curl -s -X POST "$URL/auth/v1/admin/users" \
    -H "apikey: $SEC" -H "Authorization: Bearer $SEC" -H "Content-Type: application/json" \
    -d "{\"id\":\"$id\",\"email\":\"$email\",\"password\":\"$SENHA\",\"email_confirm\":true}")
  devolvido=$(echo "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)
  verifica "criado $email" "$id" "$devolvido"
done <<< "$USUARIOS"

passo "3. montando o cenário da suíte 98 (extraído dela, não copiado)"
python3 - "$TMP/cenario.sql" <<'PY'
import re, sys, pathlib
fonte = pathlib.Path("scripts/98_teste_isolamento_tenant.sql").read_text()
ini = fonte.index("-- Cenário")
fim = fonte.index("-- Utilitário de asserção")
sql = fonte[ini:fim]
# O Auth já criou os usuários, com senha e e-mail confirmado. O insert direto em
# auth.users da suíte criaria linhas sem credencial, que não fazem login.
sql = re.sub(r"insert into auth\.users .*?;\n", "", sql, flags=re.S)
assert "auth.users" not in sql, "o insert em auth.users não saiu"
assert "app.tenant_member" in sql, "o cenário não veio inteiro"
pathlib.Path(sys.argv[1]).write_text(sql)
PY
saida=$(./scripts/sb_sql.sh "$REF" -f "$TMP/cenario.sql" 2>&1)
case "$saida" in \[*) ok "cenário aplicado";; *) falha "cenário" "$(echo "$saida" | head -c 300)";; esac

passo "4. fazendo login de verdade, pelo GoTrue"
declare -A TOKEN
while IFS=: read -r id email; do
  tok=$(curl -s -X POST "$URL/auth/v1/token?grant_type=password" \
    -H "apikey: $PUB" -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$SENHA\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
  TOKEN[$email]="$tok"
  [ -n "$tok" ] && ok "sessão de $email" "${#tok} chars" || falha "sessão de $email" "sem access_token"
done <<< "$USUARIOS"
OA="${TOKEN[owner.a@teste.local]}"; SA="${TOKEN[supervisor.a@teste.local]}"
DP="${TOKEN[dp.a@teste.local]}";    OB="${TOKEN[owner.b@teste.local]}"

passo "5. anon não lê nada — com a chave publicável e sem sessão"
for v in vw_unit vw_employee vw_deviation_event vw_deviation_summary_by_unit; do
  verifica "anon em $v" "401" "$(codigo -H "apikey: $PUB" "$URL/rest/v1/$v?select=*")"
done
verifica "sem apikey nenhuma" "401" "$(codigo "$URL/rest/v1/vw_unit?select=*")"

passo "6. schema fora de db_schema não existe — nem para a chave de serviço"
for par in "app:employee" "secullum:Funcionario" "util:is_admin"; do
  s="${par%%:*}"; o="${par##*:}"
  verifica "$s.$o via Accept-Profile" "406" \
    "$(codigo -H "apikey: $SEC" -H "Authorization: Bearer $SEC" -H "Accept-Profile: $s" "$URL/rest/v1/$o?select=*&limit=1")"
done
verifica "matview app.mv_deviation_day" "404" \
  "$(codigo -H "apikey: $SEC" -H "Authorization: Bearer $SEC" "$URL/rest/v1/mv_deviation_day?select=*&limit=1")"

passo "7. cada sessão vê o seu recorte, e só ele"
verifica "owner A: units"        "A Centro,A Norte" "$(valores name -H "apikey: $PUB" -H "Authorization: Bearer $OA" "$URL/rest/v1/vw_unit?select=name")"
verifica "owner B: units"        "B Sul"            "$(valores name -H "apikey: $PUB" -H "Authorization: Bearer $OB" "$URL/rest/v1/vw_unit?select=name")"
verifica "supervisor A: units"   "A Centro"         "$(valores name -H "apikey: $PUB" -H "Authorization: Bearer $SA" "$URL/rest/v1/vw_unit?select=name")"
verifica "owner A: employees"    "Colab A Centro,Colab A Norte" "$(valores name -H "apikey: $PUB" -H "Authorization: Bearer $OA" "$URL/rest/v1/vw_employee?select=name")"
verifica "supervisor A: employees" "Colab A Centro" "$(valores name -H "apikey: $PUB" -H "Authorization: Bearer $SA" "$URL/rest/v1/vw_employee?select=name")"
verifica "owner B: employees"    "Colab B Sul"      "$(valores name -H "apikey: $PUB" -H "Authorization: Bearer $OB" "$URL/rest/v1/vw_employee?select=name")"

passo "8. filtro do cliente não fura a policy"
# O cliente pede explicitamente o tenant do outro. A policy não confia no
# parâmetro: ela já decidiu antes de o filtro ser aplicado.
tb=$(./scripts/sb_sql.sh "$REF" "select id from app.tenant where slug='tenant-b';" \
     | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
verifica "owner A pedindo tenant_id de B" "0" \
  "$(linhas -H "apikey: $PUB" -H "Authorization: Bearer $OA" "$URL/rest/v1/vw_employee?select=name&tenant_id=eq.$tb")"

passo "9. PII não está na superfície"
verifica "vw_employee?select=cpf" "400" \
  "$(codigo -H "apikey: $PUB" -H "Authorization: Bearer $OA" "$URL/rest/v1/vw_employee?select=cpf")"

passo "10. escrita pela superfície pública"
# `authenticated` TEM grant de insert nas views: a ACL de produção é `arwdDxtm`,
# porque o privilégio default do Supabase concede tudo em `public`. O que impede
# a escrita não é esse grant, e não é a RLS — é que nenhuma das views seleciona
# de uma relação só, então o Postgres recusa antes de consultar policy alguma
# ("Views that do not select from a single table are not automatically updatable").
#
# Por isso a asserção é sobre a CAUSA, e não sobre o 4xx: no dia em que alguém
# publicar em `public` uma view de tabela única, ela nasce gravável pelo
# navegador e só a RLS ficará entre os dois. Aqui isso vira vermelho.
gravaveis=$(./scripts/sb_sql.sh "$REF" \
  "select count(*) from information_schema.views
    where table_schema='public' and is_insertable_into='YES';" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["count"])')
verifica "nenhuma view de public é gravável" "0" "$gravaveis"
esc=$(codigo -X POST -H "apikey: $PUB" -H "Authorization: Bearer $OA" -H "Content-Type: application/json" \
      -d '{"name":"Unidade Intrusa"}' "$URL/rest/v1/vw_unit")
case "$esc" in
  20*) falha "insert em vw_unit pelo navegador" "aceitou ($esc) — a superfície pública é gravável";;
  *)   ok "insert em vw_unit pelo navegador" "recusado ($esc)";;
esac

passo "11. RPC do dashboard"
rpc=$(codigo -X POST -H "apikey: $PUB" -H "Authorization: Bearer $OA" -H "Content-Type: application/json" \
      -d '{"p_de":"2026-08-01","p_ate":"2026-08-31"}' "$URL/rest/v1/rpc/fn_kpi_period")
verifica "fn_kpi_period com sessão" "200" "$rpc"
verifica "fn_kpi_period sem sessão" "401" \
  "$(codigo -X POST -H "apikey: $PUB" -H "Content-Type: application/json" \
     -d '{"p_de":"2026-08-01","p_ate":"2026-08-31"}' "$URL/rest/v1/rpc/fn_kpi_period")"

passo "12. desmontando"
derrubar
sobrou=$(./scripts/sb_sql.sh "$REF" "select count(*) from app.tenant where slug in ('tenant-a','tenant-b');" \
         | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["count"])')
verifica "tenants de teste removidos" "0" "$sobrou"

[ "$falhou" -eq 0 ] && echo -e "\n=== POSTGREST OK ===" || { echo -e "\n=== POSTGREST FALHOU ==="; exit 1; }
