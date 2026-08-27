#!/usr/bin/env bash
# Ensaia o rename num projeto Supabase de verdade, não num Postgres descartável.
#
#   scripts/ensaiar_rename_staging.sh <ref-do-staging> [<ref-da-origem>]
#
# O ensaio local (scripts/ensaiar_rename_nuvem.sh) prova o SQL. Este prova o que
# só existe num projeto: os roles do Supabase, `auth.users` de verdade, os
# privilégios default da plataforma, o PostgREST com `db_schema` configurado, e
# a forma em que o PostgREST entrega o claim — um JSON em `request.jwt.claims`,
# não a chave achatada que as suítes locais usam.
#
# ⚠️ APAGA os schemas app/secullum/util do <ref-do-staging> e os recria. O
#    <ref-da-origem> é só lido, e só do catálogo.
#
# Passa quando: a cópia é fiel campo a campo à origem, o catálogo renomeado é
# idêntico ao que as 17 migrations produzem, e as quatro suítes ficam verdes.
set -uo pipefail
STG="${1:?uso: $0 <ref-do-staging> [<ref-da-origem>]}"
ORIG="${2:-nklobmlxyidqxarzisph}"
cd "$(dirname "$0")/.."
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
falhou=0
passo() { printf '\n=== %s\n' "$1"; }
sql()   { ./scripts/sb_sql.sh "$STG" "$@"; }

[ "$STG" = "$ORIG" ] && { echo "recusa: staging e origem são o mesmo projeto"; exit 2; }

passo "1. lendo o catálogo da origem ($ORIG)"
python3 scripts/introspeccao_nuvem.py "$ORIG" \
  --out "$TMP/origem.sql" --json "$TMP/origem.json" | tail -1 || exit 1

passo "2. esvaziando o staging ($STG)"
# `drop schema` nao alcanca o que mora em `public`, e la vivem as views e as
# RPCs. Sem derrubar as funcoes tambem, uma rodada anterior deixa a versao em
# ingles para tras e a rodada seguinte comeca com o banco misto — que foi
# exatamente como este ensaio descobriu que a guarda de colisao nao via funcao.
sql "do \$\$ declare r record; begin
       for r in select viewname from pg_views where schemaname='public' loop
         execute format('drop view if exists public.%I cascade', r.viewname); end loop;
       for r in select p.oid::regprocedure::text as sig from pg_proc p
                join pg_namespace n on n.oid = p.pronamespace
                where n.nspname = 'public'
                  and not exists (select 1 from pg_depend d
                                   where d.objid = p.oid and d.deptype = 'e') loop
         execute format('drop function if exists %s cascade', r.sig); end loop; end \$\$;
     drop schema if exists app cascade;
     drop schema if exists secullum cascade;
     drop schema if exists util cascade;" >/dev/null || exit 1
