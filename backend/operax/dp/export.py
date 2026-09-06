"""Os três arquivos do ciclo: Excel, PDF e remessa bancária.

⛔ A CONTA BANCÁRIA SÓ EXISTE DENTRO DE `bytes`
Regra 10 do `PRD-DP.md`. `build_remittance` é a única função do produto que
recebe o número completo, e ela devolve `bytes`. Ela o lê pelo `operax/dp/banking.py`,
que é o único módulo com o `select` da conta, e o que sai daqui não passa por
nenhum schema Pydantic — não há resposta JSON possível com `account` dentro.
As duas outras exportações não recebem conta nenhuma: elas não têm o dado para
vazar, e a ausência é o desenho.

⛔ E A REMESSA SÓ INCLUI QUEM TEM CONTA
Quem não tem fica de fora do arquivo e volta na lista de pendências, com nome e
sem conta. A alternativa — uma linha com conta em branco — é uma remessa que o
banco recusa inteira, ou pior, aceita com destino nulo.

⏳ O LAYOUT DA REMESSA É PENDÊNCIA, E ELE ESTÁ DECLARADO AQUI
`ANEXO-COBERTURA-LEGADO-FASTPARK.md` §4.3 registra o botão "Exportar arquivo
banco" e **não** registra o layout; a `SPEC-DP.md` também não. CNAB 240 e 400
têm campos que este produto não conhece (convênio, carteira, código de serviço)
e inventá-los produziria um arquivo que o banco recusa — com a aparência de
pronto. Então o que sai é um arquivo delimitado, documentado, com os campos que
a tela do legado mostra. **Trocar por CNAB é trocar `_REMITTANCE_HEADER` e
`_remittance_row`, e nada mais.**

⚠️ O EXCEL E O PDF SÃO A MESMA TABELA
Uma função monta as linhas (`_rows`), duas as escrevem. Duas montagens
divergiriam na primeira coluna nova, e o gestor confere o PDF contra o Excel.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from operax.dp.banking import mask_account
from operax.dp.ciclo import TRANSPORT_VOUCHER, Cycle, EntitlementLine

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_CONTENT_TYPE = "application/pdf"
REMITTANCE_CONTENT_TYPE = "text/plain; charset=utf-8"

#: Laranja de marca como preenchimento, texto escuro por cima — nunca o inverso.
_FILL_HEADER = PatternFill("solid", fgColor="FF8C00")
_FONT_HEADER = Font(bold=True, color="262626")
_MIN_WIDTH = 10
_MAX_WIDTH = 42

_KIND_LABEL = {
    "food_basket": "Cesta básica",
    "transport_voucher": "Vale transporte",
}

#: As colunas da tela de VT do legado, na ordem dela. A cesta usa as cinco
#: primeiras: ela não tem dias nem valor, e uma coluna vazia numa planilha que o
#: fornecedor lê é um campo que alguém preenche à mão.
_COLUNAS_BASE = ("Unidade", "Registro", "Colaborador", "Com direito", "Motivo")
_COLUNAS_VT = (
    "Dias base",
    "Faltas período anterior",
    "Dias líquidos",
    "VT unitário",
    "Ida e volta",
    "Total",
)

#: ⛔ Ponto e vírgula, e não vírgula: nome de colaborador tem vírgula e conta
#: bancária tem hífen. O separador que não aparece no dado é o único que não
#: precisa de aspas — e aspas num arquivo de remessa é o que quebra o parser do
#: banco.
_SEP = ";"
_REMITTANCE_HEADER = (
    "registro",
    "colaborador",
    "banco",
    "agencia",
    "conta",
    "tipo_conta",
    "valor",
)


def kind_label(kind: str) -> str:
    return _KIND_LABEL.get(kind, kind)


def _dinheiro(valor: Decimal | None) -> str:
    """`1.234,56` — a forma que o gestor confere contra o legado."""
    if valor is None:
        return ""
    inteiro, _, centavos = f"{valor:.2f}".partition(".")
    negativo, inteiro = (inteiro[0] == "-", inteiro.lstrip("-"))
    milhar = f"{int(inteiro):,}".replace(",", ".")
    return f"{'-' if negativo else ''}{milhar},{centavos}"


def _rows(cycle: Cycle) -> tuple[tuple[str, ...], list[tuple[Any, ...]]]:
    """O cabeçalho e as linhas, montados uma vez para os dois formatos."""
    vt = cycle.kind == TRANSPORT_VOUCHER
    header = _COLUNAS_BASE + (_COLUNAS_VT if vt else ())
    linhas: list[tuple[Any, ...]] = []
    for linha in cycle.lines:
        base: tuple[Any, ...] = (
            linha.unit_name or "—",
            linha.registration_number or "—",
            linha.name,
            "Sim" if linha.entitled else "Não",
            linha.reason or "",
        )
        if vt:
            base += (
                linha.days_base,
                linha.absences_prior,
                linha.net_days,
                _dinheiro(linha.unit_amount),
                _dinheiro(linha.round_trip_amount),
                _dinheiro(linha.total_amount),
            )
        linhas.append(base)
    return header, linhas


def _titulo(cycle: Cycle) -> str:
    return (
        f"{kind_label(cycle.kind)} — {cycle.period_month:02d}/{cycle.period_year} "
        f"({cycle.window_start:%d/%m/%Y} a {cycle.window_end:%d/%m/%Y})"
    )


def _resumo(cycle: Cycle) -> list[str]:
    linhas = [
        f"Com direito: {cycle.entitled_count}",
        f"Perdeu direito: {cycle.denied_count}",
    ]
    if cycle.business_days is not None:
        linhas.append(f"Dias com expediente na janela: {cycle.business_days}")
    if cycle.kind == TRANSPORT_VOUCHER:
        linhas.append(f"Total previsto: R$ {_dinheiro(cycle.total_amount)}")
    return linhas


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def build_xlsx(cycle: Cycle) -> bytes:
    """A planilha do ciclo. Sem conta bancária — ela não é insumo desta tela."""
    header, linhas = _rows(cycle)
    wb = Workbook()
    ws = wb.active
    ws.title = kind_label(cycle.kind)[:31]

    ws.append([_titulo(cycle)])
    ws["A1"].font = Font(bold=True, size=13)
    for texto in _resumo(cycle):
        ws.append([texto])
    ws.append([])

    linha_do_cabecalho = ws.max_row + 1
    ws.append(list(header))
    for coluna in range(1, len(header) + 1):
        celula = ws.cell(row=linha_do_cabecalho, column=coluna)
        celula.fill = _FILL_HEADER
        celula.font = _FONT_HEADER
        celula.alignment = Alignment(vertical="center", wrap_text=True)

    for valores in linhas:
        ws.append(list(valores))

    # Congelar abaixo do cabeçalho: a lista tem 176 linhas e o fornecedor rola.
    ws.freeze_panes = ws.cell(row=linha_do_cabecalho + 1, column=1)
    for indice, rotulo in enumerate(header, start=1):
        largura = max(len(rotulo), *(len(str(v[indice - 1] or "")) for v in linhas or [header]))
        ws.column_dimensions[get_column_letter(indice)].width = min(
            max(largura + 2, _MIN_WIDTH), _MAX_WIDTH
        )

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
# `helvetica` é fonte base do PDF: nenhum arquivo de fonte para embutir e nenhuma
# dependência de sistema.
#
# ⚠️ `cp1252` E NÃO O `latin-1` PADRÃO DO fpdf2, E A DIFERENÇA É MEDIDA
# O travessão de `Vale transporte — 09/2026` e o `•` da máscara existem em
# cp1252 e NÃO em latin-1: com o padrão, gerar o PDF levantava
# `FPDFUnicodeEncodingException`. Um caractere fora de cp1252 continua estourando
# em vez de virar `?` — PDF com nome corrompido é pior que PDF que não saiu,
# porque ninguém confere o que já está impresso.
_PDF_FONT = "helvetica"
_PDF_MARGIN = 10.0


#: O que a fonte base sabe desenhar. Fora disso, o `?` — visível no papel.
_PDF_ENCODING = "cp1252"


def _pdf_text(valor: Any) -> str:
    """O texto como a fonte base consegue desenhá-lo.

    ⛔ SUBSTITUIR É VISÍVEL; ESTOURAR É UM 500 NUMA ROTA DE EXPORT
    Medido: `João Gonçalves` e `Ana — Silva` passam (cp1252 cobre pt-BR e o
    travessão), e `Łukasz Nowak` levantava `FPDFUnicodeEncodingException` — um
    500 que trava o PDF do mês inteiro por causa de um nome estrangeiro no
    quadro. O `?` que entra no lugar **aparece no documento**: não é degradação
    silenciosa, é o leitor vendo que aquele caractere não coube.

    ⚠️ E a troca vale só aqui. O Excel e o arquivo de remessa carregam o nome
    exato — o PDF é o artefato de conferência visual, não o registro.
    """
    texto = "" if valor is None else str(valor)
    return texto.encode(_PDF_ENCODING, errors="replace").decode(_PDF_ENCODING)


class _CyclePdf(FPDF):
    def __init__(self, titulo: str) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        # Atributo, não parâmetro do construtor: nesta versão do fpdf2 ele não é
        # aceito em `__init__`, e o default é `latin-1`.
        self.core_fonts_encoding = _PDF_ENCODING
        self._titulo = titulo
        self.set_auto_page_break(auto=True, margin=_PDF_MARGIN)
        self.set_margin(_PDF_MARGIN)

    def header(self) -> None:
        self.set_font(_PDF_FONT, "B", 11)
        self.cell(0, 7, _pdf_text(self._titulo), new_x="LMARGIN", new_y="NEXT")


def build_pdf(cycle: Cycle) -> bytes:
    """O mesmo conteúdo do Excel, paginado. Sem conta bancária."""
    header, linhas = _rows(cycle)
    pdf = _CyclePdf(_titulo(cycle))
    pdf.add_page()

    pdf.set_font(_PDF_FONT, "", 9)
    for texto in _resumo(cycle):
        pdf.cell(0, 5, _pdf_text(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    util = pdf.w - 2 * _PDF_MARGIN
    pesos = [len(rotulo) + 6 for rotulo in header]
    larguras = [util * peso / sum(pesos) for peso in pesos]

    pdf.set_font(_PDF_FONT, "B", 8)
    for rotulo, largura in zip(header, larguras, strict=True):
        pdf.cell(largura, 6, _pdf_text(rotulo), border=1)
    pdf.ln()

    pdf.set_font(_PDF_FONT, "", 8)
    for valores in linhas:
        for valor, largura in zip(valores, larguras, strict=True):
            texto = _pdf_text(valor)
            # Truncar em vez de quebrar: uma célula que cresce desalinha a linha
            # inteira, e a tabela que o gestor confere deixa de ser conferível.
            while texto and pdf.get_string_width(texto) > largura - 2:
                texto = texto[:-1]
            pdf.cell(largura, 5, texto, border=1)
        pdf.ln()

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Remessa — o único lugar do produto em que o número inteiro sai
# ---------------------------------------------------------------------------
class RemittanceError(RuntimeError):
    """A remessa não faz sentido para este ciclo."""


class DraftRemittanceError(RemittanceError):
    """O ciclo ainda é rascunho, e rascunho não paga ninguém.

    ⛔ TODA A IMUTABILIDADE PROTEGIA O CICLO CONGELADO E A PORTA QUE PAGA NÃO
    EXIGIA QUE ELE ESTIVESSE CONGELADO. Medido: o mesmo ciclo em `draft` gerou
    dois arquivos de banco com valores diferentes — 161,50 e 1.881,00 —, porque
    reapurar um rascunho apaga e reinsere as linhas depois de a primeira remessa
    já ter saído. É exatamente o que `ciclo.freeze` promete no docstring dele que
    não acontece, e a promessa valia só para o caminho que não paga.

    Excel e PDF de rascunho continuam saindo: eles SÃO o preview, e conferir é o
    que o rascunho existe para permitir.
    """


def _remittance_row(linha: EntitlementLine, conta: dict[str, Any]) -> str:
    return _SEP.join(
        [
            linha.registration_number or "",
            linha.name,
            conta["bank_code"],
            conta["branch"],
            conta["account"],
            conta["account_type"],
            f"{linha.total_amount:.2f}" if linha.total_amount is not None else "0.00",
        ]
    )


#: Os dois estados em que a apuração está congelada — e só deles sai dinheiro.
#: `cancelled` fica de fora: um ciclo cancelado é o que foi aposentado por um
#: ciclo novo, e reemitir a remessa dele pagaria a versão errada.
_PAGAVEL = frozenset({"generated", "exported"})


def ensure_payable(cycle: Cycle) -> None:
    """As duas condições para um ciclo virar dinheiro. **Uma implementação só.**

    Chamada em dois lugares e escrita em um: `build_remittance` a chama para que
    nenhum caminho futuro escape dela, e a rota a chama ANTES de ler as contas —
    buscar número de conta de um ciclo que não pode pagar é leitura de dado
    sensível sem motivo. Duas chamadas da mesma função não são a regra escrita
    duas vezes; duas cópias do `if` seriam.
    """
    if cycle.kind != TRANSPORT_VOUCHER:
        raise RemittanceError(
            "remessa bancária existe para vale transporte; a cesta é pedido ao "
            "fornecedor, não pagamento em conta"
        )
    if cycle.status not in _PAGAVEL:
        raise DraftRemittanceError(
            f"este ciclo está em «{cycle.status}» e a remessa só sai de ciclo congelado; "
            "gere o ciclo antes de exportar para o banco — um rascunho é reapurado a cada "
            "conferência, e dois arquivos do mesmo mês pagariam valores diferentes"
        )


def build_remittance(cycle: Cycle, accounts: Sequence[dict[str, Any]]) -> tuple[bytes, list[str]]:
    """O arquivo do banco e a lista de quem ficou de fora por não ter conta.

    ⛔ O `dict` de `accounts` carrega `account` inteiro e vem do `select` de
    `operax/dp/banking.py`. Ele morre nesta função: o que volta é `bytes` e uma
    lista de NOMES. Não há caminho daqui para uma resposta JSON — e é por isso
    que a garantia é estrutural e não uma revisão lembrando de mascarar.
    """
    ensure_payable(cycle)

    por_pessoa = {conta["employee_id"]: conta for conta in accounts}
    linhas = [_SEP.join(_REMITTANCE_HEADER)]
    sem_conta: list[str] = []
    for linha in cycle.lines:
        if not linha.entitled:
            continue
        conta = por_pessoa.get(linha.employee_id)
        if conta is None:
            sem_conta.append(linha.name)
            continue
        linhas.append(_remittance_row(linha, conta))

    return ("\n".join(linhas) + "\n").encode("utf-8"), sem_conta


def remittance_trail(
    cycle: Cycle, accounts: Sequence[dict[str, Any]], sem_conta: Sequence[str]
) -> dict[str, Any]:
    """O que a trilha de auditoria guarda da remessa — nunca o número.

    `SPEC-DP.md` §5 pede `audit_log` em toda leitura que monte remessa: quem
    gerou, quando, para qual ciclo. A cauda mascarada entra porque é ela que
    permite conferir "a remessa foi para a conta certa?" sem reabrir o arquivo;
    o número inteiro na trilha seria a segunda cópia que `banking.py` existe
    para não permitir.
    """
    return {
        "cycle_id": str(cycle.id),
        "kind": cycle.kind,
        "period": f"{cycle.period_month:02d}/{cycle.period_year}",
        "lines": len(accounts),
        "without_account": list(sem_conta),
        "accounts": sorted(mask_account(conta["account"]) for conta in accounts),
        "generated_at": datetime.now(UTC).isoformat(),
    }
