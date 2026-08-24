"""Os seis erros de linha que o R1 tem de recusar — e o que não é erro.

Um validador só vale pelo que ele RECUSA, então cada caso aqui é uma linha que
tem de falhar, com o par que tem de passar ao lado. O par importa tanto quanto:
um validador que recusa tudo passa em qualquer teste de recusa e trava o DP.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from operax.rh import validators as v
from tests.fixtures import rh_sintetico as fx

HOJE = date(2026, 8, 24)
LIMITE = 90


def codigos(erros: list[v.LineError]) -> set[str]:
    return {e.code for e in erros}


# --- 1. chaves divergentes --------------------------------------------------
def test_matricula_e_id_rh_apontando_para_pessoas_diferentes_e_erro_de_linha() -> None:
    r = v.check_keys(
        fx.LINHA_CHAVES_DIVERGEM,
        by_registration=fx.POR_MATRICULA,
        by_hr_code=fx.POR_HR_CODE,
    )
    assert r.employee_id is None, "escolher uma das duas grava na pessoa errada"
    assert codigos(list(r.errors)) == {"chaves_divergem"}


def test_a_mensagem_de_divergencia_carrega_as_duas_chaves() -> None:
    # Sem os dois nomes, o DP não tem como saber qual das duas corrigir.
    (erro,) = v.check_keys(
        fx.LINHA_CHAVES_DIVERGEM,
        by_registration=fx.POR_MATRICULA,
        by_hr_code=fx.POR_HR_CODE,
    ).errors
    assert "1001" in erro.message and "RH-02" in erro.message


def test_id_rh_vazio_ainda_resolve_pela_matricula() -> None:
    # É a fase inteira do vínculo: `hr_code` está nulo para todo mundo até o
    # template de vínculo voltar preenchido.
    r = v.check_keys(
        fx.LINHA_SEM_HR_CODE, by_registration=fx.POR_MATRICULA, by_hr_code=fx.POR_HR_CODE
    )
    assert r.employee_id == fx.CARLA
    assert not r.errors


def test_linha_sem_chave_nenhuma_nao_vira_pessoa_nova() -> None:
    r = v.check_keys({}, by_registration=fx.POR_MATRICULA, by_hr_code=fx.POR_HR_CODE)
    assert r.employee_id is None
    assert codigos(list(r.errors)) == {"sem_chave"}


def test_as_duas_chaves_concordando_resolvem_sem_erro() -> None:
    r = v.check_keys(fx.LINHA_OK, by_registration=fx.POR_MATRICULA, by_hr_code=fx.POR_HR_CODE)
    assert r.employee_id == fx.ANA
    assert not r.errors


# --- 2. campo do sync alterado ---------------------------------------------
def test_alterar_campo_do_secullum_falha_a_linha() -> None:
    erros = v.check_owned_fields(fx.LINHA_MEXE_NO_SYNC, fx.ATUAL_ANA, table="employee")
    assert codigos(erros) == {"campo_do_sync"}
    assert {e.column for e in erros} == {"name", "status"}


def test_a_recusa_diz_de_qual_coluna_do_espelho_o_valor_vem() -> None:
    # É o que a tela repete como "Secullum · leitura de HH:MM"; sem a origem, a
    # mensagem vira "não pode" sem dizer por quê.
    (erro,) = [
        e
        for e in v.check_owned_fields(fx.LINHA_MEXE_NO_SYNC, fx.ATUAL_ANA, table="employee")
        if e.column == "name"
    ]
    assert "Funcionario.Nome" in erro.message


def test_repetir_o_valor_atual_nao_e_alteracao() -> None:
    # Todo template sai pré-preenchido, então a maioria das células volta igual.
    # Tratar isso como alteração recusaria o arquivo inteiro.
    assert v.check_owned_fields({"name": "Ana Personagem"}, fx.ATUAL_ANA, table="employee") == []


def test_numero_de_planilha_e_texto_do_banco_sao_o_mesmo_valor() -> None:
    atual = {"registration_number": "1001"}
    assert v.check_owned_fields({"registration_number": 1001}, atual, table="employee") == []
    assert v.check_owned_fields({"registration_number": " 1001 "}, atual, table="employee") == []


def test_campo_do_rh_passa_livre() -> None:
    assert v.check_owned_fields(fx.LINHA_OK, fx.ATUAL_ANA, table="employee") == []


# --- 3. enum inválido -------------------------------------------------------
def test_valor_fora_do_catalogo_e_recusado_antes_de_chegar_ao_banco() -> None:
    erros = v.check_enums(fx.LINHA_ENUM_INVALIDO, table="employee")
    assert codigos(erros) == {"enum_invalido"}


def test_a_recusa_de_enum_lista_o_que_seria_aceito() -> None:
    (erro,) = v.check_enums(fx.LINHA_ENUM_INVALIDO, table="employee")
    assert "clt" in erro.message and "pj" in erro.message


def test_celula_vazia_nao_e_enum_invalido() -> None:
    assert v.check_enums({"employment_type": ""}, table="employee") == []


# --- 4. vigência retroativa -------------------------------------------------
def test_vigencia_alem_do_limite_e_recusada() -> None:
    erros = v.check_effective_from(date(2025, 1, 10), hoje=HOJE, limite_dias=LIMITE)
    assert codigos(erros) == {"vigencia_retroativa"}


def test_vigencia_dentro_do_limite_passa() -> None:
    assert v.check_effective_from(date(2026, 7, 1), hoje=HOJE, limite_dias=LIMITE) == []


def test_vigencia_no_futuro_e_recusada() -> None:
    assert codigos(v.check_effective_from(date(2026, 9, 1), hoje=HOJE, limite_dias=LIMITE)) == {
        "vigencia_futura"
    }


def test_vigencia_que_nao_e_data_e_recusada_como_tal() -> None:
    assert codigos(v.check_effective_from("ontem", hoje=HOJE, limite_dias=LIMITE)) == {
        "data_invalida"
    }


# --- 5. parcela inconsistente ----------------------------------------------
def test_parcelas_que_nao_somam_o_acordo_sao_recusadas() -> None:
    erros = v.check_installments(
        fx.ACORDO_OK["total_amount"], fx.ACORDO_OK["installment_count"], fx.PARCELAS_NAO_SOMAM
    )
    assert "parcelas_nao_somam" in codigos(erros)


def test_numeracao_com_buraco_e_recusada() -> None:
    erros = v.check_installments(
        fx.ACORDO_OK["total_amount"],
        fx.ACORDO_OK["installment_count"],
        fx.PARCELAS_NUMERACAO_PULADA,
    )
    assert "numeracao_de_parcelas" in codigos(erros)


def test_quantidade_declarada_diferente_da_que_veio_e_recusada() -> None:
    erros = v.check_installments(Decimal("800.00"), 3, fx.PARCELAS_OK[:2])
    assert "quantidade_de_parcelas" in codigos(erros)


def test_um_centavo_de_arredondamento_nao_derruba_o_acordo() -> None:
    # A planilha do cliente carrega valor digitado à mão; recusar por um centavo
    # manda o DP procurar erro onde não há.
    parcelas = [
        {"number": 1, "amount": Decimal("400.00")},
        {"number": 2, "amount": Decimal("400.00")},
        {"number": 3, "amount": Decimal("399.99")},
    ]
    assert v.check_installments(Decimal("1200.00"), 3, parcelas) == []


def test_acordo_coerente_passa() -> None:
    assert (
        v.check_installments(
            fx.ACORDO_OK["total_amount"], fx.ACORDO_OK["installment_count"], fx.PARCELAS_OK
        )
        == []
    )


# --- 6. afastamento sobreposto ---------------------------------------------
def test_periodo_que_encosta_em_afastamento_existente_e_recusado() -> None:
    erros = v.check_leave_overlap(
        date(2026, 3, 15), date(2026, 3, 25), existentes=fx.AFASTAMENTOS_ANA
    )
    assert codigos(erros) == {"afastamento_sobreposto"}


def test_afastamento_em_aberto_cobre_daqui_em_diante() -> None:
    # `end_date` nulo é normal, e tratar o intervalo como fechado no início
    # deixaria passar qualquer período posterior.
    erros = v.check_leave_overlap(date(2026, 12, 1), None, existentes=fx.AFASTAMENTOS_ANA)
    assert codigos(erros) == {"afastamento_sobreposto"}


def test_periodo_no_intervalo_livre_passa() -> None:
    assert (
        v.check_leave_overlap(date(2026, 5, 4), date(2026, 5, 10), existentes=fx.AFASTAMENTOS_ANA)
        == []
    )


def test_fim_antes_do_inicio_e_recusado() -> None:
    assert codigos(v.check_leave_overlap(date(2026, 5, 10), date(2026, 5, 4), existentes=[])) == {
        "periodo_invertido"
    }


# --- os quatro domínios compõem os mesmos seis ------------------------------
def test_o_dominio_de_cadastro_junta_dono_e_enum_num_funil_so() -> None:
    linha = dict(fx.LINHA_MEXE_NO_SYNC) | {"employment_type": "efetivo"}
    assert codigos(v.validate_registration(linha, fx.ATUAL_ANA)) == {
        "campo_do_sync",
        "enum_invalido",
    }


def test_o_dominio_de_afastamento_recusa_categoria_e_sobreposicao_juntas() -> None:
    linha = {
        "category": "ferias",
        "start_date": date(2026, 3, 15),
        "end_date": date(2026, 3, 25),
    }
    assert codigos(v.validate_leave(linha, existentes=fx.AFASTAMENTOS_ANA)) == {
        "enum_invalido",
        "afastamento_sobreposto",
    }


def test_o_dominio_de_acordo_recusa_tipo_e_soma_juntos() -> None:
    acordo = dict(fx.ACORDO_OK) | {"type": "prejuizo"}
    assert codigos(v.validate_agreement(acordo, fx.PARCELAS_NAO_SOMAM)) == {
        "enum_invalido",
        "parcelas_nao_somam",
    }


def test_a_linha_boa_atravessa_o_funil_inteiro_sem_erro() -> None:
    assert v.validate_registration(fx.LINHA_OK, fx.ATUAL_ANA) == []