# e o ensaio so comeca de um staging comprovadamente vazio
vazio=$(sql "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
             where n.nspname in ('app','secullum','util') or (n.nspname='public' and c.relkind in ('r','v','m'));" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["count"])')
sobrou_fn=$(sql "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public';" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["count"])')
echo "  relações restantes: $vazio · funções em public: $sobrou_fn"
[ "$vazio" = "0" ] && [ "$sobrou_fn" = "0" ] || { echo "  o staging não ficou vazio — abortando"; exit 1; }

passo "3. montando a cópia e conferindo se ela é a origem"
sql -f "$TMP/origem.sql" >/dev/null || { echo "  o schema não aplicou"; exit 1; }
python3 scripts/introspeccao_nuvem.py "$STG" --out /dev/null --json "$TMP/copia.json" >/dev/null 2>&1
python3 scripts/conferir_copia.py "$TMP/origem.json" "$TMP/copia.json" | tail -20 || falhou=1

passo "4. carregando as linhas de configuração da origem"
python3 scripts/extrair_config_nuvem.py "$ORIG" > "$TMP/config.sql"
sql -f "$TMP/config.sql" >/dev/null && echo "  ok" || falhou=1

# ⛔ A lista sai de `ls`, e não de um glob escrito à mão. O glob anterior
#    nomeava 11b e 12–15; o repositório passou de 15 e o ensaio continuou
#    provando cinco migrations enquanto a janela ia aplicar dezessete. Um
#    ensaio que não acompanha o repositório prova o passado com cara de
#    presente. Daqui em diante ele aplica tudo da 11b para a frente, e cresce
#    sozinho quando uma migration nova entra.
passo "5. aplicando o rename e TODAS as migrations a partir dele"
LOTE=$(ls supabase/migrations/*.sql | sed -n '/11b/,$p')
echo "  $(printf '%s\n' "$LOTE" | wc -l) migrations no lote"
for f in $LOTE; do
  printf '  %-56s ' "$(basename "$f")"
  saida=$(sql -f "$f" 2>&1)
  case "$saida" in \[*) echo "ok";; *) echo "FALHOU"; echo "$saida" | head -c 400; falhou=1;; esac
done

passo "6. comportamento — inclusive na forma em que o PostgREST entrega o claim"
# As suítes usam `set local request.jwt.claim.sub`. O PostgREST real usa
# `request.jwt.claims`, um JSON. `auth.uid()` aceita os dois, e sem esta
# variante o ensaio prova só o braço que a produção não usa.
python3 - "$TMP" <<'PY'
import re, sys, pathlib
tmp = pathlib.Path(sys.argv[1])
for nome in ("97_teste_regras_alerta", "98_teste_isolamento_tenant", "99_verificacao_rls"):
    s = "\n".join(l for l in pathlib.Path(f"scripts/{nome}.sql").read_text().splitlines()
                  if not l.startswith("\\"))
    (tmp / f"{nome}.sql").write_text(s)
    if nome == "98_teste_isolamento_tenant":
        v, n = re.subn(
            r"set local request\.jwt\.claim\.sub = '([0-9a-f-]+)';",
            lambda m: ('set local request.jwt.claims = \'{"sub":"%s",'
                       '"role":"authenticated","aud":"authenticated"}\';' % m.group(1)),
            s)
        assert "request.jwt.claim.sub" not in v and n, "a conversão do claim não pegou"
        (tmp / "98_postgrest.sql").write_text(v)
PY
for t in 97_teste_regras_alerta 98_teste_isolamento_tenant 99_verificacao_rls 98_postgrest; do
  printf '  %-32s ' "$t"
  saida=$(sql -f "$TMP/$t.sql" 2>&1)
  case "$saida" in \[*) echo "ok";; *) echo "FALHOU"; echo "$saida" | head -c 500; falhou=1;; esac
done

passo "7. o catálogo renomeado é o das 17 migrations?"
if [ -r scripts/_alvo_en.json ]; then
  python3 scripts/introspeccao_nuvem.py "$STG" --out /dev/null --json "$TMP/depois.json" >/dev/null 2>&1
  python3 scripts/comparar_catalogos.py "$TMP/depois.json" scripts/_alvo_en.json || falhou=1
else
  echo "  pulado: rode scripts/ensaiar_rename_nuvem.sh antes para gerar scripts/_alvo_en.json"
  falhou=1
fi

passo "8. a fronteira por HTTP, no PostgREST de verdade"
# Só com as duas chaves do projeto em mão. Sem elas o ensaio segue válido — só
# não alcança Kong, GoTrue nem o PostgREST, que é onde o navegador vive.
if [ -n "${SUPABASE_PUBLISHABLE_KEY:-}" ] && [ -n "${SUPABASE_SECRET_KEY:-}" ]; then
  ./scripts/provar_postgrest.sh "$STG" | sed -n '/=== 5/,$p' || falhou=1
else
  echo "  pulado: defina SUPABASE_PUBLISHABLE_KEY e SUPABASE_SECRET_KEY do staging"
fi

[ "$falhou" -eq 0 ] && echo -e "\n=== ENSAIO EM PROJETO REAL OK ===" \
                    || { echo -e "\n=== ENSAIO EM PROJETO REAL FALHOU ==="; exit 1; }
