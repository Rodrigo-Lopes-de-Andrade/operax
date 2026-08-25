#!/usr/bin/env python3
"""Confere a matriz dono-do-campo contra o schema de verdade.

    python3 scripts/95_teste_matriz_rh.py

A matriz de `operax/rh/ownership.py` nomeia colunas de `app` e colunas do espelho
`secullum."Funcionario"`. Nome errado ali não quebra nada na hora: o template
simplesmente não trava a coluna que devia travar, e a tela mostra "Secullum ·
leitura de HH:MM" apontando para um campo que não existe. Falha silenciosa, do
tipo que só aparece quando alguém edita e o dado some.

Este teste existe porque foi exatamente o que aconteceu ao escrever a matriz:
quatro dos dezessete nomes de coluna do espelho estavam errados — `Cadastro` em
vez de `NumeroFolha`, `Departamento`/`Empresa` em vez das FKs uuid, e um
`TipoContrato` que não existe em lugar nenhum.
"""

import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from operax.rh.ownership import ENUMS, MATRIX, SEM_COLUNA, Owner  # noqa: E402
from operax.rh.templates import SEM_TEMPLATE, TEMPLATES, select_sql  # noqa: E402

ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}


def q(sql: str) -> set[str]:
    r = subprocess.run(["psql", "-tA", "-c", sql], capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        sys.exit(f"psql falhou:\n{r.stderr}")
    return {linha.strip() for linha in r.stdout.splitlines() if linha.strip()}


colunas_app = q("""
    select table_name || '.' || column_name
    from information_schema.columns where table_schema = 'app'
""")
colunas_espelho = q("""
    select 'Funcionario.' || a.attname
    from pg_attribute a
    where a.attrelid = 'secullum."Funcionario"'::regclass
      and a.attnum > 0 and not a.attisdropped
""")

problemas: list[str] = []

for f in MATRIX:
    if f"{f.table}.{f.column}" not in colunas_app:
        problemas.append(f"app.{f.table}.{f.column} não existe")
    if f.mirror and f.mirror not in colunas_espelho:
        problemas.append(f"{f.table}.{f.column} aponta para {f.mirror}, que não existe no espelho")
    # Campo pendente pode não ter espelho — é literalmente o que "pendente"
    # significa: ninguém confirmou se o Secullum sabe. Campo declarado sync sem
    # pendência, não: se ele é do sync, existe uma coluna de onde ele vem, e a
    # tela precisa citá-la.
    if f.owner is Owner.SYNC and not f.pending and f.mirror is None:
        problemas.append(f"{f.table}.{f.column} é sync sem origem declarada")

# Um campo não pode ser "sem coluna" e estar na matriz ao mesmo tempo: seria a
# lacuna escondida atrás da própria declaração dela.
for nome in SEM_COLUNA:
    if any(f.column == nome for f in MATRIX):
        problemas.append(f"{nome} está em SEM_COLUNA e na matriz ao mesmo tempo")


# Os enums copiados para o Python têm de ser exatamente o `check` do banco. Um
# valor a menos recusa linha boa no preview; um a mais deixa passar a linha que o
# banco vai rejeitar depois — e aí a recusa chega sem "erro na linha 43".
def valores_do_check(tabela: str, coluna: str) -> set[str] | None:
    defs = q(f"""
        select pg_get_constraintdef(oid) from pg_constraint
        where conrelid = 'app.{tabela}'::regclass and contype = 'c'
          and pg_get_constraintdef(oid) like '%({coluna} = ANY%'
    """)
    if not defs:
        return None
    return set(re.findall(r"'([a-z_]+)'::text", next(iter(defs))))


for (tabela, coluna), esperados in sorted(ENUMS.items()):
    reais = valores_do_check(tabela, coluna)
    if reais is None:
        problemas.append(f"app.{tabela}.{coluna} não tem check de enum no banco")
    elif reais != esperados:
        faltam = sorted(reais - esperados)
        sobram = sorted(esperados - reais)
        problemas.append(
            f"app.{tabela}.{coluna}: o banco aceita {faltam or '—'} que o código não, "
            f"e o código aceita {sobram or '—'} que o banco não"
        )

# ---------------------------------------------------------------------------
# Os templates — as colunas que o repositório cita e a matriz não governa
# ---------------------------------------------------------------------------
# Toda coluna de template passa pela matriz (`templates._check_registry` recusa o
# contrário no import). O que sobra são as colunas que o SQL do repositório nomeia
# por conta própria: chave, carimbo de tempo, o fecho da faixa de vigência. Um
# nome errado aqui só apareceria em produção, no primeiro import.
LITERAIS = {
    "employee.id",
    "employee.name",
    "employee.status",
    "employee.tenant_id",
    "employee.updated_at",
    "employee_pii.employee_id",
    "employee_pii.tenant_id",
    "employee_pii.updated_at",
    "employee_compensation.employee_id",
    "employee_compensation.tenant_id",
    "employee_compensation.effective_from",
    "employee_compensation.effective_to",
    "employee_compensation.recorded_by",
    "employee_position.tenant_id",
    "employee_position.employee_id",
    "employee_position.effective_from",
    "employee_position.effective_to",
    "employee_position.cargo",
    "employee_position.unit_id",
    "payroll_period.tenant_id",
    "payroll_period.year",
    "payroll_period.month",
    "payroll_period.status",
    "file_import.id",
    "file_import.tenant_id",
    "file_import.type",
    "file_import.storage_path",
    "file_import.file_name",
    "file_import.layout_version",
    "file_import.uploaded_by",
    "file_import.status",
    "file_import.rows_total",
    "file_import.rows_ok",
    "file_import.rows_error",
    "file_import.report",
    "audit_log.tenant_id",
    "audit_log.user_id",
    "audit_log.action",
    "audit_log.entity",
    "audit_log.entity_id",
    "audit_log.antes",
    "audit_log.depois",
}
for nome in sorted(LITERAIS):
    if nome not in colunas_app:
        problemas.append(f"app.{nome} é citada pelo repositório de RH e não existe")

# O `select` de pré-preenchimento é montado a partir do template. `prepare` o
# analisa e o planeja sem executar — é o que pega alias errado e join inválido,
# que a conferência coluna a coluna não vê.
for tipo, template in sorted(TEMPLATES.items()):
    r = subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", "-c", f"prepare p as {select_sql(template)}"],
        capture_output=True,
        text=True,
        env=ENV,
    )
    if r.returncode != 0:
        problemas.append(
            f"template {tipo}: o select de pré-preenchimento não compila: {r.stderr.strip()}"
        )

