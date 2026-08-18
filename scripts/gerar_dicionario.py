#!/usr/bin/env python3
"""
Gera docs/DICIONARIO-DE-DADOS.md por introspecção do banco.

Rodar SEMPRE a partir do banco de teste recém-migrado (ou do projeto real),
nunca escrever o dicionário à mão: documentação que diverge do schema é pior
que documentação nenhuma.

    ./scripts/testar_migrations.sh && python3 scripts/gerar_dicionario.py
"""
import subprocess, collections, os, sys

PSQL = ["psql", "-tAF\t", "-v", "ON_ERROR_STOP=1"]
ENV = {**os.environ,
       "PGHOST": os.environ.get("PGHOST", "/tmp"),
       "PGPORT": os.environ.get("PGPORT", "5433"),
       "PGUSER": os.environ.get("PGUSER", "postgres"),
       "PGDATABASE": os.environ.get("PGDATABASE", "operax_test")}


def q(sql, ncols=None):
    """Executa e devolve linhas como listas de strings.

    Cuidado deliberado: NÃO usar strip() no stdout inteiro. Quando a última
    coluna da última linha é vazia (comentário ausente), o strip come o
    separador final e a linha volta com um campo a menos.
    """
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        sys.exit(f"psql falhou:\n{r.stderr}")
    linhas = [l for l in r.stdout.split("\n") if l.strip()]
    saida = [l.split("\t") for l in linhas]
    if ncols:
        saida = [row + [""] * (ncols - len(row)) for row in saida]
    return saida


SCHEMAS = "('app','secullum','util','public')"

colunas = q(f"""
select n.nspname, c.relname, a.attnum, a.attname,
       format_type(a.atttypid, a.atttypmod),
       case when a.attnotnull then 'NOT NULL' else '' end,
       coalesce(pg_get_expr(d.adbin, d.adrelid), ''),
       coalesce(col_description(c.oid, a.attnum), '')
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
left join pg_attrdef d on d.adrelid = c.oid and d.adnum = a.attnum
where n.nspname in {SCHEMAS} and c.relkind in ('r','v','m','p')
order by n.nspname, c.relname, a.attnum;
""", 8)

tab_comment = {(r[0], r[1]): r[2] for r in q(f"""
select n.nspname, c.relname, coalesce(obj_description(c.oid), '')
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname in {SCHEMAS} and c.relkind in ('r','v','m','p');
""", 3)}

kinds = {(r[0], r[1]): r[2] for r in q(f"""
select n.nspname, c.relname, c.relkind
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname in {SCHEMAS} and c.relkind in ('r','v','m','p');
""", 3)}

pks = set()
for r in q("""
select n.nspname, t.relname, a.attname
from pg_constraint c
join pg_class t on t.oid = c.conrelid
join pg_namespace n on n.oid = t.relnamespace
join pg_attribute a on a.attrelid = t.oid and a.attnum = any(c.conkey)
where c.contype = 'p';""", 3):
    pks.add(tuple(r))

fks = {}
for r in q("""
select n.nspname, t.relname, a.attname, rn.nspname, rt.relname
from pg_constraint c
join pg_class t on t.oid = c.conrelid
join pg_namespace n on n.oid = t.relnamespace
join pg_attribute a on a.attrelid = t.oid and a.attnum = c.conkey[1]
join pg_class rt on rt.oid = c.confrelid
join pg_namespace rn on rn.oid = rt.relnamespace
where c.contype = 'f' and array_length(c.conkey,1) = 1;""", 5):
    fks[(r[0], r[1], r[2])] = f"{r[3]}.{r[4]}"

checks = collections.defaultdict(list)
for r in q(f"""
select n.nspname, t.relname, pg_get_constraintdef(c.oid)
from pg_constraint c
join pg_class t on t.oid = c.conrelid
join pg_namespace n on n.oid = t.relnamespace
where c.contype = 'c' and n.nspname in {SCHEMAS};""", 3):
    checks[(r[0], r[1])].append(r[2])

