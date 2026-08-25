"""O arquivo que sai e o arquivo que volta.

Estes testes existem por causa de uma assimetria: gerar errado é visível — o
usuário abre a planilha e reclama — e ler errado é silencioso. Uma coluna
deslocada por um cabeçalho remontado à mão não dá erro nenhum; ela grava o CTPS
de uma pessoa no campo de outra. Por isso metade daqui é sobre recusar arquivo, e
cada recusa vem com a linha equivalente que precisa continuar passando.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from openpyxl import load_workbook

from operax.rh.ownership import Owner
from operax.rh.templates import TEMPLATES
from operax.rh.workbook import META_SHEET, WorkbookError, build, header_hash, parse
from tests.conftest import TENANT_ID

GERADO_EM = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
VINCULO = TEMPLATES["hr_link"]
REMUNERACAO = TEMPLATES["hr_compensation"]


def linhas_vinculo() -> list[dict[str, Any]]:
    return [
        {
            "employee_id": uuid4(),
            "registration_number": "1001",
            "name": "Ana Personagem",
            "hr_code": "RH-01",
        },
        {
            "employee_id": uuid4(),
            "registration_number": "1002",
            "name": "Bruno Personagem",
            "hr_code": None,
        },
    ]


def gerar(template=VINCULO, linhas=None, tenant_id: UUID = TENANT_ID) -> bytes:
    return build(
        template,
        linhas if linhas is not None else linhas_vinculo(),
        tenant_id=tenant_id,
        generated_at=GERADO_EM,
    )


def reabrir(conteudo: bytes):
    return load_workbook(BytesIO(conteudo))


def regravar(wb) -> bytes:
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Ida e volta
# ---------------------------------------------------------------------------
def test_o_que_foi_escrito_e_o_que_volta():
    linhas = linhas_vinculo()
    lido = parse(gerar(linhas=linhas), template=VINCULO, tenant_id=TENANT_ID)

    assert [row.line for row in lido.rows] == [2, 3]
    assert lido.rows[0].values == {
        "registration_number": "1001",
        "name": "Ana Personagem",
        "hr_code": "RH-01",
    }
    assert lido.rows[1].values["hr_code"] is None
    assert lido.layout_version == "hr_link.v1"


def test_data_e_valor_voltam_como_data_e_valor():
    from datetime import date

    linhas = [
        {
            "employee_id": uuid4(),
            "registration_number": "1001",
            "name": "Ana Personagem",
            "hr_code": "RH-01",
            "effective_from": date(2026, 1, 1),
            "salary": Decimal("2500.00"),
            "reason": "promoção",
        }
    ]
    lido = parse(gerar(REMUNERACAO, linhas), template=REMUNERACAO, tenant_id=TENANT_ID)
    valores = lido.rows[0].values
    # O Excel devolve datetime para célula de data; a coerção do template é quem
    # transforma em `date`, e isso é testado no importador.
    assert str(valores["effective_from"]).startswith("2026-01-01")
    assert Decimal(str(valores["salary"])) == Decimal("2500.00")


def test_linha_apagada_no_meio_nao_vira_linha_em_branco():
    conteudo = gerar()
    wb = reabrir(conteudo)
    ws = wb[VINCULO.sheet_title]
    for coluna in range(1, len(VINCULO.columns) + 1):
        # `ws.cell(..., value=None)` não apaga nada: openpyxl só atribui quando o
        # valor não é None. Apagar é escrever no atributo.
        ws.cell(row=3, column=coluna).value = None

    lido = parse(regravar(wb), template=VINCULO, tenant_id=TENANT_ID)

    assert [row.line for row in lido.rows] == [2]


# ---------------------------------------------------------------------------
# O que a planilha mostra
# ---------------------------------------------------------------------------
def test_coluna_do_sync_nasce_travada_e_a_do_rh_nao():
    wb = reabrir(gerar())
    ws = wb[VINCULO.sheet_title]

    for indice, column in enumerate(VINCULO.columns, start=1):
        travada = ws.cell(row=2, column=indice).protection.locked
        assert travada is (column.owner is Owner.SYNC or column.column in VINCULO.key_columns), (
            f"{column.column} deveria estar {'travada' if travada else 'livre'}"
        )
    assert ws.protection.sheet is True


def test_a_aba_de_controle_fica_escondida():
    wb = reabrir(gerar())
    assert wb[META_SHEET].sheet_state == "hidden"


def test_enum_vira_lista_suspensa_com_o_catalogo_do_campo():
    cadastro = TEMPLATES["hr_employee"]
    wb = reabrir(gerar(cadastro, [{"registration_number": "1001", "name": "Ana"}]))
    ws = wb[cadastro.sheet_title]

    formulas = [dv.formula1 for dv in ws.data_validations.dataValidation]
    assert any("clt" in f and "internship" in f for f in formulas), formulas


# ---------------------------------------------------------------------------
# Recusa de arquivo — antes da primeira linha
# ---------------------------------------------------------------------------
def test_arquivo_sem_a_aba_de_controle_e_recusado_inteiro():
    wb = reabrir(gerar())
    del wb[META_SHEET]

    with pytest.raises(WorkbookError) as erro:
        parse(regravar(wb), template=VINCULO, tenant_id=TENANT_ID)

    assert erro.value.code == "sem_meta"
    assert "baixe o modelo atual" in erro.value.message.lower()


def test_cabecalho_renomeado_a_mao_e_recusado():
    wb = reabrir(gerar())
    wb[VINCULO.sheet_title].cell(row=1, column=3, value="Código RH")

    with pytest.raises(WorkbookError) as erro:
        parse(regravar(wb), template=VINCULO, tenant_id=TENANT_ID)

    assert erro.value.code == "cabecalho_alterado"


def test_coluna_inserida_no_meio_e_recusada():
    # O caso que o hash existe para pegar: sem ele, "ID RH" passaria a ser lido
    # da coluna vizinha e o valor iria para o campo errado sem erro nenhum.
    wb = reabrir(gerar())
    wb[VINCULO.sheet_title].insert_cols(2)
    wb[VINCULO.sheet_title].cell(row=1, column=2, value="Observação")

    with pytest.raises(WorkbookError) as erro:
        parse(regravar(wb), template=VINCULO, tenant_id=TENANT_ID)

    assert erro.value.code == "cabecalho_alterado"


def test_arquivo_de_outro_cliente_nao_entra_aqui():
    outro = UUID("99999999-9999-4999-8999-999999999999")

    with pytest.raises(WorkbookError) as erro:
        parse(gerar(tenant_id=outro), template=VINCULO, tenant_id=TENANT_ID)

    assert erro.value.code == "tenant_divergente"


def test_planilha_de_um_tipo_enviada_como_outro_e_recusada():
    with pytest.raises(WorkbookError) as erro:
        parse(gerar(), template=REMUNERACAO, tenant_id=TENANT_ID)

    assert erro.value.code == "tipo_divergente"


def test_layout_antigo_e_recusado_enquanto_nao_houver_janela():
    wb = reabrir(gerar())
    meta = wb[META_SHEET]
    for linha in meta.iter_rows(min_row=1, max_col=2):
        if linha[0].value == "layout_version":
            linha[1].value = "hr_link.v0"

    with pytest.raises(WorkbookError) as erro:
        parse(regravar(wb), template=VINCULO, tenant_id=TENANT_ID)

    assert erro.value.code == "layout_antigo"


def test_qualquer_coisa_que_nao_seja_xlsx_e_recusada():
    with pytest.raises(WorkbookError) as erro:
        parse(b"matricula;nome;id_rh", template=VINCULO, tenant_id=TENANT_ID)

    assert erro.value.code == "arquivo_ilegivel"


def test_o_hash_cobre_ordem_e_nao_so_conteudo():
    assert header_hash(("Matrícula", "Nome")) != header_hash(("Nome", "Matrícula"))
