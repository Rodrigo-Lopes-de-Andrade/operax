#!/usr/bin/env python3
"""
Verifica se todo objeto de banco citado na documentação existe de fato.

Documento que cita `app.colaborador_pi` (sem o segundo i) parece certo na
revisão e manda o desenvolvedor para uma tabela que não existe. Este script
transforma isso em erro de build.

    python3 scripts/verificar_docs.py
"""
import re, subprocess, os, sys, glob

ENV = {**os.environ,
       "PGHOST": os.environ.get("PGHOST", "/tmp"),
       "PGPORT": os.environ.get("PGPORT", "5433"),
       "PGUSER": os.environ.get("PGUSER", "postgres"),
       "PGDATABASE": os.environ.get("PGDATABASE", "operax_test")}


def q(sql):
    r = subprocess.run(["psql", "-tA", "-c", sql], capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        sys.exit(f"psql falhou:\n{r.stderr}")
    return {l.strip() for l in r.stdout.split("\n") if l.strip()}


relacoes = q("""
select n.nspname || '.' || c.relname
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname in ('app','secullum','util','public') and c.relkind in ('r','v','m','p');
""")
funcoes = q("""
select n.nspname || '.' || p.proname
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname in ('app','secullum','util','public');
""")
colunas = q("""
select c.relname || '.' || a.attname
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
where n.nspname in ('app','secullum','util','public');
""")
tipos = q("""
select n.nspname || '.' || t.typname
from pg_type t join pg_namespace n on n.oid = t.typnamespace
where n.nspname in ('app','util');
""")

existentes = relacoes | funcoes | tipos
nomes_curtos = {r.split(".", 1)[1] for r in relacoes} | {f.split(".", 1)[1] for f in funcoes}

# ⛔ A EXCEÇÃO GLOBAL SAIU, E AS DUAS QUE HAVIA ESTAVAM VENCIDAS
# Eram `app.metrica.view_alvo` e `public.vw_desvio_evento`, nomes de antes da
# passada pt→en: em 26/09/2026 nenhum documento os citava mais, e o furo
# continuava aberto para qualquer nome errado que casasse com eles. O comentário
# abaixo já dizia por que a exceção por documento é melhor que a global — o que
# faltava era a guarda que reclama quando uma exceção sobra (ver o fim do
# arquivo). Não há lista global: quem precisa de exceção a declara no documento.
PREFIXOS = ("app.", "secullum.", "util.", "public.")

DOCS = sorted(glob.glob("docs/*.md")) + ["CLAUDE.md"]

problemas = []
citados = set()

# ⛔ O QUE ESTE PAR EXISTE PARA PEGAR: A EXCEÇÃO QUE SOBROU
# Suprimir sem reclamar de sobra foi o cego que deixou `scripts/95_teste_matriz_rh.py`
# aceitar por seis dias uma lacuna que já tinha coluna (SPRINTS-DP, item A), e ele
# vivia aqui também: um documento declarava `app.foo` como inexistente de
# propósito, a tabela nascia, e a declaração seguia dizendo que não existia — sem
# nada ficar vermelho. Agora cada declaração é conferida nas duas direções.
declaradas: dict[str, set[str]] = {}
citados_por_doc: dict[str, set[str]] = {}

for doc in DOCS:
    if not os.path.exists(doc):
        continue
    if doc.endswith("DICIONARIO-DE-DADOS.md"):
        continue  # gerado do banco, não pode divergir
    texto = open(doc, encoding="utf-8").read()

    # Um documento pode citar deliberadamente um nome que NÃO existe — é o caso
    # de uma avaliação que lista identificadores inventados por outra ferramenta.
    # Em vez de furar o verificador com uma exceção global (que esconderia o erro
    # de verdade se alguém passar a acreditar no nome), o próprio documento
    # declara suas exceções, e só valem dentro dele:
    #
    #   <!-- verificar-docs: inexistentes-de-proposito app.foo app.bar -->
    #
    # Vale nos TRÊS formatos que este verificador reconhece — `app.tabela`,
    # `app.tabela.coluna` e `vw_x`/`fn_x`. Valia só no primeiro até 24/08/2026, e
    # o silêncio era a pior parte: um documento declarava a exceção do jeito
    # documentado, o verificador a ignorava, e a mensagem de erro dizia que o
    # objeto não existia — que era justamente o que o autor já tinha escrito.
    excecoes_do_doc = set()
    for m in re.finditer(r"<!--\s*verificar-docs:\s*inexistentes-de-proposito([^>]*?)-->", texto):
        nomes = m.group(1).split()
        if not nomes:
            # Ficava inerte: o padrão antigo exigia `\s+` e um nome, então uma
            # diretiva sem nome não era exceção nem erro — era enfeite.
            problemas.append((doc, "<declaração sem nome>",
                              "diretiva verificar-docs vazia — apague-a"))
        excecoes_do_doc.update(nomes)
    declaradas[doc] = excecoes_do_doc
    citados_no_doc: set[str] = set()
    citados_por_doc[doc] = citados_no_doc

    # Blocos de código cercados: é de onde alguém copia e cola, então valem
    # tanto quanto o que está em crase — ou mais.
    blocos = re.findall(r"```[a-z]*\n(.*?)```", texto, re.S)
    sem_blocos = re.sub(r"```[a-z]*\n.*?```", "", texto, flags=re.S)

    trechos = re.findall(r"`([^`\n]+)`", sem_blocos)
    for bloco in blocos:
        # nomes qualificados por schema dentro do código
        trechos += re.findall(r"\b((?:app|secullum|util|public)\.\w+(?:\.\w+)?)", bloco)
        # chamadas rpc('fn_x') e from('vw_x') do supabase-js
        trechos += re.findall(r"['\"]((?:vw|fn|mv)_\w+)['\"]", bloco)

    for trecho in trechos:
        t = trecho.strip().rstrip("()").rstrip(".,;:")

        # objeto qualificado por schema
        m = re.fullmatch(r"(app|secullum|util|public)\.([a-zA-Z_][a-zA-Z0-9_]*)", t)
        if m:
            citados.add(t)
            citados_no_doc.add(t)
            base = f"{m.group(1)}.{m.group(2)}"
            if base in existentes or base in excecoes_do_doc:
                continue
            # pode ser coluna citada como schema.tabela.coluna? não neste padrão
            problemas.append((doc, t, "relação/função/tipo não existe"))
            continue

        # schema.tabela.coluna
        m = re.fullmatch(r"(app|secullum|util|public)\.([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)", t)
        if m:
            citados.add(t)
            citados_no_doc.add(t)
            if t in excecoes_do_doc:
                continue
            rel = f"{m.group(1)}.{m.group(2)}"
            col = f"{m.group(2)}.{m.group(3)}"
            if rel not in existentes:
                problemas.append((doc, t, "relação não existe"))
            elif col not in colunas:
                problemas.append((doc, t, f"coluna não existe em {rel}"))
            continue

        # view/rpc citada sem schema (vw_*, fn_*)
        if re.fullmatch(r"(vw|fn|mv)_\w+", t):
            citados.add(t)
            citados_no_doc.add(t)
            if t not in nomes_curtos and t not in excecoes_do_doc:
                problemas.append((doc, t, "view/função não existe"))


def resolve(termo):
    """O que o schema diz do termo, nos três formatos que este arquivo reconhece."""
    if termo in existentes:
        return "relação/função/tipo"
    m = re.fullmatch(r"(app|secullum|util|public)\.(\w+)\.(\w+)", termo)
    if m and f"{m.group(1)}.{m.group(2)}" in existentes and f"{m.group(2)}.{m.group(3)}" in colunas:
        return "coluna"
    if re.fullmatch(r"(vw|fn|mv)_\w+", termo) and termo in nomes_curtos:
        return "view/função"
    return None


# ⛔ AS DUAS DIREÇÕES, E A SEGUNDA É A QUE NINGUÉM ESCREVE
# A primeira é óbvia: o documento cita um nome que não existe. A segunda é a que
# custou seis dias em `95_teste_matriz_rh.py` e vinte neste repositório: o
# documento DECLARA um nome como inexistente de propósito e ele existe, ou declara
# um nome que nem cita. Nos dois casos a declaração é um furo que ninguém fechou —
# e a próxima pessoa que escrever o nome errado passa por ele em silêncio.
for doc, excecoes in declaradas.items():
    for excecao in sorted(excecoes):
        onde = resolve(excecao)
        if onde:
            # ⚠️ ESTE VEREDITO É RELATIVO AO BANCO QUE VOCÊ APONTOU, e foi assim que
            # ele mordeu quem o escreveu (26/09/2026): rodado à mão DEPOIS da suíte,
            # o ensaio já tinha a fixture do espelho aplicada, e as três tabelas de
            # `secullum` que **só existem em produção** apareciam como "vencidas".
            # Apagar a exceção delas deixaria o gate vermelho no estado canônico.
            # Dentro da suíte este passo roda ANTES do espelho — é esse o estado que
            # vale.
            estado = (
                " — ⚠️ confira EM QUE BANCO você rodou: `scripts/verificar_espelho.py`"
                " aplica a fixture e cria tabelas de `secullum` que só existem em produção"
                if excecao.startswith("secullum.")
                else ""
            )
            problemas.append((
                doc, excecao,
                f"declarada inexistente-de-proposito, e EXISTE no schema ({onde})"
                f" — a exceção venceu, apague-a{estado}",
            ))
        elif excecao not in citados_por_doc[doc]:
            problemas.append((
                doc, excecao,
                "declarada inexistente-de-proposito e não citada pelo documento — exceção sobrando, apague-a",
            ))

print(f"Documentos verificados: {len([d for d in DOCS if os.path.exists(d) and not d.endswith('DICIONARIO-DE-DADOS.md')])}")
print(f"Identificadores de banco citados: {len(citados)}")

if problemas:
    print(f"\n❌ {len(problemas)} referência(s) quebrada(s):\n")
    for doc, termo, motivo in problemas:
        print(f"  {doc}: `{termo}` — {motivo}")
    sys.exit(1)

print("✅ Toda referência a objeto de banco na documentação existe no schema.")

# Aviso: objetos do schema que nenhum documento menciona
nao_citados = sorted(
    r for r in relacoes
    if r.split(".", 1)[0] == "app"
    and r not in citados
    and r.split(".", 1)[1] not in {c.split(".")[-1] for c in citados}
)
if nao_citados:
    print(f"\nℹ️  {len(nao_citados)} tabela(s) de `app` não citadas em nenhum documento "
          f"(esperado para tabelas de apoio):")
    print("   " + ", ".join(n.split(".", 1)[1] for n in nao_citados))