rls = {(r[0], r[1]): r[2] in ('t', 'true') for r in q(f"""
select n.nspname, c.relname, c.relrowsecurity::text
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname in {SCHEMAS} and c.relkind = 'r';""", 3)}

policies = collections.defaultdict(list)
for r in q(f"""
select schemaname, tablename, policyname, cmd,
       coalesce(qual, '-'), coalesce(with_check, '-')
from pg_policies where schemaname in {SCHEMAS};""", 6):
    policies[(r[0], r[1])].append(r[2:])

indexes = collections.defaultdict(list)
for r in q(f"""
select schemaname, tablename, indexdef from pg_indexes
where schemaname in {SCHEMAS};""", 3):
    indexes[(r[0], r[1])].append(r[2])

funcs = q("""
select n.nspname, p.proname,
       pg_get_function_arguments(p.oid),
       pg_get_function_result(p.oid),
       case when p.prosecdef then 'definer' else 'invoker' end,
       coalesce(obj_description(p.oid), '')
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname in ('public','util','app') and p.prokind = 'f'
order by n.nspname, p.proname;
""", 6)

view_opts = {(r[0], r[1]): r[2] for r in q("""
select n.nspname, c.relname, coalesce(array_to_string(c.reloptions, ','), '')
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind in ('v','m');""", 3)}

# ---------------------------------------------------------------------------
por_tabela = collections.defaultdict(list)
for r in colunas:
    por_tabela[(r[0], r[1])].append(r[2:])

KIND_LABEL = {'r': 'tabela', 'v': 'view', 'm': 'materialized view', 'p': 'tabela particionada'}

SCHEMA_DESC = {
    'app': ('Domínio OperaX', 'Não exposto ao PostgREST. RLS obrigatória em toda tabela.'),
    'secullum': ('Espelho literal do Secullum', 'Não exposto ao PostgREST. PII completa. Só `service_role`.'),
    'util': ('Helpers de RLS', 'Não exposto. Funções `security definer` com `search_path` travado.'),
    'public': ('Superfície de API', 'ÚNICO schema exposto. Só views (`security_invoker = on`) e RPCs.'),
}

out = []
w = out.append

w("# OperaX — Dicionário de dados e superfície de API\n")
w("> Gerado por introspecção do banco (`scripts/gerar_dicionario.py`).")
w("> Não editar à mão: regerar depois de cada migration.\n")

w("## Arquitetura de schemas\n")
w("| Schema | Papel | Exposto ao PostgREST |")
w("|---|---|---|")
for s in ('secullum', 'app', 'util', 'public'):
    d = SCHEMA_DESC[s]
    exp = "**Sim, e só ele**" if s == 'public' else "Não"
    w(f"| `{s}` | {d[0]} — {d[1]} | {exp} |")
w("")
w("A anon key vive no bundle do painel: qualquer pessoa chama o PostgREST direto.")
w("Por isso a fronteira real é **topologia de schema**, não policy. Tabela fora do")
w("schema exposto é inalcançável mesmo com policy errada.\n")

w("## Matriz de sensibilidade\n")
w("Quatro domínios em `app.sensitive_domain`. Quem vê o quê está em")
w("`app.domain_permission` — é dado, não código, e muda por `UPDATE`.\n")
w("| Domínio | Onde vive | Padrão de acesso |")
w("|---|---|---|")
w("| `pii` | `app.employee_pii` | owner, DP, RH |")
w("| `remuneracao` | `app.employee_compensation`, `app.payroll_entry`, `app.payroll_charge`, `app.acordo_*` | owner, DP, diretoria, contabilidade |")
w("| `saude` | `app.occupational_exam` | owner, RH |")
w("| `disciplinar` | ocorrências administrativas | owner, DP, RH |")
w("")
w("Gestor regional, supervisor de unidade, gestor operacional e consulta **não**")
w("recebem nenhum domínio sensível: veem ocorrência de ponto da sua unidade, não")
w("veem salário, RG nem ASO. Ver a unidade não dá direito a ver o dado sensível —")
w("as policies exigem escopo **e** domínio.\n")

