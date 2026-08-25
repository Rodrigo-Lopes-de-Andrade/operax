"""O veredito de cada linha — inclusive o veredito de que não há nada a fazer.

O terceiro resultado é o que mais precisa de teste. `ok` e `error` são óbvios;
`unchanged` é o que separa "reimportei as três linhas corrigidas" de "reescrevi as
oitenta". O template vem preenchido, então um arquivo intocado é um arquivo em que
toda linha já diz o que o banco diz — e sem essa distinção o reenvio abriria uma
faixa de salário nova para cada pessoa da planilha.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from operax.rh.importer import ImportContext, retroactive_limit, validate
from operax.rh.templates import TEMPLATES
from operax.rh.workbook import SheetRow
from tests.fixtures.rh_sintetico import ANA, BRUNO, CARLA, POR_HR_CODE, POR_MATRICULA

VINCULO = TEMPLATES["hr_link"]
CADASTRO = TEMPLATES["hr_employee"]
REMUNERACAO = TEMPLATES["hr_compensation"]

HOJE = date(2026, 8, 24)
SEM_TETO = retroactive_limit(HOJE, None)

ATUAL_VINCULO: dict[Any, dict[str, Any]] = {
    ANA: {"registration_number": "1001", "name": "Ana Personagem", "hr_code": "RH-01"},
    BRUNO: {"registration_number": "1002", "name": "Bruno Personagem", "hr_code": None},
    CARLA: {"registration_number": "1003", "name": "Carla Personagem", "hr_code": None},
}

ATUAL_REMUNERACAO: dict[Any, dict[str, Any]] = {
    ANA: {
        "registration_number": "1001",
        "name": "Ana Personagem",
        "hr_code": "RH-01",
        "effective_from": date(2026, 1, 1),
        "salary": Decimal("2500.00"),
        "reason": "admissão",
    }
}


def contexto(atual: dict[Any, dict[str, Any]], *, limite: int = SEM_TETO) -> ImportContext:
    return ImportContext(
        by_registration=dict(POR_MATRICULA),
        by_hr_code=dict(POR_HR_CODE),
        current=atual,
        today=HOJE,
        retroactive_limit_days=limite,
    )


def linhas(*valores: dict[str, Any]) -> tuple[SheetRow, ...]:
    return tuple(SheetRow(line=2 + i, values=v) for i, v in enumerate(valores))


def codigos(resultado) -> list[str]:
    return [erro.code for erro in resultado.errors]


# ---------------------------------------------------------------------------
# Vínculo — o primeiro template, e o único em que o ID RH é campo e não chave
# ---------------------------------------------------------------------------
def test_o_id_rh_novo_e_gravado():
    resultado = validate(
        VINCULO,
        linhas({"registration_number": "1002", "name": "Bruno Personagem", "hr_code": "RH-03"}),
        contexto(ATUAL_VINCULO),
    )[0]

    assert resultado.status == "ok"
    assert resultado.values == {"hr_code": "RH-03"}
    assert resultado.previous == {"hr_code": None}


def test_a_linha_que_ja_estava_certa_nao_escreve_nada():
    resultado = validate(
        VINCULO,
        linhas({"registration_number": "1001", "name": "Ana Personagem", "hr_code": "RH-01"}),
        contexto(ATUAL_VINCULO),
    )[0]

    assert resultado.status == "unchanged"
    assert resultado.values == {}


def test_matricula_de_fora_do_cliente_nao_encontra_ninguem():
    resultado = validate(
        VINCULO,
        linhas({"registration_number": "9999", "name": "Alguém", "hr_code": "RH-09"}),
        contexto(ATUAL_VINCULO),
    )[0]

    assert resultado.status == "error"
    assert codigos(resultado) == ["chave_desconhecida"]
    assert resultado.employee_id is None


def test_o_mesmo_id_rh_em_duas_linhas_do_arquivo():
    resultados = validate(
        VINCULO,
        linhas(
            {"registration_number": "1002", "name": "Bruno Personagem", "hr_code": "RH-09"},
            {"registration_number": "1003", "name": "Carla Personagem", "hr_code": "RH-09"},
        ),
        contexto(ATUAL_VINCULO),
    )

    assert resultados[0].status == "ok"
    assert codigos(resultados[1]) == ["duplicado_no_arquivo"]
    # A mensagem cita a linha, porque procurar "RH-09" numa planilha de 200
    # linhas é o que faz o DP desistir de corrigir.
    assert "linha 2" in resultados[1].errors[0].message


def test_id_rh_que_ja_e_de_outra_pessoa():
    resultado = validate(
        VINCULO,
        linhas({"registration_number": "1002", "name": "Bruno Personagem", "hr_code": "RH-01"}),
        contexto(ATUAL_VINCULO),
    )[0]

    assert codigos(resultado) == ["duplicado_no_cadastro"]


def test_reescrever_o_nome_que_vem_do_ponto_recusa_a_linha():
    resultado = validate(
        VINCULO,
        linhas({"registration_number": "1001", "name": "Ana P. Personagem", "hr_code": "RH-01"}),
        contexto(ATUAL_VINCULO),
    )[0]

    assert codigos(resultado) == ["campo_do_sync"]
    assert "Funcionario.Nome" in resultado.errors[0].message


# ---------------------------------------------------------------------------
# Cadastro — o template que atravessa duas tabelas
# ---------------------------------------------------------------------------
def test_regime_fora_do_catalogo_e_recusado_antes_do_banco():
    atual = {ANA: {**ATUAL_VINCULO[ANA], "employment_type": "clt", "ctps": None}}
    resultado = validate(
        CADASTRO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "employment_type": "efetivo",
                "ctps": "123456",
            }
        ),
        contexto(atual),
    )[0]

    assert codigos(resultado) == ["enum_invalido"]
    assert "clt" in resultado.errors[0].message


def test_uma_linha_pode_mudar_campo_de_duas_tabelas():
    atual = {ANA: {**ATUAL_VINCULO[ANA], "employment_type": "clt", "ctps": None}}
    resultado = validate(
        CADASTRO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "employment_type": "pj",
                "ctps": "123456/0001",
            }
        ),
        contexto(atual),
    )[0]

    assert resultado.status == "ok"
    assert resultado.values == {"employment_type": "pj", "ctps": "123456/0001"}


# ---------------------------------------------------------------------------
# Remuneração — vigência, nunca edição
# ---------------------------------------------------------------------------
def test_a_planilha_de_salario_intocada_nao_abre_faixa_nenhuma():
    # O caso que o `unchanged` existe para cobrir: baixar e subir sem editar não
    # pode virar uma vigência nova por pessoa.
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": date(2026, 1, 1),
                "salary": Decimal("2500"),
                "reason": "admissão",
            }
        ),
        contexto(ATUAL_REMUNERACAO),
    )[0]

    assert resultado.status == "unchanged"


def test_a_vigencia_nova_leva_a_faixa_inteira():
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": date(2026, 8, 1),
                "salary": Decimal("3000.00"),
                "reason": "promoção",
            }
        ),
        contexto(ATUAL_REMUNERACAO),
    )[0]

    assert resultado.status == "ok"
    assert resultado.values["salary"] == Decimal("3000.00")
    assert resultado.values["effective_from"] == date(2026, 8, 1)
    assert resultado.previous["salary"] == Decimal("2500.00")


def test_vigencia_na_mesma_data_da_vigente_e_sobreposicao_e_nao_correcao():
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": date(2026, 1, 1),
                "salary": Decimal("3000.00"),
                "reason": "correção",
            }
        ),
        contexto(ATUAL_REMUNERACAO),
    )[0]

    assert codigos(resultado) == ["vigencia_sobreposta"]
    assert "revogue" in resultado.errors[0].message


def test_vigencia_dentro_de_competencia_fechada_e_recusada():
    limite = retroactive_limit(HOJE, date(2026, 6, 30))
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": date(2026, 6, 30),
                "salary": Decimal("3000.00"),
                "reason": "acerto",
            }
        ),
        contexto(ATUAL_REMUNERACAO, limite=limite),
    )[0]

    assert "vigencia_retroativa" in codigos(resultado)


def test_o_primeiro_dia_aberto_da_folha_ainda_passa():
    limite = retroactive_limit(HOJE, date(2026, 6, 30))
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": date(2026, 7, 1),
                "salary": Decimal("3000.00"),
                "reason": "acerto",
            }
        ),
        contexto(ATUAL_REMUNERACAO, limite=limite),
    )[0]

    assert resultado.status == "ok"


def test_salario_apagado_numa_linha_que_muda_e_recusado():
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": date(2026, 8, 1),
                "salary": None,
                "reason": "promoção",
            }
        ),
        contexto(ATUAL_REMUNERACAO),
    )[0]

    assert "campo_obrigatorio" in codigos(resultado)


def test_data_digitada_em_texto_e_lida_como_data():
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": "01/08/2026",
                "salary": "3.000,00",
                "reason": "promoção",
            }
        ),
        contexto(ATUAL_REMUNERACAO),
    )[0]

    assert resultado.status == "ok"
    assert resultado.values["effective_from"] == date(2026, 8, 1)
    assert resultado.values["salary"] == Decimal("3000.00")


def test_data_ilegivel_recusa_a_linha_dizendo_o_formato():
    resultado = validate(
        REMUNERACAO,
        linhas(
            {
                "registration_number": "1001",
                "name": "Ana Personagem",
                "hr_code": "RH-01",
                "effective_from": "agosto",
                "salary": Decimal("3000.00"),
                "reason": "promoção",
            }
        ),
        contexto(ATUAL_REMUNERACAO),
    )[0]

    assert "data_invalida" in codigos(resultado)
    assert "dd/mm/aaaa" in resultado.errors[0].message


# ---------------------------------------------------------------------------
# O teto de retroatividade sai da folha, não de um número inventado
# ---------------------------------------------------------------------------
def test_sem_competencia_fechada_nao_ha_teto_de_retroatividade():
    # Não é "permitir tudo": vigência ausente, futura ou ilegível continua caindo.
    # É que não existe competência fechada para proteger.
    assert retroactive_limit(HOJE, None) > 365 * 100


def test_o_teto_e_o_dia_seguinte_a_ultima_competencia_fechada():
    limite = retroactive_limit(HOJE, date(2026, 6, 30))

    assert (HOJE - date(2026, 7, 1)).days == limite
    assert (HOJE - date(2026, 6, 30)).days == limite + 1


# ---------------------------------------------------------------------------
# ASO — um exame por pessoa, e o modelo imprime o mais recente
# ---------------------------------------------------------------------------
ASO = TEMPLATES["hr_exam"]

ATUAL_ASO: dict[Any, dict[str, Any]] = {
    ANA: {
        "registration_number": "1001",
        "name": "Ana Personagem",
        "hr_code": "RH-01",
        "type": "periodic",
        "performed_on": date(2025, 9, 2),
        "valid_until": date(2026, 9, 2),
        "result": "fit",
    },
    BRUNO: {"registration_number": "1002", "name": "Bruno Personagem", "hr_code": None},
}


def test_a_planilha_de_aso_intocada_nao_registra_exame_nenhum():
    """Baixar e subir de volta não pode criar um exame por pessoa."""
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1001",
                "hr_code": "RH-01",
                "name": "Ana Personagem",
                "type": "periodic",
                "performed_on": date(2025, 9, 2),
                "valid_until": date(2026, 9, 2),
                "result": "fit",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert [r.status for r in resultado] == ["unchanged"]


def test_o_exame_novo_leva_a_linha_inteira():
    """Meia linha nova não é um exame: tipo, data, validade e aptidão vão juntos."""
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1001",
                "hr_code": "RH-01",
                "name": "Ana Personagem",
                "type": "periodic",
                "performed_on": date(2026, 8, 20),
                "valid_until": date(2027, 8, 20),
                "result": "fit",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert resultado[0].status == "ok"
    assert resultado[0].values == {
        "type": "periodic",
        "performed_on": date(2026, 8, 20),
        "valid_until": date(2027, 8, 20),
        "result": "fit",
    }


def test_exame_anterior_ao_impresso_e_recusado():
    """O modelo carrega o mais recente: uma data anterior entraria a cada reenvio.

    Não é preciosismo de ordenação. A linha continuaria diferindo do que o modelo
    imprime na rodada seguinte, e o mesmo arquivo criaria uma cópia por vez.
    """
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1001",
                "hr_code": "RH-01",
                "name": "Ana Personagem",
                "type": "pre_employment",
                "performed_on": date(2024, 8, 15),
                "valid_until": date(2025, 8, 15),
                "result": "fit",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert codigos(resultado[0]) == ["exame_anterior"]


def test_exame_com_data_no_futuro_e_recusado():
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1002",
                "name": "Bruno Personagem",
                "type": "periodic",
                "performed_on": date(2026, 12, 1),
                "result": "fit",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert codigos(resultado[0]) == ["data_no_futuro"]


def test_validade_antes_da_realizacao_e_recusada():
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1002",
                "name": "Bruno Personagem",
                "type": "periodic",
                "performed_on": date(2026, 8, 1),
                "valid_until": date(2026, 7, 1),
                "result": "fit",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert codigos(resultado[0]) == ["validade_invalida"]


def test_aso_vencido_entra_sem_reclamacao():
    """Validade no passado é um fato do cadastro — é o que a lista existe para mostrar."""
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1002",
                "name": "Bruno Personagem",
                "type": "periodic",
                "performed_on": date(2024, 3, 1),
                "valid_until": date(2025, 3, 1),
                "result": "fit",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert resultado[0].status == "ok"


def test_exame_sem_tipo_numa_linha_que_escreve_e_recusado():
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1002",
                "name": "Bruno Personagem",
                "type": "",
                "performed_on": date(2026, 8, 1),
                "result": "fit",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert codigos(resultado[0]) == ["campo_obrigatorio"]


def test_aptidao_fora_do_catalogo_e_recusada_antes_do_banco():
    resultado = validate(
        ASO,
        linhas(
            {
                "registration_number": "1002",
                "name": "Bruno Personagem",
                "type": "periodic",
                "performed_on": date(2026, 8, 1),
                "result": "apto",
            }
        ),
        contexto(ATUAL_ASO),
    )

    assert codigos(resultado[0]) == ["enum_invalido"]
