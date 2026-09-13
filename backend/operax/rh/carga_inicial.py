"""A planilha viva do cliente, virada em template — e na lista do que não entrou.

Roda na implantação, num terminal, contra um arquivo local. Não abre conexão com
o banco, não tem credencial e não escreve linha nenhuma: a saída são os mesmos
.xlsx que o DP baixaria da tela, agora preenchidos, mais o relatório do que ficou
de fora e por quê. A entrada continua sendo template + preview + confirmação
humana, que é o único caminho de escrita que existe (SPEC §6.4).

POR QUE ELE PREENCHE O MODELO BAIXADO EM VEZ DE GERAR UM
O template tem identidade: `_meta` com tenant, versão de layout e o hash do
cabeçalho. Um conversor que gera o arquivo do zero é um conversor que pode gerar
identidade errada — e o arquivo com identidade errada é aceito pelo import, que é
o pior desfecho possível. Preenchendo o modelo que o próprio sistema emitiu, a
identidade é a que veio, e o ensaio prova isso mandando o resultado de volta por
`workbook.parse`: qualquer célula de cabeçalho fora do lugar recusa o arquivo
inteiro.

O QUE É "FECHAR EM 100%"
Toda linha da planilha original termina em um de quatro lugares, e a soma dos
quatro é o total lido:

  destino     — foi para uma célula de um template emitido;
  parqueado   — foi convertida para o formato de destino e gravada num .csv,
                porque a tabela de destino ainda não tem caminho de escrita;
  conferência — não se importa por decisão (DESLIGADOS), e virou comparação;
  descarte    — não entrou, com o motivo nomeado.

O balanço é conferido no fim e o processo termina em erro se não fechar. Um
conversor que perde linha em silêncio é pior do que um que não roda.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from operax.rh.templates import SEM_TEMPLATE, TEMPLATES, Template
from operax.rh.workbook import META_SHEET

# Quantas linhas do topo o leitor examina à procura do cabeçalho. A planilha real
# tem cabeçalho na 1, na 2, na 6 e na 8 — não por desleixo, mas porque as abas
# ganharam título, filtro e legenda em cima do dado ao longo dos anos.
_LINHAS_DE_TOPO = 12

# `data_only=True` devolve o último valor calculado; numa fórmula quebrada esse
# valor é o próprio texto do erro. Ler "#REF!" como conteúdo escreveria "#REF!"
# dentro do sistema.
_ERROS_EXCEL = frozenset({"#REF!", "#N/A", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"})

_SUFIXO_DUPLICADA = re.compile(r"^(?P<base>.+?)\s*(?:\(\d+\)|-?\s*COPIA|\s\d)$")


class Purpose(StrEnum):
    """O que se faz com as linhas de uma aba."""

    #: Preenchem um template emitido, que o DP sobe pela tela de Importação.
    TEMPLATE = "template"
    #: Não se importam por decisão: viram comparação contra o que o ponto diz.
    CONFERENCE = "conferencia"
    #: Convertidas para o formato de destino e guardadas em .csv — a tabela alvo
    #: ainda não tem caminho de escrita pelo painel.
    PARKED = "parqueado"
    #: Não entram. Dashboard, derivado, ou assunto de outra tela.
    OUT = "fora"


@dataclass(frozen=True, slots=True)
class SourceColumn:
    """Uma coluna da planilha do cliente e para onde ela vai — ou não vai."""

    label: str
    #: "<destino>.<coluna>", onde destino é um tipo de template (`hr_link`) ou
    #: uma tabela de `app` (`occupational_exam`). `None` = sem destino.
    target: str | None = None
    kind: str = "text"
    #: Tradução de valor, quando a planilha escreve em português o que a coluna
    #: guarda em inglês. Chave já normalizada.
    values: Mapping[str, str] | None = None
    #: Preenchido quando a coluna é recusada **por regra**, e não por falta de
    #: lugar. É o que faz o relatório servir de prova de LGPD.
    refused: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatrixSpec:
    """Uma aba em que o dado está no cabeçalho, e não na célula.

    FÉRIAS é uma matriz: uma linha por pessoa, um par de colunas por ano. Vira
    formato longo — uma linha por período — porque `app.leave_period` guarda
    período, e uma tabela com uma coluna por ano de calendário é uma tabela que
    precisa de migration todo mês de janeiro.
    """

    category: str
    pattern: re.Pattern[str]
    target: str


@dataclass(frozen=True, slots=True)
class LatestOnly:
    """A planilha traz histórico e o template carrega um registro por pessoa.

    Vence a linha de data maior. As outras não somem: os destinos delas são
    reescritos para a tabela, e saem no .csv parqueado — o histórico fica
    convertido, esperando quem o carregue.

    Sem isto, várias linhas da mesma pessoa escreveriam na mesma célula do modelo
    e a última lida ganharia. Em silêncio, e pela ordem da planilha.
    """

    by: str
    park_as: str


@dataclass(frozen=True, slots=True)
class SourceSheet:
    """Uma aba da planilha do cliente."""

    name: str
    purpose: Purpose
    #: Por que não vira template. Obrigatório em tudo que não é TEMPLATE.
    reason: str = ""
    columns: tuple[SourceColumn, ...] = ()
    #: A coluna que diz de quem é a linha.
    key: str = "MATRICULA"
    matrix: MatrixSpec | None = None
    latest_only: LatestOnly | None = None
    aliases: tuple[str, ...] = ()


def normalize(texto: Any) -> str:
    """Rótulo comparável: sem acento, sem pontuação de fim, caixa alta.

    "Férias", "FERIAS" e "FÉRIAS " são a mesma aba, e "CONTROLE PARC." é a mesma
    coluna que "CONTROLE PARC". Comparar a string crua faz o mapa depender de
    como o cliente digitou.
    """
    if texto is None:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    limpo = re.sub(r"[\s ]+", " ", sem_acento).strip().upper()
    return limpo.rstrip(".:")


# ---------------------------------------------------------------------------
# O mapa: aba da planilha -> destino
# ---------------------------------------------------------------------------
# É a tabela §7 de `docs/DECISAO-RH-UPLOAD-TELAS.md` escrita em código, porque um
# mapa que vive só na prosa é um mapa que ninguém executa. Cada aba das 17 está
# aqui — inclusive as que não entram, que é o que permite ao relatório afirmar
# que nada foi esquecido em vez de que nada foi encontrado.

#: A coluna identifica a linha e nunca é escrita: o sistema já a imprime no
#: modelo, e o conversor só a usa para achar de quem é a linha.
CHAVE = "chave"

_DASHBOARDS = (
    "QUADRO GERAL",
    "GERAL",
    "FACE GERAL",
    "QUADRO_POSTOS",
    "CESTAS",
    "PLANILHA1",
)

_REGIME = {
    "CLT": "clt",
    "PJ": "pj",
    "ESTAGIO": "internship",
    "ESTAGIARIO": "internship",
    "TEMPORARIO": "temporary",
    "APRENDIZ": "apprentice",
    "JOVEM APRENDIZ": "apprentice",
    "TERCEIRO": "contractor",
    "TERCEIRIZADO": "contractor",
}

_TIPO_ASO = {
    "ADMISSIONAL": "pre_employment",
    "PERIODICO": "periodic",
    "DEMISSIONAL": "exit",
    "RETORNO AO TRABALHO": "return_to_work_exam",
    "MUDANCA DE FUNCAO": "job_change",
}

_RESULTADO_ASO = {
    "APTO": "fit",
    "INAPTO": "unfit",
    "APTO COM RESTRICAO": "fit_with_restriction",
}

_CATEGORIA_AFASTAMENTO = {
    "FERIAS": "vacation",
    "ATESTADO": "leave_period",
    "FALTA": "leave_period",
    "LICENCA": "leave_of_absence",
    "AFASTAMENTO": "leave_of_absence",
    "SUSPENSAO": "suspension",
}

_TIPO_MOVIMENTACAO = {
    "ADMISSAO": "hire",
    "DEMISSAO": "termination",
    "TRANSFERENCIA": "transfer",
    "PROMOCAO": "promotion",
    "AFASTAMENTO": "leave_period",
    "RETORNO": "return_to_work",
}

_TIPO_ACORDO = {
    "PARCELAMENTO": "installment_plan",
    "AVARIA VEICULO": "vehicle_damage",
    "SINISTRO": "vehicle_damage",
    "AVARIA EQUIPAMENTO": "equipment_damage",
    "ADIANTAMENTO": "advance",
    "EMPRESTIMO": "loan",
    "BENEFICIO": "benefit",
}

_SITUACAO_ACORDO = {
    "ATIVO": "active",
    "QUITADO": "settled",
    "CANCELADO": "cancelled",
    "SUSPENSO": "suspended",
}

_SITUACAO_PARCELA = {
    "PENDENTE": "pending",
    "DESCONTADA": "processed",
    "PROCESSADA": "processed",
    "CANCELADA": "cancelled",
    "RENEGOCIADA": "renegotiated",
}

_CID = (
    "diagnóstico não entra em lugar nenhum (regra 10): sem coluna em template, "
    "sem campo em tela, sem coluna em tabela"
)
_BANCARIO = (
    "fora do escopo v1: folha é do Domínio, e conta bancária no OperaX seria um "
    "domínio sensível novo — decisão à parte"
)
_SEM_UUID = (
    "o conversor não consulta o banco: sai o nome, e a resolução acontece quando "
    "a tabela ganhar caminho de escrita"
)


def _sem_coluna(label: str, chave: str) -> SourceColumn:
    """Coluna que a SPEC §4 nomeia e a carga inicial recusa.

    O motivo vem de `ownership.SEM_COLUNA`, e não de um texto escrito aqui: a
    decisão foi tomada uma vez, no R1, e é ela que precisa aparecer na ata da
    implantação.

    ⚠️ "Sem coluna" deixou de ser verdade para oito dos dez em 06-07/09/2026, e
    o texto seguiu dizendo que não havia lugar. O nome desta função ficou, mas o
    motivo agora distingue **não há onde gravar** de **há, e a carga ainda não
    grava** — e `scripts/95_teste_matriz_rh.py` confere as duas afirmações contra
    o schema. O que NÃO mudou é a recusa: o escopo da v1 é decisão do dono.
    """
    from operax.rh.ownership import SEM_COLUNA

    return SourceColumn(label, refused=f"fora do escopo v1 — {SEM_COLUNA[chave].motivo}")


DADOS_FUNCIONARIOS = SourceSheet(
    name="DADOS FUNCIONARIOS",
    purpose=Purpose.TEMPLATE,
    aliases=("DADOS FUNCIONARIO", "CADASTRO", "DADOS"),
    columns=(
        SourceColumn("MATRICULA", CHAVE, aliases=("MATR", "MAT")),
        SourceColumn("NOME", CHAVE, aliases=("NOME COMPLETO", "FUNCIONARIO")),
        SourceColumn("ID RH", "hr_link.hr_code", aliases=("CODIGO RH", "ID")),
        SourceColumn(
            "REGIME",
            "hr_employee.employment_type",
            values=_REGIME,
            aliases=("TIPO DE CONTRATO", "VINCULO", "CONTRATO"),
        ),
        SourceColumn("CTPS", "hr_employee.ctps", aliases=("CARTEIRA", "CTPS/SERIE")),
        SourceColumn(
            "SALARIO", "hr_compensation.salary", kind="decimal", aliases=("SALARIO BASE",)
        ),
        SourceColumn(
            "DATA ULTIMO REAJUSTE",
            "hr_compensation.effective_from",
            kind="date",
            aliases=("ULTIMO REAJUSTE", "DATA REAJUSTE"),
        ),
        # Sem data de reajuste, a faixa vigente vale desde a admissão: é a única
        # data que se pode afirmar sem inventar. Quantas linhas caíram aqui vai
        # no relatório — a suposição fica visível, não implícita.
        SourceColumn("ADMISSAO", "@fallback:hr_compensation.effective_from", kind="date"),
        SourceColumn("CARGO", "employee_position.cargo", aliases=("FUNCAO",)),
        SourceColumn(
            "SUPERVISOR",
            refused=(
                "pendente de confirmação com o cliente; tratado como sync até lá (ownership.MATRIX)"
            ),
        ),
        SourceColumn("BANCO", refused=_BANCARIO),
        SourceColumn("AGENCIA", refused=_BANCARIO),
        SourceColumn("CONTA", refused=_BANCARIO),
        SourceColumn("PIX", refused=_BANCARIO),
        _sem_coluna("CBO", "cbo"),
        _sem_coluna("UNIFORME", "uniforme"),
        _sem_coluna("NIVEL", "nivel"),
        _sem_coluna("VR", "beneficios_vr"),
        _sem_coluna("VT", "beneficios_vt"),
        _sem_coluna("CESTA BASICA", "beneficios_cesta"),
        _sem_coluna("PLANO DE SAUDE", "beneficios_planos"),
        _sem_coluna("PERICULOSIDADE", "periculosidade"),
        _sem_coluna("CARGO DE CONFIANCA", "cargo_de_confianca"),
        _sem_coluna("UNIDADE DE ATUACAO", "unidade_de_atuacao"),
    ),
)


SHEETS: tuple[SourceSheet, ...] = (
    DADOS_FUNCIONARIOS,
    SourceSheet(
        name="DESLIGADOS",
        purpose=Purpose.CONFERENCE,
        reason=(
            "`app.employee.status` é do sync (`Funcionario.Demissao`). Duas fontes para o "
            "mesmo fato é uma a mais: a aba vira conferência do que o ponto já sabe"
        ),
        columns=(
            SourceColumn("MATRICULA", CHAVE),
            SourceColumn("NOME", "conferencia.name"),
            SourceColumn(
                "DATA DEMISSAO",
                "conferencia.terminated_on",
                kind="date",
                aliases=("DEMISSAO", "DATA"),
            ),
            SourceColumn("CID", refused=_CID),
            SourceColumn("MOTIVO", refused="`app.employee` não guarda motivo de desligamento"),
        ),
    ),
    SourceSheet(
        name="FALTAS_ATESTADOS",
        purpose=Purpose.PARKED,
        reason=SEM_TEMPLATE["hr_leave"],
        columns=(
            SourceColumn("MATRICULA", CHAVE),
            SourceColumn(
                "TIPO", "leave_period.category", values=_CATEGORIA_AFASTAMENTO, aliases=("MOTIVO",)
            ),
            SourceColumn("INICIO", "leave_period.start_date", kind="date", aliases=("DATA",)),
            SourceColumn("FIM", "leave_period.end_date", kind="date", aliases=("RETORNO",)),
            SourceColumn("CID", refused=_CID),
        ),
    ),
    SourceSheet(
        name="MOVIMENTACOES",
        purpose=Purpose.PARKED,
        reason=SEM_TEMPLATE["hr_movement"],
        columns=(
            SourceColumn("MATRICULA", CHAVE),
            SourceColumn("TIPO", "workforce_movement.type", values=_TIPO_MOVIMENTACAO),
            SourceColumn("DATA", "workforce_movement.event_date", kind="date"),
            SourceColumn("UNIDADE DESTINO", "workforce_movement.unit_id", aliases=("UNIDADE",)),
            SourceColumn("OBSERVACAO", "workforce_movement.notes", aliases=("OBS",)),
        ),
    ),
    SourceSheet(
        name="FERIAS",
        purpose=Purpose.PARKED,
        reason=SEM_TEMPLATE["hr_leave"],
        columns=(SourceColumn("MATRICULA", CHAVE), SourceColumn("NOME", CHAVE)),
        matrix=MatrixSpec(
            category="vacation",
            pattern=re.compile(r"^(?P<ano>\d{4})\s*(?P<lado>INICIO|FIM|GOZO|RETORNO)$"),
            target="leave_period",
        ),
    ),
    SourceSheet(
        name="CNH",
        purpose=Purpose.PARKED,
        reason=SEM_TEMPLATE["hr_document"],
        columns=(
            SourceColumn("MATRICULA", CHAVE),
            SourceColumn("CATEGORIA", "document.type_id"),
            SourceColumn("EMISSAO", "document.issued_on", kind="date"),
            SourceColumn("VALIDADE", "document.valid_until", kind="date", aliases=("VENCIMENTO",)),
            SourceColumn("NUMERO", refused="`app.document` não guarda número de documento"),
        ),
    ),
    SourceSheet(
        name="VENCIMENTO ASO",
        purpose=Purpose.TEMPLATE,
        aliases=("ASO", "VENCIMENTOS ASO"),
        # O modelo imprime o exame vigente de cada pessoa; a planilha do cliente
        # guarda o histórico na mesma aba. O mais recente sobe, o resto é
        # convertido e parqueado.
        latest_only=LatestOnly(by="hr_exam.performed_on", park_as="occupational_exam"),
        columns=(
            SourceColumn("MATRICULA", CHAVE),
            SourceColumn("TIPO", "hr_exam.type", values=_TIPO_ASO, aliases=("EXAME",)),
            SourceColumn("DATA", "hr_exam.performed_on", kind="date", aliases=("REALIZACAO",)),
            SourceColumn("VENCIMENTO", "hr_exam.valid_until", kind="date", aliases=("VALIDADE",)),
            SourceColumn(
                "RESULTADO", "hr_exam.result", values=_RESULTADO_ASO, aliases=("APTIDAO",)
            ),
            SourceColumn(
                "RESTRICAO",
                refused=(
                    "descrição de restrição é dado de saúde detalhado (regra 10): a tabela "
                    "guarda `fit_with_restriction` e nada mais"
                ),
            ),
        ),
    ),
    SourceSheet(
        name="SINISTROS",
        purpose=Purpose.PARKED,
        reason=SEM_TEMPLATE["hr_agreement"],
        columns=(
            SourceColumn("MATRICULA", CHAVE),
            SourceColumn("TIPO", "financial_agreement.type", values=_TIPO_ACORDO),
            SourceColumn("DESCRICAO", "financial_agreement.description", aliases=("HISTORICO",)),
            SourceColumn(
                "VALOR", "financial_agreement.total_amount", kind="decimal", aliases=("TOTAL",)
            ),
            SourceColumn("PARCELAS", "financial_agreement.installment_count"),
            SourceColumn("DATA", "financial_agreement.agreement_date", kind="date"),
            SourceColumn(
                "SITUACAO",
                "financial_agreement.status",
                values=_SITUACAO_ACORDO,
                aliases=("STATUS",),
            ),
        ),
    ),
    SourceSheet(
        name="CONTROLE PARC",
        purpose=Purpose.PARKED,
        reason=SEM_TEMPLATE["hr_agreement"],
        aliases=("CONTROLE PARCELAS", "PARCELAS"),
        columns=(
            SourceColumn("MATRICULA", CHAVE),
            SourceColumn("PARCELA", "agreement_installment.number"),
            SourceColumn("ANO", "agreement_installment.period_year"),
            SourceColumn("MES", "agreement_installment.period_month"),
            SourceColumn("VALOR", "agreement_installment.amount", kind="decimal"),
            SourceColumn("SITUACAO", "agreement_installment.status", values=_SITUACAO_PARCELA),
        ),
    ),
    SourceSheet(
        name="UNIDADES",
        purpose=Purpose.OUT,
        reason=(
            "curadoria de unidade é tela da Administração (`app.unit`, `app.unit_secullum_map`), "
            "não carga de RH"
        ),
    ),
    SourceSheet(
        name="COD POSTOS",
        purpose=Purpose.OUT,
        aliases=("CODIGO POSTOS", "POSTOS"),
        reason=(
            "pendência 3: candidata a fonte de escala esperada, avaliada depois desta etapa "
            "(DECISAO-RH-UPLOAD-TELAS §10)"
        ),
    ),
    *(
        SourceSheet(
            name=nome,
            purpose=Purpose.OUT,
            reason="dashboard ou derivado — o sistema substitui a aba, não a importa",
        )
        for nome in _DASHBOARDS
    ),
)

_POR_NOME: dict[str, SourceSheet] = {}
for _sheet in SHEETS:
    for _nome in (_sheet.name, *_sheet.aliases):
        _POR_NOME[normalize(_nome)] = _sheet


# ---------------------------------------------------------------------------
# Leitura da planilha viva
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class SourceRow:
    """Uma linha da planilha do cliente, já traduzida para os nomes de destino."""

    sheet: str
    line: int
    key: str
    #: "<destino>.<coluna>" -> valor no tipo do banco.
    values: dict[str, Any] = field(default_factory=dict)
    #: Períodos extraídos de uma aba em matriz (FÉRIAS).
    periods: list[tuple[date, date]] = field(default_factory=list)
    #: O que não deu para aproveitar nesta linha, com o motivo.
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SheetRead:
    """O que foi lido de uma aba — inclusive quando não foi nada."""

    title: str
    sheet: SourceSheet | None
    hidden: bool = False
    header_row: int | None = None
    rows: list[SourceRow] = field(default_factory=list)
    #: Rótulos presentes no arquivo que o mapa não conhece nem recusa.
    unmapped: list[str] = field(default_factory=list)
    #: Colunas encontradas no arquivo e recusadas **por regra**, com o motivo. É
    #: a prova de que o CID estava lá e não entrou — a lista de colunas que o
    #: mapa recusa em tese não prova nada sobre este arquivo.
    refused_found: list[tuple[str, str]] = field(default_factory=list)
    #: Rótulos que a matriz de FÉRIAS reconheceu.
    matrix_columns: list[str] = field(default_factory=list)
    broken_cells: int = 0
    duplicate_of: str | None = None
    #: Linhas com célula preenchida que não puderam virar dado.
    unread: int = 0


def _valor(bruto: Any) -> Any:
    """A célula, ou nada — e "#REF!" é nada."""
    if bruto is None:
        return None
    if isinstance(bruto, str):
        texto = bruto.strip()
        if not texto or texto in _ERROS_EXCEL:
            return None
        return texto
    return bruto


def _e_quebrada(bruto: Any) -> bool:
    return isinstance(bruto, str) and bruto.strip() in _ERROS_EXCEL


def _as_date(bruto: Any) -> date | None:
    if isinstance(bruto, datetime):
        return bruto.date()
    if isinstance(bruto, date):
        return bruto
    texto = str(bruto).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _as_decimal(bruto: Any) -> Decimal | None:
    if isinstance(bruto, Decimal):
        return bruto
    if isinstance(bruto, (int, float)):
        return Decimal(str(bruto))
    texto = str(bruto).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def _converter(column: SourceColumn, bruto: Any) -> tuple[Any, str | None]:
    """O valor da célula no tipo e no vocabulário do banco, ou o motivo de não ir."""
    if column.kind == "date":
        convertido = _as_date(bruto)
        if convertido is None:
            return None, f"{column.label}: {bruto!r} não é uma data"
        return convertido, None
    if column.kind == "decimal":
        convertido = _as_decimal(bruto)
        if convertido is None:
            return None, f"{column.label}: {bruto!r} não é um valor"
        return convertido, None
    texto = str(bruto).strip()
    if column.values is not None:
        traduzido = column.values.get(normalize(texto))
        if traduzido is None:
            return None, f"{column.label}: {texto!r} não está no catálogo de valores"
        return traduzido, None
    return texto, None


def _indice(sheet: SourceSheet) -> dict[str, SourceColumn]:
    indice: dict[str, SourceColumn] = {}
    for column in sheet.columns:
        for rotulo in (column.label, *column.aliases):
            indice[normalize(rotulo)] = column
    return indice


def _achar_cabecalho(ws: Worksheet, sheet: SourceSheet) -> tuple[int, dict[int, SourceColumn]]:
    """A linha em que o cabeçalho está de fato, e as colunas que ela nomeia.

    Não é o primeiro `for` do arquivo: a aba tem título, filtro e legenda em cima
    do dado, e a linha 1 costuma ser o nome da empresa. Procura-se a linha do
    topo que casa mais rótulos conhecidos — quem manda é o mapa, não a posição.
    """
    indice = _indice(sheet)
    melhor_linha, melhor_casadas, melhor_colunas = 0, 0, {}

    for numero, celulas in enumerate(ws.iter_rows(min_row=1, max_row=_LINHAS_DE_TOPO), start=1):
        colunas: dict[int, SourceColumn] = {}
        casadas = 0
        for posicao, celula in enumerate(celulas, start=1):
            rotulo = normalize(_valor(celula.value))
            if not rotulo:
                continue
            achada = indice.get(rotulo)
            if achada is not None:
                colunas[posicao] = achada
                casadas += 1
            elif sheet.matrix and sheet.matrix.pattern.match(rotulo):
                casadas += 1
        if casadas > melhor_casadas:
            melhor_linha, melhor_casadas, melhor_colunas = numero, casadas, colunas

    # Duas colunas conhecidas: o suficiente para não confundir um título com um
    # cabeçalho, e pouco o bastante para uma aba de três colunas ser encontrada.
    if melhor_casadas < 2:
        return 0, {}
    return melhor_linha, melhor_colunas


def _ler_matriz(
    ws: Worksheet, sheet: SourceSheet, header_row: int
) -> tuple[dict[int, tuple[str, str]], list[str]]:
    """As colunas do cabeçalho que são ano+lado, agrupadas por ano."""
    assert sheet.matrix is not None
    encontradas: dict[int, tuple[str, str]] = {}
    rotulos: list[str] = []
    for celulas in ws.iter_rows(min_row=header_row, max_row=header_row):
        for posicao, celula in enumerate(celulas, start=1):
            rotulo = normalize(_valor(celula.value))
            achado = sheet.matrix.pattern.match(rotulo) if rotulo else None
            if achado:
                lado = "fim" if achado["lado"] in ("FIM", "RETORNO") else "inicio"
                encontradas[posicao] = (achado["ano"], lado)
                rotulos.append(rotulo)
    return encontradas, rotulos


def _linha_vazia(celulas: Iterable[Any]) -> bool:
    return all(_valor(c.value) is None for c in celulas)


def _ler_aba(ws: Worksheet, sheet: SourceSheet, leitura: SheetRead) -> None:
    """As linhas de uma aba mapeada, já nos nomes de destino."""
    header_row, colunas = _achar_cabecalho(ws, sheet)
    if not header_row:
        # Sem cabeçalho reconhecível não há como saber o que é cada coluna, e
        # adivinhar pela posição é como se importa o salário de um na linha de
        # outro. A aba inteira vira descarte, com as linhas contadas.
        leitura.unread = sum(
            0 if _linha_vazia(celulas) else 1 for celulas in ws.iter_rows(min_row=1)
        )
        return

    leitura.header_row = header_row
    matriz: dict[int, tuple[str, str]] = {}
    if sheet.matrix:
        matriz, leitura.matrix_columns = _ler_matriz(ws, sheet, header_row)

    for column in colunas.values():
        if column.refused is not None:
            leitura.refused_found.append((column.label, column.refused))

    conhecidas = set(colunas) | set(matriz)
    for celulas in ws.iter_rows(min_row=header_row, max_row=header_row):
        for posicao, celula in enumerate(celulas, start=1):
            rotulo = _valor(celula.value)
            if rotulo is not None and posicao not in conhecidas:
                leitura.unmapped.append(str(rotulo))

    chave_normalizada = normalize(sheet.key)
    for numero, celulas in enumerate(ws.iter_rows(min_row=header_row + 1), start=header_row + 1):
        if _linha_vazia(celulas):
            continue
        leitura.broken_cells += sum(1 for c in celulas if _e_quebrada(c.value))
        row = SourceRow(sheet=sheet.name, line=numero, key="")
        anos: dict[str, dict[str, date]] = defaultdict(dict)

        for posicao, celula in enumerate(celulas, start=1):
            bruto = _valor(celula.value)
            if bruto is None:
                continue
            if posicao in matriz:
                ano, lado = matriz[posicao]
                convertido = _as_date(bruto)
                if convertido is None:
                    row.notes.append(f"{ano} {lado}: {bruto!r} não é uma data")
                else:
                    anos[ano][lado] = convertido
                continue
            column = colunas.get(posicao)
            if column is None or column.refused is not None:
                continue
            if column.target == CHAVE:
                if normalize(column.label) == chave_normalizada:
                    row.key = str(bruto).strip()
                continue
            valor, motivo = _converter(column, bruto)
            if motivo is not None:
                row.notes.append(motivo)
            else:
                row.values[column.target] = valor

        for ano in sorted(anos):
            periodo = anos[ano]
            if "inicio" in periodo and "fim" in periodo:
                row.periods.append((periodo["inicio"], periodo["fim"]))
            else:
                lado = "fim" if "inicio" in periodo else "início"
                row.notes.append(f"período de {ano} sem {lado}")

        leitura.rows.append(row)


def ler_planilha(caminho: Path) -> list[SheetRead]:
    """O arquivo do cliente inteiro, aba por aba — inclusive as que não entram.

    Nenhuma aba é ignorada em silêncio. A que não está no mapa é lida como
    desconhecida e vai para o relatório com as linhas contadas; é o que permite
    afirmar que as 17 abas foram vistas em vez de que 11 foram encontradas.
    """
    wb = load_workbook(caminho, data_only=True, read_only=False)
    leituras: list[SheetRead] = []

    vistas: set[str] = set()
    for titulo in wb.sheetnames:
        ws = wb[titulo]
        normalizado = normalize(titulo)
        sheet = _POR_NOME.get(normalizado)
        leitura = SheetRead(title=titulo, sheet=sheet, hidden=ws.sheet_state != "visible")

        if sheet is None:
            achado = _SUFIXO_DUPLICADA.match(normalizado)
            base = _POR_NOME.get(achado["base"]) if achado else None
            if base is not None and base.name in vistas:
                leitura.sheet, leitura.duplicate_of = base, base.name

        if leitura.sheet is not None and leitura.duplicate_of is None:
            vistas.add(leitura.sheet.name)

        if (
            leitura.sheet is None
            or leitura.duplicate_of is not None
            or (leitura.sheet.purpose is Purpose.OUT)
        ):
            # Nada aqui é convertido: dashboard, cópia esquecida ou aba que o
            # mapa não conhece. As linhas são contadas para o balanço fechar, e a
            # primeira é dada como cabeçalho — é o que ela é em todas as abas
            # deste arquivo, e contar o cabeçalho como pessoa infla o descarte.
            leitura.unread = sum(
                0 if _linha_vazia(celulas) else 1 for celulas in ws.iter_rows(min_row=2)
            )
        else:
            _ler_aba(ws, leitura.sheet, leitura)

        leituras.append(leitura)

    return leituras


# ---------------------------------------------------------------------------
# Os modelos baixados do sistema
# ---------------------------------------------------------------------------
#: A ordem de emissão, que é a ordem de upload: o vínculo primeiro, porque é ele
#: que grava o ID RH; o resto depois, quando a chave do cliente já existe dos
#: dois lados.
ORDEM = ("hr_link", "hr_employee", "hr_exam", "hr_compensation")

_FALLBACK = "@fallback:"


@dataclass(slots=True)
class Model:
    """Um template baixado do sistema, aberto e indexado pela matrícula."""

    type: str
    template: Template
    path: Path
    workbook: Any
    sheet: Worksheet
    #: nome da coluna do template -> posição na planilha.
    positions: dict[str, int]
    #: matrícula -> número da linha.
    rows: dict[str, int]
    #: matrícula -> nome, como o sistema imprimiu.
    roster: dict[str, str]
    written: set[str] = field(default_factory=set)


class ConverterError(RuntimeError):
    """O conversor não tem como rodar. Não é linha recusada — é a corrida inteira."""


def carregar_modelos(diretorio: Path) -> dict[str, Model]:
    """Os modelos que o implantador baixou, identificados pela própria `_meta`.

    O nome do arquivo não decide nada: quem diz o que o arquivo é são os
    metadados que o sistema escreveu nele. Um modelo renomeado continua sendo o
    que é, e um arquivo qualquer com nome de modelo é recusado.
    """
    from operax.rh.workbook import read_meta

    modelos: dict[str, Model] = {}
    for caminho in sorted(diretorio.glob("*.xlsx")):
        if caminho.name.startswith("~$"):
            continue
        wb = load_workbook(caminho)
        meta = read_meta(wb)
        tipo = meta.get("type", "")
        template = TEMPLATES.get(tipo)
        if template is None:
            raise ConverterError(f"{caminho.name}: tipo {tipo!r} não tem template neste sistema")
        if tipo in modelos:
            raise ConverterError(
                f"dois modelos do tipo {tipo!r}: {modelos[tipo].path.name} e {caminho.name}"
            )

        ws = wb[meta["sheet"]]
        colunas = meta["columns"].split(",")
        positions = {nome: posicao for posicao, nome in enumerate(colunas, start=1)}
        if "registration_number" not in positions:
            raise ConverterError(f"{caminho.name}: o modelo não imprime a matrícula")

        rows: dict[str, int] = {}
        roster: dict[str, str] = {}
        coluna_matricula = positions["registration_number"]
        coluna_nome = positions.get("name")
        for numero, celulas in enumerate(ws.iter_rows(min_row=2), start=2):
            bruto = _valor(celulas[coluna_matricula - 1].value)
            if bruto is None:
                continue
            matricula = str(bruto).strip()
            rows[matricula] = numero
            if coluna_nome is not None:
                roster[matricula] = str(_valor(celulas[coluna_nome - 1].value) or "")

        modelos[tipo] = Model(
            type=tipo,
            template=template,
            path=caminho,
            workbook=wb,
            sheet=ws,
            positions=positions,
            rows=rows,
            roster=roster,
        )

    if not modelos:
        raise ConverterError(
            f"nenhum modelo .xlsx em {diretorio} — baixe os modelos pela tela de Importação "
            f"antes de rodar o conversor"
        )
    return modelos


def _editaveis(model: Model) -> frozenset[str]:
    """As colunas que o conversor pode escrever neste modelo.

    Chave e coluna do sync ficam de fora pelo mesmo motivo que ficam travadas na
    tela: quem manda nelas não é a planilha do cliente.
    """
    return frozenset(c.column for c in model.template.editable())


# ---------------------------------------------------------------------------
# Conversão
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Discard:
    """Um motivo de descarte e as linhas que caíram nele."""

    sheet: str
    reason: str
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def registrar(self, descricao: str | None) -> None:
        self.count += 1
        if descricao and len(self.examples) < 5:
            self.examples.append(descricao)


@dataclass(slots=True)
class Resultado:
    """O balanço da corrida — e a razão de o script existir."""

    lidas: int = 0
    destino: int = 0
    parqueadas: int = 0
    conferidas: int = 0
    descartadas: int = 0
    emitidos: list[tuple[str, Path, int]] = field(default_factory=list)
    parqueados: list[tuple[str, Path, int]] = field(default_factory=list)
    divergencias: list[str] = field(default_factory=list)
    descartes: list[Discard] = field(default_factory=list)
    #: Célula que não deu para aproveitar, agrupada por coluna. Não derruba a
    #: linha — mas some do sistema, e sumir em silêncio é o que este script
    #: existe para não deixar acontecer.
    notas: list[Discard] = field(default_factory=list)
    leituras: list[SheetRead] = field(default_factory=list)
    admissao_como_vigencia: int = 0
    #: aba -> quantas linhas eram histórico e foram parqueadas no lugar do
    #: template, porque o modelo carrega um registro por pessoa.
    historico: dict[str, int] = field(default_factory=dict)
    relatorio: Path | None = None

    def fecha(self) -> bool:
        """Toda linha lida terminou em algum lugar."""
        return self.lidas == self.destino + self.parqueadas + self.conferidas + self.descartadas


def _ordem_parqueada() -> dict[str, list[str]]:
    """A ordem das colunas de cada .csv, tirada da ordem declarada no mapa."""
    ordem: dict[str, list[str]] = defaultdict(list)
    for sheet in SHEETS:
        for column in sheet.columns:
            alvo = column.target
            if not alvo or alvo == CHAVE or alvo.startswith("@"):
                continue
            destino, coluna = alvo.split(".", 1)
            if destino in TEMPLATES or destino == "conferencia":
                continue
            if coluna not in ordem[destino]:
                ordem[destino].append(coluna)
    ordem["leave_period"] = ["category", "start_date", "end_date"]
    return dict(ordem)


ORDEM_PARQUEADA = _ordem_parqueada()


def converter(
    *, planilha: Path, modelos: Path, saida: Path, agora: datetime | None = None
) -> Resultado:
    """A planilha do cliente vira modelo preenchido, .csv parqueado e relatório.

    Nenhuma escrita no banco, em nenhum ramo. O que sai daqui ainda passa por
    preview e confirmação humana na tela de Importação, como qualquer upload.
    """
    leituras = ler_planilha(planilha)
    carregados = carregar_modelos(modelos)
    resultado = Resultado(leituras=leituras)

    roster: dict[str, str] = {}
    for model in carregados.values():
        roster.update(model.roster)

    parqueados: dict[str, list[dict[str, Any]]] = defaultdict(list)
    descartes: dict[tuple[str, str], Discard] = {}

    def descartar(aba: str, motivo: str, descricao: str | None = None, quantas: int = 1) -> None:
        alvo = descartes.get((aba, motivo))
        if alvo is None:
            alvo = descartes[(aba, motivo)] = Discard(sheet=aba, reason=motivo)
            resultado.descartes.append(alvo)
        for _ in range(quantas):
            alvo.registrar(descricao)
        resultado.descartadas += quantas

    notas: dict[tuple[str, str], Discard] = {}

    def anotar(aba: str, row: SourceRow) -> None:
        for texto in row.notes:
            campo = texto.split(":", 1)[0]
            alvo = notas.get((aba, campo))
            if alvo is None:
                alvo = notas[(aba, campo)] = Discard(sheet=aba, reason=campo)
                resultado.notas.append(alvo)
            alvo.registrar(f"linha {row.line} — {texto}")

    for leitura in leituras:
        resultado.lidas += len(leitura.rows) + leitura.unread
        if leitura.unread:
            descartar(leitura.title, _motivo_da_aba(leitura), quantas=leitura.unread)
        if leitura.sheet is None:
            continue
        sheet = leitura.sheet
        if sheet.latest_only:
            reduzidas = _reduzir_ao_mais_recente(leitura.rows, sheet.latest_only)
            if reduzidas:
                resultado.historico[leitura.title] = reduzidas

        for row in leitura.rows:
            anotar(leitura.title, row)
            if not row.key:
                descartar(
                    leitura.title,
                    "linha sem matrícula: não dá para saber de quem é",
                    f"linha {row.line}",
                )
                continue
            # A conferência é julgada antes do quadro ativo, e não depois: numa
            # aba de DESLIGADOS, **não** estar no quadro é o desfecho certo. Ler
            # a ausência como descarte transformaria a conferência que fecha na
            # única que parece problema.
            if sheet.purpose is Purpose.CONFERENCE:
                resultado.conferidas += 1
                if row.key in roster:
                    resultado.divergencias.append(_divergencia(row, roster[row.key]))
                continue

            if row.key not in roster:
                descartar(
                    leitura.title,
                    "matrícula fora do quadro ativo do sistema — rode o sync do Secullum "
                    "primeiro; quem está desligado não vem no modelo",
                    f"linha {row.line} (matrícula {row.key})",
                )
                continue

            escreveu, parqueou, faltando = _distribuir(
                row, sheet, carregados, parqueados, resultado
            )
            if escreveu:
                resultado.destino += 1
            elif parqueou:
                resultado.parqueadas += 1
            elif faltando:
                descartar(
                    leitura.title,
                    f"o modelo de {', '.join(sorted(faltando))} não estava no diretório: "
                    "baixe-o pela tela de Importação e rode de novo",
                    f"linha {row.line} (matrícula {row.key})",
                )
            else:
                descartar(
                    leitura.title,
                    "nenhuma coluna com destino preenchida nesta linha",
                    f"linha {row.line} (matrícula {row.key})",
                )

    saida.mkdir(parents=True, exist_ok=True)
    _emitir_modelos(carregados, saida, resultado)
    _emitir_parqueados(parqueados, saida, resultado)
    resultado.relatorio = _emitir_relatorio(planilha, saida, resultado, agora)
    return resultado


def _divergencia(row: SourceRow, nome: str) -> str:
    """O que a conferência do DESLIGADOS tem a dizer sobre uma pessoa."""
    demissao = row.values.get("conferencia.terminated_on")
    quando = f"em {demissao:%d/%m/%Y}" if isinstance(demissao, date) else "sem data"
    return (
        f"matrícula {row.key} ({nome}): a planilha marca desligamento {quando} e o ponto ainda "
        "traz a pessoa no quadro ativo"
    )


def _distribuir(
    row: SourceRow,
    sheet: SourceSheet,
    carregados: dict[str, Model],
    parqueados: dict[str, list[dict[str, Any]]],
    resultado: Resultado,
) -> tuple[bool, bool, set[str]]:
    """Cada valor da linha na célula do modelo ou no registro parqueado.

    O registro parqueado é montado por **linha de origem**, e não por matrícula:
    a mesma pessoa tem três atestados e quatro parcelas, e juntar por matrícula
    faria os três virarem um.
    """
    valores = dict(row.values)
    for alvo, valor in list(valores.items()):
        if not alvo.startswith(_FALLBACK):
            continue
        del valores[alvo]
        real = alvo[len(_FALLBACK) :]
        if real not in valores:
            valores[real] = valor
            resultado.admissao_como_vigencia += 1

    faltando: set[str] = set()
    registros: dict[str, dict[str, Any]] = {}
    por_modelo: dict[str, dict[str, Any]] = {}

    for alvo, valor in valores.items():
        destino, coluna = alvo.split(".", 1)
        if destino == "conferencia":
            continue
        if destino in carregados:
            por_modelo.setdefault(destino, {})[coluna] = valor
        elif destino in TEMPLATES:
            faltando.add(destino)
        else:
            registros.setdefault(destino, {"matricula": row.key})[coluna] = valor

    escreveu = _preencher_modelos(row, por_modelo, carregados)

    for destino, registro in registros.items():
        parqueados[destino].append(registro)

    for inicio, fim in row.periods:
        parqueados["leave_period"].append(
            {
                "matricula": row.key,
                "category": sheet.matrix.category if sheet.matrix else "vacation",
                "start_date": inicio,
                "end_date": fim,
            }
        )

    return escreveu, bool(registros or row.periods), faltando


def _preencher_modelos(
    row: SourceRow, por_modelo: dict[str, dict[str, Any]], carregados: dict[str, Model]
) -> bool:
    """As células do modelo, na linha da pessoa — e as que ficam em branco.

    A célula em branco é a parte que importa. Num template de vigência ou de
    exame a linha vai **inteira**, e deixar o pré-preenchimento onde a planilha
    não disse nada produz um registro que nunca existiu: o exame de fevereiro com
    a validade do de setembro. O que a origem não trouxe é apagado, e a linha ou
    fica coerente ou é recusada no preview por campo obrigatório vazio — que é a
    pergunta certa para o RH.
    """
    escreveu = False
    for destino, colunas in por_modelo.items():
        model = carregados[destino]
        linha_modelo = model.rows.get(row.key)
        editaveis = _editaveis(model)
        valores = {coluna: v for coluna, v in colunas.items() if coluna in editaveis}
        if linha_modelo is None or not valores:
            continue
        if model.template.writes_whole_row:
            valores = {coluna: valores.get(coluna) for coluna in editaveis}
        for coluna, valor in valores.items():
            # Atribuição, e não `cell(..., value=...)`: com `value=None` o
            # openpyxl devolve a célula sem mexer nela, e o pré-preenchimento
            # ficaria exatamente onde não pode ficar.
            model.sheet.cell(row=linha_modelo, column=model.positions[coluna]).value = valor
        model.written.add(row.key)
        escreveu = True
    return escreveu


def _reduzir_ao_mais_recente(rows: list[SourceRow], regra: LatestOnly) -> int:
    """Uma linha por pessoa vai para o template; as outras são reescritas.

    Reescritas, não descartadas: os destinos `<template>.<coluna>` viram
    `<tabela>.<coluna>`, e a linha cai no .csv parqueado pelo mesmo caminho de
    qualquer outro histórico. A conversão já está feita e não se joga fora.
    """
    prefixo = regra.by.split(".", 1)[0] + "."
    vence: dict[str, tuple[Any, int]] = {}
    for row in rows:
        valor = row.values.get(regra.by)
        if not row.key or valor is None:
            continue
        atual = vence.get(row.key)
        if atual is None or valor > atual[0]:
            vence[row.key] = (valor, row.line)

    linhas_vencedoras = {linha for _, linha in vence.values()}
    reduzidas = 0
    for row in rows:
        if row.line in linhas_vencedoras:
            continue
        reescritas = {
            (regra.park_as + "." + alvo.split(".", 1)[1] if alvo.startswith(prefixo) else alvo): v
            for alvo, v in row.values.items()
        }
        if reescritas != row.values:
            reduzidas += 1
        row.values = reescritas
    return reduzidas


def _motivo_da_aba(leitura: SheetRead) -> str:
    if leitura.duplicate_of:
        return f"aba duplicada de {leitura.duplicate_of} — vale a primeira"
    if leitura.sheet is None:
        return "aba fora do mapa de implantação: não estava nas 17 previstas"
    if leitura.sheet.purpose is Purpose.OUT:
        return leitura.sheet.reason
    return (
        f"cabeçalho não localizado nas {_LINHAS_DE_TOPO} primeiras linhas: sem cabeçalho não há "
        "como saber o que é cada coluna, e adivinhar pela posição grava o dado de um na linha "
        "de outro"
    )


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------
def _emitir_modelos(carregados: dict[str, Model], saida: Path, resultado: Resultado) -> None:
    """Os modelos preenchidos, numerados na ordem em que devem subir.

    O número no nome não é enfeite: `hr_link` grava o ID RH, e é ele que faz a
    planilha do cliente e o cadastro passarem a falar da mesma pessoa pela chave
    do cliente. Subir na ordem errada não corrompe nada — só desperdiça uma
    rodada de preview.
    """
    for posicao, tipo in enumerate(ORDEM, start=1):
        model = carregados.get(tipo)
        if model is None:
            continue
        caminho = saida / f"{posicao:02d}-{tipo}.xlsx"
        model.workbook.save(caminho)
        resultado.emitidos.append((tipo, caminho, len(model.written)))


def _celula_csv(valor: Any) -> str:
    if isinstance(valor, date):
        return valor.isoformat()
    return "" if valor is None else str(valor)


def _emitir_parqueados(
    parqueados: dict[str, list[dict[str, Any]]], saida: Path, resultado: Resultado
) -> None:
    """O que foi convertido e não tem onde entrar ainda.

    Sai em .csv, e não em .xlsx, de propósito: um .xlsx aqui pareceria um
    template e alguém tentaria subi-lo. Este arquivo é produto de trabalho — a
    conversão já feita, esperando a tabela de destino ganhar caminho de escrita.
    Datas em ISO e decimal com ponto, porque quem vai lê-lo é código.
    """
    if not parqueados:
        return
    pasta = saida / "parqueado"
    pasta.mkdir(parents=True, exist_ok=True)

    for destino in sorted(parqueados):
        registros = parqueados[destino]
        colunas = ["matricula", *ORDEM_PARQUEADA.get(destino, [])]
        for registro in registros:
            for coluna in registro:
                if coluna not in colunas:
                    colunas.append(coluna)
        caminho = pasta / f"{destino}.csv"
        with caminho.open("w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=colunas)
            escritor.writeheader()
            for registro in registros:
                escritor.writerow({c: _celula_csv(registro.get(c)) for c in colunas})
        resultado.parqueados.append((destino, caminho, len(registros)))


def _tabela(linhas: list[tuple[str, ...]], cabecalho: tuple[str, ...]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "---|" * len(cabecalho)]
    saida += ["| " + " | ".join(celulas) + " |" for celulas in linhas]
    return saida


def _destino_da_aba(leitura: SheetRead) -> str:
    if leitura.duplicate_of:
        return f"duplicada de {leitura.duplicate_of}"
    if leitura.sheet is None:
        return "fora do mapa"
    return {
        Purpose.TEMPLATE: "template",
        Purpose.CONFERENCE: "conferência",
        Purpose.PARKED: "parqueado",
        Purpose.OUT: "não importa",
    }[leitura.sheet.purpose]


def _emitir_relatorio(
    planilha: Path, saida: Path, resultado: Resultado, agora: datetime | None = None
) -> Path:
    """O relatório de descarte, para anexar à ata da implantação.

    Ele responde à única pergunta que o cliente vai fazer depois da carga — "e o
    resto?" — sem que ninguém precise abrir a planilha de novo.
    """
    quando = agora or datetime.now()
    linhas: list[str] = [
        "# Carga inicial de RH — relatório de descarte",
        "",
        f"**Planilha:** `{planilha.name}`  ",
        f"**Gerado em:** {quando:%d/%m/%Y %H:%M}  ",
        "**Escreveu no banco:** não. O conversor não abre conexão — a entrada continua sendo "
        "template, preview e confirmação humana.",
        "",
        "## 1. Balanço",
        "",
    ]
    linhas += _tabela(
        [
            ("linhas lidas", str(resultado.lidas), "todas as abas, inclusive as que não entram"),
            ("com destino", str(resultado.destino), "foram para uma célula de template emitido"),
            (
                "parqueadas",
                str(resultado.parqueadas),
                "convertidas para o formato de destino, à espera de caminho de escrita",
            ),
            ("conferência", str(resultado.conferidas), "comparadas contra o ponto, não importadas"),
            ("descartadas", str(resultado.descartadas), "com motivo, na seção 6"),
        ],
        ("", "linhas", "o que é"),
    )
    fechou = "**sim**" if resultado.fecha() else "**NÃO — há linha sem destino**"
    linhas += ["", f"Fecha em 100%: {fechou}.", ""]

    linhas += ["## 2. Modelos emitidos", ""]
    if resultado.emitidos:
        linhas += _tabela(
            [
                (f"`{caminho.name}`", tipo, str(preenchidas))
                for tipo, caminho, preenchidas in resultado.emitidos
            ],
            ("arquivo", "tipo", "pessoas preenchidas"),
        )
        linhas += [
            "",
            "Subir pela tela de Importação **na ordem do nome do arquivo**, conferindo o preview "
            "de cada um antes de confirmar.",
            "",
        ]
    else:
        linhas += ["Nenhum — nenhum modelo do sistema estava no diretório informado.", ""]

    linhas += ["## 3. Abas da planilha", ""]
    linhas += _tabela(
        [
            (
                f"`{leitura.title}`" + (" (oculta)" if leitura.hidden else ""),
                _destino_da_aba(leitura),
                str(leitura.header_row or "—"),
                str(len(leitura.rows) + leitura.unread),
            )
            for leitura in resultado.leituras
        ],
        ("aba", "destino", "cabeçalho na linha", "linhas"),
    )
    linhas += [""]

    recusadas = [
        (f"`{leitura.title}`", coluna, motivo)
        for leitura in resultado.leituras
        for coluna, motivo in leitura.refused_found
    ]
    linhas += ["## 4. Colunas recusadas por regra", ""]
    if recusadas:
        linhas += [
            "Estavam no arquivo e não entraram. É esta lista, e não a ausência da coluna no "
            "sistema, que prova que o dado foi visto e recusado.",
            "",
        ]
        linhas += _tabela(recusadas, ("aba", "coluna", "por quê"))
    else:
        linhas += ["Nenhuma coluna recusada por regra foi encontrada no arquivo."]
    linhas += [""]

    sem_destino = [
        (f"`{leitura.title}`", ", ".join(sorted(set(leitura.unmapped))))
        for leitura in resultado.leituras
        if leitura.unmapped
    ]
    linhas += ["## 5. Colunas sem destino no v1", ""]
    if sem_destino:
        linhas += [
            "O mapa não as conhece e o banco não tem onde guardá-las. Ficam na planilha "
            "original, que continua existindo como arquivo morto até o cliente aposentá-la.",
            "",
        ]
        linhas += _tabela(sem_destino, ("aba", "colunas"))
    else:
        linhas += ["Nenhuma."]
    linhas += [""]

    linhas += ["## 6. Descartes", ""]
    if resultado.descartes:
        linhas += _tabela(
            [
                (
                    f"`{descarte.sheet}`",
                    str(descarte.count),
                    descarte.reason,
                    "; ".join(descarte.examples) or "—",
                )
                for descarte in sorted(
                    resultado.descartes, key=lambda d: (-d.count, d.sheet, d.reason)
                )
            ],
            ("aba", "linhas", "motivo", "exemplos"),
        )
    else:
        linhas += ["Nenhuma linha descartada."]
    linhas += [""]

    linhas += ["## 7. Conferência do DESLIGADOS", ""]
    if resultado.conferidas == 0:
        linhas += ["A aba não veio no arquivo ou não tinha linha legível.", ""]
    elif resultado.divergencias:
        linhas += [
            f"{resultado.conferidas} linha(s) conferida(s), "
            f"**{len(resultado.divergencias)} divergência(s)**. O desligamento é fato do ponto: "
            "quem aparece aqui está desligado na planilha e ativo no Secullum, e é no Secullum "
            "que a correção acontece.",
            "",
        ]
        linhas += [f"- {d}" for d in resultado.divergencias]
        linhas += [""]
    else:
        linhas += [
            f"{resultado.conferidas} linha(s) conferida(s), nenhuma divergência: todo mundo que "
            "a planilha dá como desligado já está fora do quadro ativo do sistema.",
            "",
        ]

    linhas += ["## 8. Parqueado — convertido, sem onde entrar ainda", ""]
    if resultado.parqueados:
        linhas += _tabela(
            [
                (f"`parqueado/{caminho.name}`", destino, str(quantos), _porque_parqueado(destino))
                for destino, caminho, quantos in resultado.parqueados
            ],
            ("arquivo", "tabela de destino", "registros", "o que falta"),
        )
        linhas += [
            "",
            "São .csv de propósito: não são template e não sobem por nenhuma tela. A conversão "
            "já está feita — é o caminho de escrita que não existe. Coluna de uuid (`unit_id`, "
            "`type_id`) sai com o nome, porque o conversor não consulta o banco.",
            "",
        ]
    else:
        linhas += ["Nada parqueado.", ""]

    linhas += ["## 9. Células que não puderam ser lidas", ""]
    if resultado.notas:
        linhas += [
            "A linha entrou; a célula não. Valor fora do catálogo, data ilegível, período pela "
            "metade — cada uma dessas é uma pergunta para o RH antes de o preview rodar.",
            "",
        ]
        linhas += _tabela(
            [
                (f"`{nota.sheet}`", nota.reason, str(nota.count), "; ".join(nota.examples))
                for nota in sorted(resultado.notas, key=lambda n: (-n.count, n.sheet, n.reason))
            ],
            ("aba", "coluna", "células", "exemplos"),
        )
    else:
        linhas += ["Nenhuma."]
    linhas += [""]

    linhas += ["## 10. Observações da leitura", ""]
    observacoes: list[str] = []
    if resultado.admissao_como_vigencia:
        observacoes.append(
            f"{resultado.admissao_como_vigencia} pessoa(s) sem data de último reajuste: a faixa "
            "salarial vigente entrou com a **data de admissão**, que é a única que se pode "
            "afirmar sem inventar."
        )
    quebradas = sum(leitura.broken_cells for leitura in resultado.leituras)
    if quebradas:
        observacoes.append(
            f"{quebradas} célula(s) com fórmula quebrada (`#REF!` e vizinhos) lidas como vazias — "
            "o texto do erro nunca vira conteúdo."
        )
    for aba, quantas in sorted(resultado.historico.items()):
        observacoes.append(
            f"`{aba}`: {quantas} linha(s) são histórico — a pessoa tem registro mais recente na "
            "mesma aba. O modelo carrega um por pessoa; as demais foram convertidas e estão em "
            "`parqueado/`."
        )
    ocultas = [leitura.title for leitura in resultado.leituras if leitura.hidden]
    if ocultas:
        observacoes.append(
            f"Aba(s) oculta(s) lida(s) como qualquer outra: {', '.join(f'`{o}`' for o in ocultas)}."
        )
    duplicadas = [
        f"`{leitura.title}` (de {leitura.duplicate_of})"
        for leitura in resultado.leituras
        if leitura.duplicate_of
    ]
    if duplicadas:
        observacoes.append(
            f"Aba(s) duplicada(s) descartada(s) inteira(s): {', '.join(duplicadas)}."
        )
    linhas += [f"- {o}" for o in observacoes] if observacoes else ["Nada a registrar."]
    linhas += [""]

    caminho = saida / "RELATORIO-DE-DESCARTE.md"
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho


#: Destinos parqueados cujo motivo não é o de uma aba inteira. `employee_position`
#: é o único: ele nasce de uma coluna da aba de cadastro, que vira template.
_MOTIVO_EXTRA = {
    "occupational_exam": (
        "histórico: o template `hr_exam` carrega o exame vigente de cada pessoa, e estes são os "
        "anteriores — convertidos, à espera de quem os carregue"
    ),
    "employee_position": (
        "`app.file_import.type` não tem valor para posição; a vigência de cargo se cria uma a "
        "uma pela tela do colaborador"
    ),
}


def _porque_parqueado(destino: str) -> str:
    """O motivo declarado no mapa, na aba que alimenta este destino."""
    if destino in _MOTIVO_EXTRA:
        return _MOTIVO_EXTRA[destino]
    for sheet in SHEETS:
        alvos = {c.target.split(".", 1)[0] for c in sheet.columns if c.target and "." in c.target}
        if sheet.matrix and sheet.matrix.target == destino:
            alvos.add(destino)
        if destino in alvos and sheet.reason:
            return sheet.reason
    return "sem tipo de importação declarado"


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------
if set(ORDEM) != set(TEMPLATES):
    # A ordem é a de upload e precisa cobrir todo template que existe: um
    # template fora dela seria preenchido e nunca gravado em disco.
    raise RuntimeError(f"ORDEM não cobre TEMPLATES: {sorted(set(TEMPLATES) - set(ORDEM))}")

# Importado só para o `make db-test` conferir que a aba de controle continua
# chamando o que o conversor espera.
_ = META_SHEET


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rh_carga_inicial",
        description=(
            "Converte a planilha de RH do cliente nos templates do OperaX, preenchidos, mais o "
            "relatório do que não entrou. Não escreve no banco."
        ),
    )
    parser.add_argument("--planilha", required=True, type=Path, help="a planilha do cliente")
    parser.add_argument(
        "--modelos",
        required=True,
        type=Path,
        help="diretório com os modelos baixados da tela de Importação",
    )
    parser.add_argument("--saida", required=True, type=Path, help="onde gravar o resultado")
    args = parser.parse_args(argv)

    if not args.planilha.is_file():
        print(f"erro: planilha não encontrada: {args.planilha}", file=sys.stderr)
        return 2
    if not args.modelos.is_dir():
        print(f"erro: diretório de modelos não encontrado: {args.modelos}", file=sys.stderr)
        return 2

    try:
        resultado = converter(planilha=args.planilha, modelos=args.modelos, saida=args.saida)
    except ConverterError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2

    print(f"lidas       {resultado.lidas}")
    print(f"destino     {resultado.destino}")
    print(f"parqueadas  {resultado.parqueadas}")
    print(f"conferência {resultado.conferidas}")
    print(f"descartadas {resultado.descartadas}")
    for tipo, caminho, preenchidas in resultado.emitidos:
        print(f"  {caminho.name}  {tipo}  {preenchidas} pessoa(s)")
    print(f"relatório   {resultado.relatorio}")

    if not resultado.fecha():
        print(
            "ERRO: o balanço não fecha — há linha lida que não terminou em lugar nenhum.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