# ------------------------------ tabelas por schema -------------------------
for schema in ('app', 'secullum'):
    nomes = sorted({t for (s, t) in por_tabela if s == schema and kinds.get((s, t)) in ('r', 'p', 'm')})
    if not nomes:
        continue
    w(f"\n---\n\n# Schema `{schema}`\n")
    w(f"{SCHEMA_DESC[schema][0]}. {SCHEMA_DESC[schema][1]}\n")
    for t in nomes:
        key = (schema, t)
        w(f"\n## `{schema}.{t}`\n")
        if tab_comment.get(key):
            w(f"> {tab_comment[key]}\n")
        rk = kinds.get(key, 'r')
        kind = KIND_LABEL.get(rk, 'tabela')
        if rk == 'm':
            flag = ("**não respeita RLS por natureza** — contém todos os tenants, "
                    "não é exposta, só é lida server-side com `service_role`")
        elif rls.get(key):
            flag = "RLS ligada"
        else:
            flag = "⚠️ **SEM RLS — corrigir**"
        w(f"*{kind} — {flag}*\n")

        w("| Coluna | Tipo | Nulo | Default | Referência | Nota |")
        w("|---|---|---|---|---|---|")
        for (ordn, name, typ, nn, dflt, cmt) in por_tabela[key]:
            marca = " 🔑" if (schema, t, name) in pks else ""
            ref = fks.get((schema, t, name), "")
            ref = f"`{ref}`" if ref else ""
            nulo = "não" if nn else "sim"
            dflt = f"`{dflt[:44]}`" if dflt else ""
            w(f"| `{name}`{marca} | {typ} | {nulo} | {dflt} | {ref} | {cmt} |")
        w("")

        if checks.get(key):
            w("**Restrições**\n")
            for c in sorted(checks[key]):
                w(f"- `{c}`")
            w("")

        if policies.get(key):
            w("**Policies**\n")
            w("| Policy | Comando | USING | WITH CHECK |")
            w("|---|---|---|---|")
            for (pname, cmd, qual, wc) in sorted(policies[key]):
                w(f"| `{pname}` | {cmd} | `{qual[:110]}` | `{wc[:70]}` |")
            w("")
        elif rls.get(key):
            w("**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.\n")

        idx = [i for i in indexes.get(key, []) if 'pkey' not in i]
        if idx:
            w("<details><summary>Índices</summary>\n")
            for i in sorted(idx):
                w(f"- `{i.split(' ON ')[0].replace('CREATE ', '').replace('INDEX ', '')}` — `{i.split(' ON ')[1]}`")
            w("\n</details>\n")

# ------------------------------ superfície pública -------------------------
w("\n---\n\n# Schema `public` — superfície de API\n")
w("Único schema exposto. Toda view usa `security_invoker = on`: a RLS do usuário")
w("que consulta continua valendo. `anon` não lê nada — o painel autentica antes.\n")

views = sorted({t for (s, t) in por_tabela if s == 'public' and kinds.get((s, t)) == 'v'})
for v in views:
    key = ('public', v)
    opts = view_opts.get(key, '')
    seguro = "✅ `security_invoker`" if 'security_invoker' in opts else "⚠️ **SEM security_invoker**"
    w(f"\n## `public.{v}`  {seguro}\n")
    if tab_comment.get(key):
        w(f"> {tab_comment[key]}\n")
    w("| Coluna | Tipo |")
    w("|---|---|")
    for (ordn, name, typ, nn, dflt, cmt) in por_tabela[key]:
        w(f"| `{name}` | {typ} |")
    w("")