# Toda instrução fixa do RH — import e aba Colaboradores —, compilada contra o
# schema. A fonte é lida do arquivo em vez de importada porque os dois módulos
# puxam o driver e este teste roda fora do venv; e SQL copiado para cá à mão
# divergiria na primeira alteração. Os `update`/`insert` montados coluna a coluna
# ficam de fora: o que varia neles é nome de coluna, e isso é o que LITERAIS e a
# matriz conferem.
instrucoes: list[tuple[str, str]] = []
for modulo in ("repository.py", "employees.py"):
    fonte = (RAIZ / "backend" / "operax" / "rh" / modulo).read_text()
    instrucoes += re.findall(r'^(_?[A-Z][A-Z_]*_SQL) = """(.*?)"""', fonte, re.S | re.M)
if len(instrucoes) < 20:
    problemas.append(f"esperava ao menos 20 instruções fixas de RH, achei {len(instrucoes)}")


def posicionar(sql: str) -> str:
    """`%(nome)s` do psycopg vira `$n` do Postgres, na ordem de aparição."""
    ordem: list[str] = []

    def trocar(m: re.Match) -> str:
        if m.group(1) not in ordem:
            ordem.append(m.group(1))
        return f"${ordem.index(m.group(1)) + 1}"

    return re.sub(r"%\((\w+)\)s", trocar, sql)


for nome, sql in instrucoes:
    preparavel = posicionar(sql)
    r = subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", "-c", f"prepare p as {preparavel}"],
        capture_output=True,
        text=True,
        env=ENV,
    )
    if r.returncode != 0:
        problemas.append(f"{nome} não compila: {r.stderr.strip().splitlines()[0]}")

# Um template cujo tipo o `check` de `app.file_import` recusa é um template que
# não consegue nem registrar a própria importação.
tipos_aceitos = q("""
    select pg_get_constraintdef(oid) from pg_constraint
    where conrelid = 'app.file_import'::regclass and conname = 'file_import_type_check'
""")
aceitos = (
    set(re.findall(r"'([a-z_]+)'::text", next(iter(tipos_aceitos)))) if tipos_aceitos else set()
)
declarados = set(TEMPLATES) | set(SEM_TEMPLATE)
if declarados - aceitos:
    problemas.append(f"app.file_import não aceita os tipos {sorted(declarados - aceitos)}")
faltando_declarar = {t for t in aceitos if t.startswith("hr_")} - declarados
if faltando_declarar:
    problemas.append(
        f"tipos hr_* aceitos pelo banco e não declarados: {sorted(faltando_declarar)} — "
        "cada um precisa de template ou de um motivo em SEM_TEMPLATE"
    )

sync = sum(1 for f in MATRIX if f.owner is Owner.SYNC)
print(f"  matriz: {len(MATRIX)} campos ({sync} do sync, {len(MATRIX) - sync} do RH)")
print(f"  enums conferidos: {len(ENUMS)}")
print(f"  lacunas declaradas: {len(SEM_COLUNA)}")
print(f"  templates: {len(TEMPLATES)} com caminho de volta, {len(SEM_TEMPLATE)} sem")
print(f"  instruções fixas de RH compiladas: {len(instrucoes)}")

if problemas:
    print("\n❌ " + f"{len(problemas)} problema(s):")
    for p in problemas:
        print(f"  {p}")
    sys.exit(1)

print("\n================================================")
print(" MATRIZ DONO-DO-CAMPO: TODOS OS NOMES EXISTEM")
print("================================================")
