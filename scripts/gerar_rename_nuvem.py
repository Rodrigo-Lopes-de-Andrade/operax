#!/usr/bin/env python3
"""
Gera a migration de rename pt→en de um projeto Supabase na nuvem.

    python3 scripts/gerar_rename_nuvem.py <ref-producao> --alvo scripts/_alvo_en.json

Nada aqui é digitado à mão. Cada par (nome velho, nome novo) sai de duas fontes
reais confrontadas entre si:

  1. **O mapa** vem do histórico de migration da própria nuvem.
     `supabase_migrations.schema_migrations.statements` guarda o SQL das doze
     migrations que este repositório também tem — só que na grafia em português,
     de antes do rename. São o mesmo arquivo em duas grafias, então alinhar o
     fluxo de identificadores dos dois lados pareia um a um, sem heurística.

  2. **A conferência** vem dos dois catálogos, lidos pelo mesmo código
     (`scripts/introspeccao_nuvem.py`): o da nuvem e o que as 16 migrations deste
     repositório produzem num Postgres descartável. Um par só entra na migration
     se o nome novo existir de fato do outro lado.

O que o alinhamento não resolve sozinho fica registrado, não adivinhado:
`papel` é `role` como coluna e `user_role` como tipo, e é a única ambiguidade em
348 identificadores.

Espécies tratadas, cada uma pelo que o Postgres exige dela:

  • tabela, coluna, índice, constraint, policy, trigger → `alter ... rename`,
    que é baseado em OID: view, policy e índice que apontam para o objeto seguem
    junto sozinhos.
  • tipo enum e seus rótulos → `alter type ... rename value` antes do rename do
    tipo.
  • função → rename **e** troca de corpo: o corpo de uma função `language sql`
    é texto, roda com `search_path = ''` e cita `app.unidade` por extenso.
  • view → rename, rename das colunas de saída (o alias é texto e não segue) e,
    quando o corpo filtra por valor (`status = 'ativo'`), troca do corpo.
  • matview → derrubada e recriada com os índices: `create or replace
    materialized view` não existe.
  • check constraint que lista valores → derrubada antes da tradução do dado e
    recriada depois, porque `add constraint` valida as linhas na hora.
  • default de coluna e linhas das tabelas de catálogo → `update`, com a chave
    primária tratada por insere-novo → reaponta-filho → apaga-velho, já que as
    três FKs para o catálogo de tipo não têm `on update cascade`.

Num banco que já está em inglês a migration gerada não faz nada: todo passo é
guardado por "o nome velho existe E o novo não".
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SB_SQL = RAIZ / "scripts" / "sb_sql.sh"

# `secullum` fica de fora: espelho literal da origem, PascalCase por convenção.
DOM = ("app", "util", "public")

# As quatro tabelas da ingestão ficam congeladas. Elas nascem das migrations
# anteriores a este repositório, as Edge Functions escrevem nelas por nome
# literal em string JS e não existe um único teste em `supabase/functions/`.
# Congelar é reversível; quebrar a sincronização não é.
SYNC = {
    "batida_marcacao",
    "cursor_sincronizacao",
    "empresa_evento_status",
    "funcionario_evento_status",
}

# A única ambiguidade que o alinhamento se recusou a resolver sozinho.
COL_EXTRA = {"papel": "role"}
TIPO_EXTRA = {"papel": "user_role"}

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
LITERAL = re.compile(r"'([^']*)'")
COLUNA_EM = re.compile(r"\(\((\w+)\s")


# ---------------------------------------------------------------------------
# 1. O mapa, derivado do histórico de migration da nuvem
# ---------------------------------------------------------------------------
def consultar(ref: str, sql: str) -> list[dict]:
    saida = subprocess.run([str(SB_SQL), ref, sql], capture_output=True, text=True)
    if saida.returncode != 0:
        sys.exit(f"falhou ao consultar {ref}: {saida.stderr.strip()}")
    return json.loads(saida.stdout)


def baixar_migrations(ref: str, destino: pathlib.Path) -> list[pathlib.Path]:
    """O SQL das migrations como a nuvem o guarda — na grafia em português."""
    destino.mkdir(parents=True, exist_ok=True)
    linhas = consultar(
        ref,
        "select version, name, array_to_string(statements, E';\\n\\n') as sql "
        "from supabase_migrations.schema_migrations order by version",
    )
    arquivos = []
    for linha in linhas:
        arquivo = destino / f"{linha['version']}_{linha.get('name') or 'sem-nome'}.sql"
        arquivo.write_text((linha.get("sql") or "") + "\n")
        arquivos.append(arquivo)
    return arquivos


def _tokens(texto: str) -> list[str]:
    """Identificadores, sem comentário nem literal — o que alinha entre as duas grafias."""
    texto = re.sub(r"--[^\n]*", " ", texto)
    texto = re.sub(r"/\*.*?\*/", " ", texto, flags=re.S)
    texto = re.sub(r"\$\$.*?\$\$", " $BODY$ ", texto, flags=re.S)
    texto = re.sub(r"'[^']*'", " 'LIT' ", texto)
    texto = re.sub(r'"[^"]*"', ' "QID" ', texto)
    return TOKEN.findall(texto)


QUALIFICADO = re.compile(r"\b(app|util|public)\.([a-zA-Z_][a-zA-Z0-9_]*)")


def derivar_mapa(pt_dir: pathlib.Path, en_dir: pathlib.Path) -> dict[str, str]:
    """Pareia identificador a identificador entre as duas grafias do mesmo arquivo.

    Duas passadas. A primeira compara só os identificadores QUALIFICADOS por
    schema, que alinham em todos os arquivos. A segunda compara o fluxo inteiro
    de tokens e pega o que a primeira não vê — coluna, índice, policy. Um arquivo
    cujos dois lados tenham contagens diferentes é pulado inteiro, em vez de
    pareado por aproximação: aqui, o `01_fundacao_schemas`, que ganhou depois um
    bloco de preflight que a nuvem nunca viu.
    """
    mapa: dict[str, set[str]] = collections.defaultdict(set)
    pulados = []

    for pt in sorted(pt_dir.glob("*.sql")):
        en = en_dir / pt.name
        if not en.exists():
            continue
        p_qual, e_qual = QUALIFICADO.findall(pt.read_text()), QUALIFICADO.findall(en.read_text())
        if len(p_qual) == len(e_qual):
            for (ps, pn), (es, en_nome) in zip(p_qual, e_qual):
                if ps == es:
                    mapa[pn].add(en_nome)
        p_tok, e_tok = _tokens(pt.read_text()), _tokens(en.read_text())
        if len(p_tok) != len(e_tok):
            pulados.append(pt.name)
            continue
        for a, b in zip(p_tok, e_tok):
            if a != b:
                mapa[a].add(b)

    ambiguos = {k: sorted(v) for k, v in mapa.items() if len(v) > 1}
    resolvido = {k: next(iter(v)) for k, v in mapa.items() if len(v) == 1}
    if pulados:
        print(
            f"  alinhamento por token pulou {len(pulados)}: {', '.join(pulados)}", file=sys.stderr
        )
    if ambiguos:
        print(f"  ambíguos (resolvidos por espécie): {ambiguos}", file=sys.stderr)
    return resolvido


# ---------------------------------------------------------------------------
# 2. O plano, conferido contra os dois catálogos
# ---------------------------------------------------------------------------
def carregar_valores() -> dict[str, str]:
    """`VALORES` do rename_map.py: os literais de dado que o alinhamento descarta."""
    spec = importlib.util.spec_from_file_location("rename_map", RAIZ / "scripts" / "rename_map.py")
    modulo = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = ["rename_map.py"]
    try:
        spec.loader.exec_module(modulo)
    except SystemExit:
        pass
    finally:
        sys.argv = argv
    return dict(getattr(modulo, "VALORES", {}))


def montar_plano(prod: dict, alvo: dict, mapa: dict, valores: dict) -> tuple[dict, list[str]]:
    plano = collections.defaultdict(list)
    avisos: list[str] = []

    def en(nome, extra=None):
        if extra and nome in extra:
            return extra[nome]
        return mapa.get(nome, nome)

    def normaliza(texto):
        return " ".join((texto or "").split()).lower()

    def traduz(texto, extra=None):
        t = TOKEN.sub(lambda m: en(m.group(0), extra), texto or "")
        return LITERAL.sub(lambda m: "'" + valores.get(m.group(1), m.group(1)) + "'", t)

    kind_de = {(r["schema"], r["name"]): r["kind"] for r in prod.get("kinds", [])}

    # --- tipos e rótulos ---------------------------------------------------
    pt_tipo = {(r["schema"], r["name"]): r["labels"] for r in prod["enums"] if r["schema"] in DOM}
    en_tipo = {(r["schema"], r["name"]): r["labels"] for r in alvo["enums"] if r["schema"] in DOM}
    for (sch, nome), rot_pt in sorted(pt_tipo.items()):
        novo = en(nome, TIPO_EXTRA)
        rot_en = en_tipo.get((sch, novo))
        if rot_en is None or len(rot_pt) != len(rot_en):
            avisos.append(f"tipo {sch}.{nome}: sem par de mesma cardinalidade no alvo")
            continue
        # A ordem do enum é significativa e o rename a preservou: parear por
        # posição é o único critério que não inventa correspondência.
        for a, b in zip(rot_pt, rot_en, strict=True):
            if a != b:
                plano["rotulos"].append([sch, nome, a, b])
        if novo != nome:
            plano["tipos"].append([sch, nome, novo])

    # --- tabelas e colunas -------------------------------------------------
    en_tab = {(r["schema"], r["name"]) for r in alvo["tables"] if r["schema"] in DOM}
    for r in sorted(prod["tables"], key=lambda x: (x["schema"], x["name"])):
        if r["schema"] not in DOM or r["name"] in SYNC:
            continue
        novo = en(r["name"])
        if (r["schema"], novo) in en_tab and novo != r["name"]:
            plano["tabelas"].append([r["schema"], r["name"], novo])

    pc, ac = collections.defaultdict(dict), collections.defaultdict(dict)
    for c in prod["columns"]:
        if c["schema"] in DOM:
            pc[(c["schema"], c["name"])][c["column"]] = c
    for c in alvo["columns"]:
        if c["schema"] in DOM:
            ac[(c["schema"], c["name"])][c["column"]] = c

    for (sch, nome), cols in sorted(pc.items()):
        if nome in SYNC or kind_de.get((sch, nome)) in ("v", "m"):
            continue
        destino = ac.get((sch, en(nome)))
        if not destino:
            continue
        for col in cols:
            novo_c = en(col, COL_EXTRA)
            if novo_c != col and novo_c in destino:
                plano["colunas"].append([sch, en(nome), col, novo_c])

    # --- colunas de saída de view -----------------------------------------
    # O alias de uma view é texto na definição e não segue o rename da coluna de
    # origem: `vw_deviation_by_employee_day` continuaria entregando
    # `colaborador_id` ao frontend.
    for (sch, nome), cols in sorted(pc.items()):
        kind = kind_de.get((sch, nome))
        if kind not in ("v", "m"):
            continue
        destino = ac.get((sch, en(nome)))
        if not destino:
            continue
        for (col, _), alvo_col in zip(
            sorted(cols.items(), key=lambda x: x[1]["pos"]),
            sorted(destino.values(), key=lambda x: x["pos"]),
        ):
            if col != alvo_col["column"]:
                plano["colunas_view"].append([sch, en(nome), col, alvo_col["column"], kind])

    # --- funções -----------------------------------------------------------
    def aridade(args):
        return 0 if not (args or "").strip() else len(args.split(","))

    pt_fn = {
        (f["schema"], f["name"], aridade(f["args"])): f
        for f in prod["functions"]
        if f["schema"] in DOM
    }
    en_fn = {
        (f["schema"], f["name"], aridade(f["args"])): f
        for f in alvo["functions"]
        if f["schema"] in DOM
    }
    for (sch, nome, ar), f in sorted(pt_fn.items()):
        novo = en(nome)
        destino = en_fn.get((sch, novo, ar))
        if not destino:
            avisos.append(f"função {sch}.{nome}/{ar} não tem par no alvo")
            continue
        if novo != nome:
            plano["funcoes"].append([sch, nome, f["args"], novo])
        # O corpo é texto com `search_path = ''`: rename não o alcança.
        plano["corpos"].append(destino["definition"])

    # --- views -------------------------------------------------------------
    en_view = {(v["schema"], v["name"]): v for v in alvo["views"]}
    for v in prod["views"]:
        if v["schema"] not in DOM:
            continue
        novo = en(v["name"])
        if (v["schema"], novo) in en_view and novo != v["name"]:
            plano["views"].append([v["schema"], v["name"], novo])

    # Corpo que filtra por VALOR não segue o rename: o literal é dado, não
    # identificador. Depois da tradução essas views devolveriam zero linha.
    tem_literal_pt = lambda d: any(
        lit in valores and valores[lit] != lit for lit in LITERAL.findall(d or "")
    )
    for v in prod["views"]:
        if v["schema"] not in DOM or not tem_literal_pt(v["definition"]):
            continue
        novo = en(v["name"])
        destino = en_view.get((v["schema"], novo))
        if not destino:
            continue
        idx = [
            i["definition"]
            for i in alvo["indexes"]
            if i["schema"] == v["schema"] and i["name"] == novo
        ]
        plano["views_refazer"].append(
            [
                v["schema"],
                v["name"],
                novo,
                kind_de.get((v["schema"], v["name"]), "v"),
                destino["definition"],
                destino["options"] or [],
                idx,
            ]
        )
    return plano, avisos


def parear_por_definicao(
    plano, avisos, prod, alvo, especie, chave, campo, campo_def, en, traduz, normaliza
):
    """Pareia índice, constraint, policy e trigger pela ESTRUTURA, não pelo nome.

    Nome auto-gerado pelo Postgres (`colaborador_status_check`, `<tabela>_pkey`)
    nunca aparece no texto da migration, então o mapa de identificadores não pode
    conhecê-lo. Aqui traduz-se a definição do lado pt e procura-se a definição
    idêntica no alvo, na tabela correspondente — com o nome da tabela e o do
    próprio objeto apagados dos dois lados, para que a igualdade seja sobre a
    estrutura.
    """
    por_tab_pt, por_tab_en = collections.defaultdict(list), collections.defaultdict(list)
    for r in prod[chave]:
        if r["schema"] in DOM and r["name"] not in SYNC:
            por_tab_pt[(r["schema"], r["name"])].append(r)
    for r in alvo[chave]:
        if r["schema"] in DOM:
            por_tab_en[(r["schema"], r["name"])].append(r)

    def limpa(texto, tabela, objeto):
        # Do mais longo para o mais curto: o nome do objeto costuma conter o da
        # tabela como prefixo (`financial_agreement_pkey`), e trocar a tabela
        # primeiro deixaria "@_pkey" de um lado e "@" do outro.
        t = normaliza(texto)
        for x in sorted({tabela, objeto}, key=len, reverse=True):
            t = t.replace(x.lower(), "@")
        return t

    naocasou = []
    for (sch, tab), linhas in sorted(por_tab_pt.items()):
        destino = por_tab_en.get((sch, en(tab)), [])
        indice_en = collections.defaultdict(list)
        for d in destino:
            indice_en[limpa(d[campo_def], en(tab), d[campo])].append(d)
        for r in linhas:
            alvo_chave = limpa(traduz(r[campo_def], COL_EXTRA), en(tab), en(r[campo], COL_EXTRA))
            cands = indice_en.get(alvo_chave, [])
            if len(cands) == 1:
                if cands[0][campo] != r[campo]:
                    plano[especie].append([sch, en(tab), r[campo], cands[0][campo]])
            elif not cands:
                naocasou.append(r)
            else:
                avisos.append(
                    f"{especie[:-1]} {sch}.{tab}.{r[campo]}: {len(cands)} definições iguais no alvo"
                )
    return naocasou


def completar_plano(plano, avisos, prod, alvo, mapa, valores):
    def en(nome, extra=None):
        if extra and nome in extra:
            return extra[nome]
        return mapa.get(nome, nome)

    def normaliza(texto):
        return " ".join((texto or "").split()).lower()

    def traduz(texto, extra=None):
        t = TOKEN.sub(lambda m: en(m.group(0), extra), texto or "")
        return LITERAL.sub(lambda m: "'" + valores.get(m.group(1), m.group(1)) + "'", t)

    for especie, chave, campo in (
        ("indices", "indexes", "index"),
        ("constraints", "constraints", "constraint"),
        ("triggers", "triggers", "trigger"),
    ):
        parear_por_definicao(
            plano, avisos, prod, alvo, especie, chave, campo, "definition", en, traduz, normaliza
        )

    # Policy não tem uma definição única: tem comando, roles e dois predicados.
    def assinatura(r):
        return f"{r['command']}|{sorted(r['roles'] or [])}|{r['using_expr']}|{r['check_expr']}"

    for r in prod["policies"] + alvo["policies"]:
        r["_def"] = assinatura(r)
    parear_por_definicao(
        plano, avisos, prod, alvo, "policies", "policies", "policy", "_def", en, traduz, normaliza
    )

    # --- checks que mudam de CONTEÚDO --------------------------------------
    # Renomear uma check não muda o que ela aceita, e o nome nem sempre muda:
    # `deviation_event_status_check` já se chama assim nos dois lados porque a
    # tabela do grão já estava em inglês. Só que a definição lista 'ativo' e o
    # alvo lista 'active'. Varrer apenas os pares renomeados deixava essa passar.
    en_con = {
        (c["schema"], c["name"], c["constraint"]): c
        for c in alvo["constraints"]
        if c["schema"] in DOM
    }
    renomeadas = {(s, t, v): n for s, t, v, n in plano["constraints"]}
    refazer, ja = [], set()
    for c in prod["constraints"]:
        if c["schema"] not in DOM or c["type"] != "c" or c["name"] in SYNC:
            continue
        tab_en = en(c["name"])
        con_en = renomeadas.get((c["schema"], tab_en, c["constraint"]), c["constraint"])
        destino = en_con.get((c["schema"], tab_en, con_en))
        if not destino:
            continue
        so_ids = TOKEN.sub(lambda m: en(m.group(0), COL_EXTRA), c["definition"] or "")
        if normaliza(so_ids) != normaliza(destino["definition"]):
            refazer.append(
                [c["schema"], tab_en, c["constraint"], destino["constraint"], destino["definition"]]
            )
            ja.add((c["schema"], tab_en, c["constraint"]))

    # Quando nem o nome nem a definição pareiam — caso das checks de provedor que
    # a migration 14 reescreveu — pareia-se pela coluna que a checagem cobre.
    por_coluna = collections.defaultdict(list)
    for c in alvo["constraints"]:
        if c["schema"] in DOM and c["type"] == "c":
            achado = COLUNA_EM.search(c["definition"] or "")
            if achado:
                por_coluna[(c["schema"], c["name"], achado.group(1))].append(c)
    for c in prod["constraints"]:
        if (
            c["schema"] not in DOM
            or c["type"] != "c"
            or c["name"] in SYNC
            or (c["schema"], en(c["name"]), c["constraint"]) in ja
            or (c["schema"], en(c["name"]), c["constraint"]) in en_con
        ):
            continue
        achado = COLUNA_EM.search(c["definition"] or "")
        cands = (
            por_coluna.get((c["schema"], en(c["name"]), en(achado.group(1), COL_EXTRA)), [])
            if achado
            else []
        )
        if len(cands) == 1:
            refazer.append(
                [
                    c["schema"],
                    en(c["name"]),
                    c["constraint"],
                    cands[0]["constraint"],
                    cands[0]["definition"],
                ]
            )
    plano["refazer"] = refazer
    refeitas = {(r[0], r[1], r[2]) for r in refazer}
    plano["constraints"] = [c for c in plano["constraints"] if (c[0], c[1], c[2]) not in refeitas]

    # --- defaults que carregam valor ---------------------------------------
    pc = {(c["schema"], c["name"], c["column"]): c for c in prod["columns"] if c["schema"] in DOM}
    ac = {(c["schema"], c["name"], c["column"]): c for c in alvo["columns"] if c["schema"] in DOM}
    for (sch, tab, col), c in sorted(pc.items()):
        if tab in SYNC:
            continue
        destino = ac.get((sch, en(tab), en(col, COL_EXTRA)))
        if not destino:
            continue
        d_pt, d_en = c["column_default"] or "", destino["column_default"] or ""
        if d_pt != d_en and any(l in valores and valores[l] != l for l in LITERAL.findall(d_pt)):
            plano["defaults"].append([sch, en(tab), en(col, COL_EXTRA), d_en])

    # A matview sai das listas de rename: ela é derrubada e recriada, e
    # `alter view` nem a aceita. As views comuns continuam sendo renomeadas —
    # `create or replace view` precisa encontrá-las já com o nome novo.
    refeitos = {(v[0], v[1]) for v in plano["views_refazer"] if v[3] == "m"}
    alvos = {(a, en(b)) for a, b in refeitos}
    plano["views"] = [v for v in plano["views"] if (v[0], v[1]) not in refeitos]
    plano["colunas_view"] = [c for c in plano["colunas_view"] if (c[0], c[1]) not in alvos]
    plano["indices"] = [i for i in plano["indices"] if (i[0], i[1]) not in alvos]
    return plano


# ---------------------------------------------------------------------------
# 3. A migration
# ---------------------------------------------------------------------------
def emitir(P, ALVO, PROD, CFG, VALORES, MAPA, PRESAS, ALVO_FN):
    """Escreve o SQL. Cada bloco carrega, no comentário, a razão de existir —
    porque quase todos existem por uma armadilha que o ensaio encontrou."""

    def q(s):
        return "'" + str(s).replace("'", "''") + "'"

    def valores(linhas, cols):
        return ",\n".join("      (" + ", ".join(q(l[i]) for i in cols) + ")" for l in linhas)

    out = []
    w = out.append

    w("""-- ============================================================================
    -- OperaX — 11b. RENAME pt→en DO PROJETO NA NUVEM
    -- ----------------------------------------------------------------------------
    -- Alinha um banco que rodou as migrations 00–11 na grafia em PORTUGUÊS com o
    -- que este repositório define em inglês. É o caso do projeto de produção
    -- (Kastro Park Ponto), que parou na migration 11 e cujo histórico guarda a
    -- versão pt dos mesmos doze arquivos que aqui estão em en.
    --
    -- POR QUE O TIMESTAMP CAI ENTRE A 11 E A 12
    -- As migrations 12 a 15 referenciam nomes em inglês. Se o rename rodasse depois
    -- delas, a 12 encontraria `app.jornada_dia` e criaria uma segunda tabela ao
    -- lado — que é exatamente o desfecho que esta migration existe para evitar.
    --
    -- NUM BANCO QUE JÁ ESTÁ EM INGLÊS ESTA MIGRATION NÃO FAZ NADA. Todo rename é
    -- guardado por "o nome velho existe E o novo não". É o que mantém `make db-test`
    -- verde: no banco local as migrations 00–11 já criaram tudo em inglês.
    --
    -- SE OS DOIS NOMES EXISTIREM, ELA PARA. Coexistência de `app.colaborador` e
    -- `app.employee` significa que alguém já rodou metade da fusão, e seguir em
    -- frente duplicaria o modelo em silêncio.
    --
    -- O QUE ELA NÃO TOCA, DE PROPÓSITO
    --   • `secullum.*` — espelho literal da origem, PascalCase por convenção.
    --   • As quatro tabelas da ingestão: app.batida_marcacao, app.cursor_sincronizacao,
    --     app.empresa_evento_status e app.funcionario_evento_status. Elas nascem das
    --     onze migrations anteriores a este repositório, as Edge Functions escrevem
    --     nelas por nome literal em string JS, e não existe um único teste em
    --     `supabase/functions/`. Renomeá-las exige alterar as funções no mesmo
    --     instante, sem rede. Congelar é reversível; quebrar a sincronização não é.
    --     A decisão é do dono — ver docs/PLANO-RECONCILIACAO-NUVEM.md §5.
    --   • public.rls_auto_enable() — existe na nuvem e em nenhuma migration daqui.
    --     É event trigger que liga RLS em tabela criada em `public`; complementa o
    --     util.block_table_in_public() deste repositório, que é mais estrito.
    --
    -- GERADO por scripts/gerar_rename_nuvem.py confrontando o catálogo real dos dois
    -- lados. Nenhum par foi digitado à mão.
    -- ============================================================================
    """)

    w("""-- ---------------------------------------------------------------------------
    -- 0. Guarda de coexistência
    -- Antes de qualquer rename: se algum par (velho, novo) já estiver dos dois
    -- lados, esta migration não sabe qual é o certo e não tem o direito de
    -- escolher.
    -- ---------------------------------------------------------------------------
    do $$
    declare
      r record;
      v_colisao text[] := '{}';
    begin
      for r in
        select * from (values""")
    w(valores(P["tabelas"], (0, 1, 2)))
    w("""    ) as t(sch, velho, novo)
      loop
        if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
           and to_regclass(format('%I.%I', r.sch, r.novo)) is not null then
          v_colisao := v_colisao || format('%s.%s ↔ %s.%s', r.sch, r.velho, r.sch, r.novo);
        end if;
      end loop;
      if array_length(v_colisao, 1) > 0 then
        raise exception 'fusão pela metade: % par(es) coexistindo — %',
          array_length(v_colisao, 1), array_to_string(v_colisao, '; ')
          using hint = 'Alguém já rodou parte do rename. Resolver à mão antes de seguir.';
      end if;
    end $$;
    """)

    w("""-- ---------------------------------------------------------------------------
    -- 1. Tipos e rótulos de enum
    -- Os rótulos vêm antes do rename do tipo: `alter type ... rename value` precisa
    -- do tipo pelo nome que ele tem agora.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
    w(valores(P["rotulos"], (0, 1, 2, 3)))
    w("""    ) as t(sch, tipo, velho, novo)
      loop
        if exists (
          select 1 from pg_enum e
          join pg_type ty on ty.oid = e.enumtypid
          join pg_namespace n on n.oid = ty.typnamespace
          where n.nspname = r.sch and ty.typname = r.tipo and e.enumlabel = r.velho
        ) and not exists (
          select 1 from pg_enum e
          join pg_type ty on ty.oid = e.enumtypid
          join pg_namespace n on n.oid = ty.typnamespace
          where n.nspname = r.sch and ty.typname = r.tipo and e.enumlabel = r.novo
        ) then
          execute format('alter type %I.%I rename value %L to %L',
                         r.sch, r.tipo, r.velho, r.novo);
        end if;
      end loop;

      for r in
        select * from (values""")
    w(valores(P["tipos"], (0, 1, 2)))
    w("""    ) as t(sch, velho, novo)
      loop
        if exists (select 1 from pg_type ty join pg_namespace n on n.oid = ty.typnamespace
                    where n.nspname = r.sch and ty.typname = r.velho)
           and not exists (select 1 from pg_type ty join pg_namespace n on n.oid = ty.typnamespace
                            where n.nspname = r.sch and ty.typname = r.novo) then
          execute format('alter type %I.%I rename to %I', r.sch, r.velho, r.novo);
        end if;
      end loop;
    end $$;
    """)

    w("""-- ---------------------------------------------------------------------------
    -- 2. Tabelas
    -- `alter table ... rename` é baseado em OID: view, policy, índice e constraint
    -- que apontam para a tabela seguem sozinhos, porque guardam o OID e não o texto.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
    w(valores(P["tabelas"], (0, 1, 2)))
    w("""    ) as t(sch, velho, novo)
      loop
        if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
           and to_regclass(format('%I.%I', r.sch, r.novo)) is null then
          execute format('alter table %I.%I rename to %I', r.sch, r.velho, r.novo);
        end if;
      end loop;
    end $$;
    """)

    if P.get("matviews"):
        w("""-- ---------------------------------------------------------------------------
    -- 2b. Materialized views
    -- `alter table ... rename` recusa uma matview; a forma é `alter materialized
    -- view`. app.mv_desvio_dia não respeita RLS, contém todos os tenants e nunca é
    -- exposta — mas o nome dela precisa acompanhar o resto.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
        w(valores(P["matviews"], (0, 1, 2)))
        w("""    ) as t(sch, velho, novo)
      loop
        if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
           and to_regclass(format('%I.%I', r.sch, r.novo)) is null then
          execute format('alter materialized view %I.%I rename to %I', r.sch, r.velho, r.novo);
        end if;
      end loop;
    end $$;
    """)

    w("""-- ---------------------------------------------------------------------------
    -- 3. Colunas
    -- A tabela já está com o nome novo (bloco 2), então o alvo aqui é o nome novo.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
    w(valores(P["colunas"], (0, 1, 2, 3)))
    w("""    ) as t(sch, tab, velho, novo)
      loop
        if to_regclass(format('%I.%I', r.sch, r.tab)) is not null
           and exists (select 1 from information_schema.columns
                        where table_schema = r.sch and table_name = r.tab
                          and column_name = r.velho)
           and not exists (select 1 from information_schema.columns
                            where table_schema = r.sch and table_name = r.tab
                              and column_name = r.novo) then
          execute format('alter table %I.%I rename column %I to %I',
                         r.sch, r.tab, r.velho, r.novo);
        end if;
      end loop;
    end $$;
    """)

    for titulo, chave, verbo, nota in (
        (
            "4. Constraints",
            "constraints",
            "rename constraint",
            "Nome de check criado inline é gerado pelo Postgres (`colaborador_status_check`)\n-- e não acompanha o rename da tabela: tem de vir explícito.",
        ),
        (
            "5. Índices",
            "indices",
            None,
            "`alter index` é a forma para índice; constraint-índice (pkey, unique) já foi\n-- renomeado no bloco 4 e o índice segue junto.",
        ),
        (
            "6. Policies",
            "policies",
            None,
            "`alter policy ... rename` preserva o predicado. Derrubar e recriar exigiria\n-- ler 57 predicados de produção e reescrevê-los — e mudar policy de RLS é uma\n-- das três coisas que este projeto sempre para e pergunta.",
        ),
        ("7. Triggers", "triggers", None, "O trigger segue a tabela; só o nome precisa mudar."),
    ):
        linhas = P.get(chave, [])
        w(f"""-- ---------------------------------------------------------------------------
    -- {titulo}
    -- {nota}
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
        w(valores(linhas, (0, 1, 2, 3)))
        w("""    ) as t(sch, tab, velho, novo)
      loop
        if to_regclass(format('%I.%I', r.sch, r.tab)) is null then
          continue;
        end if;""")
        if chave == "constraints":
            w("""    if exists (select 1 from pg_constraint c
                    join pg_class rel on rel.oid = c.conrelid
                    join pg_namespace n on n.oid = rel.relnamespace
                    where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.velho)
           and not exists (select 1 from pg_constraint c
                            join pg_class rel on rel.oid = c.conrelid
                            join pg_namespace n on n.oid = rel.relnamespace
                            where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.novo) then
          execute format('alter table %I.%I rename constraint %I to %I',
                         r.sch, r.tab, r.velho, r.novo);
        end if;""")
        elif chave == "indices":
            w("""    if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
           and to_regclass(format('%I.%I', r.sch, r.novo)) is null then
          execute format('alter index %I.%I rename to %I', r.sch, r.velho, r.novo);
        end if;""")
        elif chave == "policies":
            w("""    if exists (select 1 from pg_policy p
                    join pg_class rel on rel.oid = p.polrelid
                    join pg_namespace n on n.oid = rel.relnamespace
                    where n.nspname = r.sch and rel.relname = r.tab and p.polname = r.velho)
           and not exists (select 1 from pg_policy p
                            join pg_class rel on rel.oid = p.polrelid
                            join pg_namespace n on n.oid = rel.relnamespace
                            where n.nspname = r.sch and rel.relname = r.tab and p.polname = r.novo) then
          execute format('alter policy %I on %I.%I rename to %I',
                         r.velho, r.sch, r.tab, r.novo);
        end if;""")
        else:
            w("""    if exists (select 1 from pg_trigger t
                    join pg_class rel on rel.oid = t.tgrelid
                    join pg_namespace n on n.oid = rel.relnamespace
                    where n.nspname = r.sch and rel.relname = r.tab and t.tgname = r.velho)
           and not exists (select 1 from pg_trigger t
                            join pg_class rel on rel.oid = t.tgrelid
                            join pg_namespace n on n.oid = rel.relnamespace
                            where n.nspname = r.sch and rel.relname = r.tab and t.tgname = r.novo) then
          execute format('alter trigger %I on %I.%I rename to %I',
                         r.velho, r.sch, r.tab, r.novo);
        end if;""")
        w("""  end loop;
    end $$;
    """)

    w("""-- ---------------------------------------------------------------------------
    -- 8. Views de public
    -- A definição de uma view é parse tree, não texto: os renames dos blocos 2 e 3
    -- já a atualizaram por dentro. Só o nome dela precisa mudar.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
    w(valores(P["views"], (0, 1, 2)))
    w("""    ) as t(sch, velho, novo)
      loop
        if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
           and to_regclass(format('%I.%I', r.sch, r.novo)) is null then
          execute format('alter view %I.%I rename to %I', r.sch, r.velho, r.novo);
        end if;
      end loop;
    end $$;
    """)

    if P.get("colunas_view"):
        w("""-- ---------------------------------------------------------------------------
    -- 8b. Colunas de saída das views
    -- O corpo de uma view segue o rename sozinho (é parse tree), mas o NOME das
    -- colunas que ela entrega, não: `select c.nome as colaborador_nome` guarda o
    -- alias como texto. Sem este bloco a view renomeada continuaria devolvendo
    -- `colaborador_id` — e é por esse nome que o frontend lê o resultado.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
        w(valores(P["colunas_view"], (0, 1, 2, 3, 4)))
        w("""    ) as t(sch, obj, velho, novo, kind)
      loop
        if to_regclass(format('%I.%I', r.sch, r.obj)) is not null
           and exists (select 1 from information_schema.columns
                        where table_schema = r.sch and table_name = r.obj and column_name = r.velho)
           and not exists (select 1 from information_schema.columns
                            where table_schema = r.sch and table_name = r.obj and column_name = r.novo) then
          if r.kind = 'm' then
            execute format('alter materialized view %I.%I rename column %I to %I',
                           r.sch, r.obj, r.velho, r.novo);
          else
            execute format('alter view %I.%I rename column %I to %I',
                           r.sch, r.obj, r.velho, r.novo);
          end if;
        end if;
      end loop;
    end $$;
    """)

    _views_v = [v for v in P.get("views_refazer", []) if v[3] == "v"]
    _views_m = [v for v in P.get("views_refazer", []) if v[3] == "m"]

    if _views_v:
        w("""-- ---------------------------------------------------------------------------
    -- 8c. Corpo das views que filtram por VALOR
    -- Seis views de public filtram `status = 'ativo'` ou `modo = 'producao'`. O
    -- corpo segue o rename de identificador sozinho, porque é parse tree — mas o
    -- literal dentro dele é dado, não identificador, e não segue. Depois do bloco
    -- 11 essas views devolveriam ZERO linha, filtrando por um valor que não existe
    -- mais. Não dá erro; dá tela vazia.
    --
    -- `create or replace view` não renomeia coluna, e é por isso que o 8b vem
    -- antes: aqui só o corpo é trocado, pela definição deste repositório.
    -- ---------------------------------------------------------------------------""")
        for sch, velho, novo, _kind, definicao, opcoes, _idx in _views_v:
            opts = (" with (" + ", ".join(opcoes) + ")") if opcoes else ""
            corpo = definicao.rstrip().rstrip(";")
            w(f"""do $$
    begin
      if to_regclass('{sch}.{novo}') is not null then
        execute $vw$create or replace view {sch}.{novo}{opts} as
    {corpo}$vw$;
      end if;
    end $$;""")
        w("")

    w("""-- ---------------------------------------------------------------------------
    -- 9. Funções
    -- Aqui rename não basta. O corpo de uma função `language sql` declarada com
    -- `as $$ ... $$` é TEXTO, e todas estas rodam com `search_path = ''`, então
    -- citam `app.unidade` por extenso. Renomear a tabela não mexe no corpo: a
    -- função continua apontando para um nome que não existe mais.
    --
    -- Renomeia-se primeiro (o OID é preservado, então as 57 policies que chamam
    -- estes helpers continuam apontando para eles) e em seguida o corpo é
    -- substituído pela definição em inglês. `create or replace` com a mesma
    -- assinatura também preserva o OID.
    -- ---------------------------------------------------------------------------
    do $$
    declare
      r record;
      v_sig text;
    begin
      for r in
        select * from (values""")
    w(
        ",\n".join(
            "      ("
            + ", ".join(q(x) for x in (f[0], f[1], f[2], f[3]))
            + f", {0 if not f[2].strip() else len(f[2].split(','))})"
            for f in P["funcoes"]
        )
    )
    w("""    ) as t(sch, velho, args, novo, aridade)
      loop
        -- A assinatura é lida do catálogo pelo OID (`::regprocedure`), não montada a
        -- partir do que produção tinha: o tipo do parâmetro de `pode_ver_dominio` já
        -- foi renomeado no bloco 1 (app.dominio_sensivel -> app.sensitive_domain), e
        -- a assinatura literal antiga não existe mais para ser citada.
        if not exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                        where n.nspname = r.sch and p.proname = r.novo) then
          for v_sig in
            select p.oid::regprocedure::text
            from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = r.sch and p.proname = r.velho
              and p.pronargs = r.aridade
          loop
            execute format('alter function %s rename to %I', v_sig, r.novo);
          end loop;
        end if;
      end loop;
    end $$;
    """)
    w("""-- Corpos em inglês.
    --
    -- `create or replace` NÃO consegue trocar o nome de um parâmetro
    -- ("cannot change name of input parameter"), e nove funções trocam. Cinco delas
    -- podem ser derrubadas e recriadas — nada depende delas. As outras quatro são os
    -- helpers `util.pode_ver_*`, e o Postgres recusa derrubá-las: 57 policies as
    -- citam no predicado. Para essas, o corpo novo entra com o nome de parâmetro
    -- ANTIGO, porque policy chama por posição e o nome do parâmetro de um helper
    -- `security definer` não é visto por ninguém. Fica registrado como divergência
    -- deliberada em docs/PLANO-RECONCILIACAO-NUVEM.md.
    --
    -- Num banco que já está em inglês tudo isto redefine cada função com
    -- exatamente o que ela já era.""")

    _por_nome = {}
    for sch, velho, args, novo in P["funcoes"]:
        _por_nome[(sch, novo)] = (velho, args)

    for corpo in P["corpos"]:
        m = re.match(r"CREATE OR REPLACE FUNCTION (\w+)\.(\w+)\(", corpo)
        if not m:
            w(corpo.rstrip().rstrip(";") + ";")
            continue
        sch, nome = m.group(1), m.group(2)
        velho, args_pt = _por_nome.get((sch, nome), (nome, None))
        alvo_fn = ALVO_FN.get((sch, nome))
        troca_param = alvo_fn and args_pt is not None and alvo_fn["args"] != args_pt
        if troca_param and f"{sch}.{velho}" not in PRESAS:
            # ninguem depende: derruba e recria com a assinatura exata do alvo.
            # Importa para as `public.fn_*`: o frontend as chama por parametro
            # NOMEADO via PostgREST, entao o nome do parametro e contrato.
            w(f"drop function if exists {sch}.{nome}({args_pt});")
            w(corpo.rstrip().rstrip(";") + ";")
        elif troca_param:
            # Presa por policy: nao pode ser derrubada, e `create or replace` recusa
            # trocar o nome de um parametro. O corpo novo entra com os nomes de
            # parametro de PRODUCAO — mas so quando a funcao ainda os tem. Num banco
            # que ja esta em ingles a mesma instrucao falharia ao contrario, entao as
            # duas variantes ficam no arquivo e o `if` escolhe.
            de = [x.strip().split()[0] for x in alvo_fn["args"].split(",")]
            para = [x.strip().split()[0] for x in args_pt.split(",")]

            # A assinatura a comparar e a que a funcao tem AGORA, nao a que producao
            # tinha: o bloco 1 ja renomeou app.dominio_sensivel para
            # app.sensitive_domain, e o parametro carrega esse tipo.
            # Traduz-se o TIPO, nunca o nome do parametro: o mapa conhece
            # `p_colaborador_id -> p_employee_id` (os dois arquivos de migration
            # tinham a definicao da funcao, entao o alinhamento pareou tambem os
            # parametros) e usa-lo aqui compararia contra o nome que a funcao ainda
            # nao tem.
            def _so_tipo(arg):
                nome_par, _, tipo = arg.strip().partition(" ")
                tipo = re.sub(
                    r"[A-Za-z_][A-Za-z0-9_]*", lambda m: MAPA.get(m.group(0), m.group(0)), tipo
                )
                return f"{nome_par} {tipo}".strip()

            args_pt_agora = ", ".join(_so_tipo(a) for a in args_pt.split(","))
            corpo_pt = corpo
            for a, b in zip(de, para):
                if a != b:
                    corpo_pt = re.sub(rf"\b{re.escape(a)}\b", b, corpo_pt)
            w(f"""do $$
    begin
      if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                  where n.nspname = {q(sch)} and p.proname = {q(nome)}
                    and pg_get_function_identity_arguments(p.oid) = {q(args_pt_agora)}) then
        execute $fn${corpo_pt.rstrip().rstrip(";")}
    $fn$;
      else
        execute $fn${corpo.rstrip().rstrip(";")}
    $fn$;
      end if;
    end $$;""")
        else:
            w(corpo.rstrip().rstrip(";") + ";")
    w("")

    # --- constraints que mudam de conteudo, nao de grafia ---
    if P.get("refazer"):
        w("""-- ---------------------------------------------------------------------------
    -- 10a. Derruba as check constraints que carregam VALOR
    -- Trinta e nove das setenta e cinco checks de `app` não mudam só de nome: elas
    -- listam os valores aceitos, e esses valores estão em português. Renomear
    -- `desvio_tipo_direcao_check` para `deviation_type_direction_check` deixa uma
    -- constraint que continua exigindo 'excedente' — e o update do bloco 11, que
    -- grava 'surplus', bate nela.
    --
    -- Elas caem aqui e voltam no bloco 12, depois de o dado estar traduzido. Entre
    -- os dois blocos a tabela fica sem essa checagem; é o único jeito, porque
    -- `add constraint ... check` valida as linhas existentes na hora.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
        w(valores(P["refazer"], (0, 1, 2)))
        w("""    ) as t(sch, tab, velho)
      loop
        if to_regclass(format('%I.%I', r.sch, r.tab)) is not null
           and exists (select 1 from pg_constraint c
                        join pg_class rel on rel.oid = c.conrelid
                        join pg_namespace n on n.oid = rel.relnamespace
                        where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.velho) then
          execute format('alter table %I.%I drop constraint %I', r.sch, r.tab, r.velho);
        end if;
      end loop;
    end $$;
    """)

    # --- 10b. defaults de coluna que carregam valor ---------------------------------
    if P.get("defaults"):
        out.append("""-- ---------------------------------------------------------------------------
    -- 10b. Defaults de coluna que carregam valor
    -- `status text default 'ativo'` continua gravando 'ativo' depois do rename, e a
    -- check já refeita no bloco 10 recusaria a linha. O default vem do alvo.
    -- ---------------------------------------------------------------------------
    do $$
    begin""")
        for sch, tab, col, d in P["defaults"]:
            alvo_d = f"set default {d}" if d else "drop default"
            out.append(f"""  if to_regclass('{sch}.{tab}') is not null
         and exists (select 1 from information_schema.columns
                      where table_schema = '{sch}' and table_name = '{tab}'
                        and column_name = '{col}') then
        execute $sql$alter table {sch}.{tab} alter column {col} {alvo_d}$sql$;
      end if;""")
        out.append("end $$;\n")

    # --- 11. valores de dado nas tabelas de catalogo -------------------------------
    dt = [(r["codigo"], VALORES.get(r["codigo"], r["codigo"])) for r in CFG["dt_prod"]]
    dirs = sorted({(r["direcao"], VALORES.get(r["direcao"], r["direcao"])) for r in CFG["dt_prod"]})
    cats = sorted(
        {(r["categoria"], VALORES.get(r["categoria"], r["categoria"])) for r in CFG["dt_prod"]}
    )
    faltando = [a for a, b in dt if a == b]
    assert not faltando, f"VALORES nao cobre: {faltando}"

    out.append("""-- ---------------------------------------------------------------------------
    -- 11. Valores de dado no catálogo
    -- Rename de identificador não alcança o conteúdo das linhas. `deviation_type`
    -- guarda 'entrada_atrasada' onde este repositório guarda 'late_entry', e o
    -- código é chave primária referenciada por três FKs sem `on update cascade`.
    --
    -- Por isso a ordem é insere-novo → reaponta filho → apaga-velho, em vez de
    -- `update`: nenhuma constraint precisa ser derrubada, e em nenhum instante uma
    -- linha filha aponta para um código que não existe.
    --
    -- As direções e categorias são colunas comuns e vão por `update` direto.
    -- ---------------------------------------------------------------------------
    do $$
    begin
      if to_regclass('app.deviation_type') is null then
        return;
      end if;

      insert into app.deviation_type (code, description, direction, category)
      select v.novo, t.description, t.direction, t.category
      from app.deviation_type t
      join (values""")
    out.append(",\n".join(f"          ({q(a)}, {q(b)})" for a, b in dt))
    out.append("""       ) as v(velho, novo) on v.velho = t.code
      where not exists (select 1 from app.deviation_type x where x.code = v.novo);

      update app.deviation_type_config c set code = v.novo
        from (values""")
    out.append(",\n".join(f"           ({q(a)}, {q(b)})" for a, b in dt))
    out.append("""         ) as v(velho, novo) where c.code = v.velho;

      update app.deviation_event d set type = v.novo
        from (values""")
    out.append(",\n".join(f"           ({q(a)}, {q(b)})" for a, b in dt))
    out.append("""         ) as v(velho, novo) where d.type = v.velho;

      update app.alert_rule a set deviation_type = v.novo
        from (values""")
    out.append(",\n".join(f"           ({q(a)}, {q(b)})" for a, b in dt))
    out.append("""         ) as v(velho, novo) where a.deviation_type = v.velho;

      delete from app.deviation_type where code in (""")
    out.append("    " + ", ".join(q(a) for a, b in dt))
    out.append("""  );""")
    for velho, novo in dirs:
        out.append(
            f"  update app.deviation_type set direction = {q(novo)} where direction = {q(velho)};"
        )
    for velho, novo in cats:
        out.append(
            f"  update app.deviation_type set category = {q(novo)} where category = {q(velho)};"
        )
    out.append("end $$;\n")

    # metrica: codigo, view_alvo e dominio carregam nome/valor em pt
    out.append("""do $$
    begin
      if to_regclass('app.metric') is null then
        return;
      end if;""")
    for a, b in zip(CFG["m_prod"], CFG["m_alvo"]):
        dom = q(b["domain"]) if b["domain"] is not None else "null"
        out.append(
            f"  update app.metric set code = {q(b['code'])}, "
            f"target_view = {q(b['target_view'])}, domain = {dom} "
            f"where code = {q(a['codigo'])};"
        )
    out.append("end $$;\n")

    # --- 12. recria as checks, agora que o dado esta em ingles ---------------------
    if P.get("refazer"):
        out.append("""-- ---------------------------------------------------------------------------
    -- 12. Recria as check constraints, agora com os valores em inglês
    -- `add constraint ... check` valida as linhas existentes, então este bloco só
    -- funciona depois do 11. Se alguma linha tiver escapado da tradução, é aqui que
    -- a migration para — que é o comportamento certo: melhor falhar do que aceitar
    -- uma tabela cuja checagem não corresponde ao que ela guarda.
    -- ---------------------------------------------------------------------------
    do $$
    declare r record;
    begin
      for r in
        select * from (values""")
        out.append(
            ",\n".join(
                "      (" + ", ".join(q(x) for x in (l[0], l[1], l[3], l[4])) + ")"
                for l in P["refazer"]
            )
        )
        out.append("""    ) as t(sch, tab, nome, definicao)
      loop
        if to_regclass(format('%I.%I', r.sch, r.tab)) is not null
           and not exists (select 1 from pg_constraint c
                            join pg_class rel on rel.oid = c.conrelid
                            join pg_namespace n on n.oid = rel.relnamespace
                            where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.nome) then
          execute format('alter table %I.%I add constraint %I %s', r.sch, r.tab, r.nome, r.definicao);
        end if;
      end loop;
    end $$;
    """)

    if _views_m:
        out.append("""-- ---------------------------------------------------------------------------
    -- 12b. Materialized view
    -- `create or replace materialized view` não existe, e o corpo dela filtra
    -- `status = 'ativo'` como as views do bloco 8c. Então ela cai e sobe de novo,
    -- com os índices — que caem junto e voltam junto.
    --
    -- Vem aqui, no fim, porque `create materialized view` executa a consulta na
    -- hora: antes do bloco 11 ela se popularia filtrando por um valor que a
    -- tradução ainda não tinha gravado.
    --
    -- app.mv_deviation_day não respeita RLS e nunca é exposta — recriá-la não muda
    -- quem enxerga o quê.
    -- ---------------------------------------------------------------------------""")
        for sch, velho, novo, _kind, definicao, _opcoes, indices in _views_m:
            corpo = definicao.rstrip().rstrip(";")
            out.append(f"""do $$
    begin
      if to_regclass('{sch}.{velho}') is not null then
        execute format('drop materialized view %I.%I cascade', '{sch}', '{velho}');
      end if;
      if to_regclass('{sch}.{novo}') is null then
        execute $mv$create materialized view {sch}.{novo} as
    {corpo}$mv$;""")
            for idx in indices:
                out.append(f"    execute $ix${idx}$ix$;")
            out.append("""  end if;
    end $$;""")
        out.append("")

    # O corpo desta função foi transportado do gerador que os ensaios validaram, e
    # embrulhá-lo numa função indentou também o CONTEÚDO das strings — todo
    # comentário e todo SQL ganhou quatro espaços. Em SQL isso não muda nada, mas
    # o arquivo é lido por gente. Tira-se aqui, uma vez, no fim.
    sql = "\n".join(out) + "\n"
    return "\n".join(
        linha[4:] if linha.startswith("    ") else linha for linha in sql.split("\n")
    )


def linhas_de_catalogo(ref: str, alvo_db: str) -> dict:
    """As linhas das tabelas de catálogo, dos dois lados.

    São dados, não schema: `deviation_type` guarda 'entrada_atrasada' onde este
    repositório guarda 'late_entry'. Só tabelas de configuração são lidas —
    nenhuma tabela de pessoa entra aqui.
    """

    def local(sql):
        saida = subprocess.run(
            [
                "psql",
                "-tAX",
                "-d",
                alvo_db,
                "-c",
                f"select coalesce(json_agg(t),'[]') from ({sql}) t",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return json.loads(saida.stdout or "[]")

    dt_prod = consultar(
        ref, "select codigo, descricao, direcao, categoria from app.desvio_tipo order by codigo"
    )
    m_prod = consultar(
        ref, "select codigo, titulo, view_alvo, dominio from app.metrica order by codigo"
    )
    dt_alvo = local(
        "select code, description, direction, category from app.deviation_type order by code"
    )
    m_alvo = local("select code, title, target_view, domain from app.metric order by code")

    valores = carregar_valores()
    # Pareia métrica pelo código traduzido, não por posição: a ordem alfabética
    # de 'colaboradores_afetados' não é a de 'affected_employees'.
    por_code = {r["code"]: r for r in m_alvo}
    pares = [
        (r, por_code[valores.get(r["codigo"], r["codigo"])])
        for r in m_prod
        if valores.get(r["codigo"], r["codigo"]) in por_code
    ]
    return {
        "dt_prod": dt_prod,
        "dt_alvo": dt_alvo,
        "m_prod": [a for a, _ in pares],
        "m_alvo": [b for _, b in pares],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="project ref da nuvem cujo schema será renomeado")
    parser.add_argument(
        "--producao",
        default="scripts/_producao.json",
        help="catálogo da nuvem (scripts/introspeccao_nuvem.py <ref> --json)",
    )
    parser.add_argument(
        "--alvo",
        default="scripts/_alvo_en.json",
        help="catálogo do que as migrations deste repositório produzem",
    )
    parser.add_argument(
        "--alvo-db",
        default="alvo_en",
        help="dbname do Postgres onde o alvo foi montado (para as linhas de catálogo)",
    )
    parser.add_argument(
        "--saida", default="supabase/migrations/20260815101150_11b_rename_pt_en.sql"
    )
    parser.add_argument("--trabalho", default=None, help="onde guardar o SQL pt baixado da nuvem")
    args = parser.parse_args()

    trabalho = pathlib.Path(args.trabalho or (RAIZ / "scripts" / "_rename_trabalho"))
    print("baixando o SQL das migrations como a nuvem o guarda…", file=sys.stderr)
    baixar_migrations(args.ref, trabalho)

    mapa = derivar_mapa(trabalho, RAIZ / "supabase" / "migrations")
    print(f"  mapa derivado: {len(mapa)} identificadores", file=sys.stderr)

    prod = json.load(open(args.producao))
    alvo = json.load(open(args.alvo))
    valores = carregar_valores()

    plano, avisos = montar_plano(prod, alvo, mapa, valores)
    completar_plano(plano, avisos, prod, alvo, mapa, valores)

    for especie in sorted(plano):
        print(f"  {especie:<14} {len(plano[especie])}", file=sys.stderr)
    for aviso in avisos:
        print(f"  aviso: {aviso}", file=sys.stderr)

    # Políticas de produção citam estes helpers no predicado; derrubá-los é
    # recusado pelo Postgres, então o corpo entra por `create or replace` com o
    # nome de parâmetro que a função ainda tem.
    presas = set()
    for pol in prod["policies"]:
        for expr in (pol["using_expr"], pol["check_expr"]):
            for m in re.findall(r"\b(util|app|public)\.(\w+)\(", expr or ""):
                presas.add(f"{m[0]}.{m[1]}")

    sql = emitir(
        dict(plano),
        alvo,
        prod,
        linhas_de_catalogo(args.ref, args.alvo_db),
        valores,
        mapa,
        presas,
        {(f["schema"], f["name"]): f for f in alvo["functions"]},
    )
    pathlib.Path(args.saida).write_text(sql)
    print(f"{args.saida} — {len(sql)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