w("\n## RPCs\n")
w("Funções com período parametrizado. `security invoker`: herdam a RLS de quem chama.\n")
for (sch, name, args, ret, sec, cmt) in funcs:
    if sch != 'public':
        continue
    w(f"\n### `{name}`\n")
    w("```sql")
    w(f"{sch}.{name}({args})")
    w(f"  returns {ret}")
    w("```")
    if cmt:
        w(f"\n{cmt}\n")

w("\n## Helpers de RLS (`util`)\n")
w("Não são API. `security definer` com `search_path` travado, `EXECUTE` revogado de `anon`.\n")
w("| Função | Assinatura | Retorno |")
w("|---|---|---|")
for (sch, name, args, ret, sec, cmt) in funcs:
    if sch == 'util':
        w(f"| `util.{name}` | `{args}` | `{ret}` |")
w("")

# ------------------------------ exemplos -----------------------------------
w("\n---\n\n# Como consumir\n")
w("""## Caminho 1 — navegador direto no Supabase (anon key)

Só agregado não sensível. A RLS filtra por tenant e escopo automaticamente.

```ts
const supabase = createClient(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)

// KPIs do período — filters vêm da query string do link do relatório
const { data } = await supabase.rpc('fn_kpi_period', {
  p_de: '2026-08-01', p_ate: '2026-08-31',
  p_unidade_id: searchParams.get('unit'),
})

// Série diária para o gráfico de tendência
const { data: serie } = await supabase
  .from('vw_deviation_daily_trend')
  .select('reference_date, direction, eventos, minutos_abs')
  .gte('reference_date', de).lte('reference_date', ate)
  .order('reference_date')
```

`anon` não lê nada: a sessão precisa estar autenticada. O cliente **não** manda
`tenant_id` — e não adianta mandar, porque a policy não confia em parâmetro do
cliente.

## Caminho 2 — navegador → FastAPI (individual, identificável ou sensível)

O `service_role` vive **somente** no backend FastAPI no Railway. Nunca no
Next.js, nunca no navegador. Uma chave que ignora toda a RLS não pode ter duas
cópias em dois provedores de deploy diferentes.

```python
# backend/server/routers/employee.py
@router.get("/employee/{employee_id}/pii")
async def ler_pii(employee_id: UUID, ctx: TenantContext = Depends(tenant_ctx)):
    # ctx vem do JWT do Supabase, validado contra o JWKS do projeto.
    # service_role IGNORA RLS — o filtro de tenant é obrigação nossa.
    async with pool_app.connection() as conn:
        row = await conn.execute(
            "select cpf, rg from app.employee_pii "
            "where tenant_id = %s and employee_id = %s",   # NUNCA omitir o tenant
            (ctx.tenant_id, employee_id),
        )
    return row
```

Antes de responder, o backend revalida papel e domínio sensível — não confia no
que o frontend diz que o usuário pode ver.

## Do sync — espelho do Secullum

```python
# backend/operax/core/db.py — conexão direta; upsert em lote é bem mais
# rápido que via PostgREST, e `secullum` nem é exposto ao PostgREST.
pool_secullum = ConnectionPool(
    DATABASE_URL,
    kwargs={"options": "-c search_path=secullum"},
)
```

**Regra para todo código com `service_role`:** nenhuma consulta sem filtro
explícito de `tenant_id`. É onde vazamento entre clientes acontece na prática,
porque a rede de proteção da RLS está desligada.
""")

os.makedirs("docs", exist_ok=True)
with open("docs/DICIONARIO-DE-DADOS.md", "w") as f:
    f.write("\n".join(out) + "\n")

n_tab = len([1 for k, v in kinds.items() if v in ('r', 'p') and k[0] in ('app', 'secullum')])
print(f"docs/DICIONARIO-DE-DADOS.md gerado — {n_tab} tabelas, {len(views)} views, "
      f"{len([f for f in funcs if f[0]=='public'])} RPCs, {sum(len(v) for v in policies.values())} policies")
