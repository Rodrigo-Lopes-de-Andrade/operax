"""A planilha de 17 abas, sintética — a bagunça, sem o dado.

Regra 7 da etapa: dado real não entra em teste. O arquivo do cliente é lido pelo
conversor na implantação, em ambiente controlado, e nunca chega aqui. O que chega
é a **forma** dele, que é o que o conversor precisa aguentar:

  cabeçalho na linha 1, na 2, na 6 e na 8 — as abas ganharam título, filtro e
    legenda em cima do dado ao longo dos anos;
  aba oculta com dado vivo dentro;
  fórmula quebrada (`#REF!`) no lugar de um valor;
  aba duplicada, com o sufixo que o Excel dá;
  dashboards misturados com cadastro;
  uma aba que ninguém mapeou.

Nada aqui é pessoa: as matrículas são as do seed de desenvolvimento, os nomes são
inventados e os CPFs não existem. Cada linha foi desenhada em cima de um caso que
o conversor precisa decidir, e o nome da constante diz qual.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from openpyxl import Workbook

from operax.rh.templates import TEMPLATES
from operax.rh.workbook import build

TENANT = UUID("dede0000-0000-0000-0000-000000000001")

#: As matrículas do seed de desenvolvimento (`lpad(n, 5, '0')`), para o ensaio
#: contra o Supabase local usar o mesmo arquivo do teste.
PESSOAS: tuple[tuple[str, str], ...] = tuple(
    (f"{n:05d}", nome)
    for n, nome in enumerate(
        (
            "Ana Almeida",
            "Bruno Barbosa",
            "Carla Cardoso",
            "Diego Duarte",
            "Eliane Esteves",
            "Fábio Ferreira",
            "Gisele Gomes",
            "Heitor Henriques",
            "Ivone Ibrahim",
            "João Jardim",
            "Karina Klein",
            "Lucas Lopes",
        ),
        start=1,
    )
)

#: Está na planilha e não está no sistema: o sync não a conhece.
FORA_DO_QUADRO = "09999"

HOJE = date(2026, 8, 24)


def _preencher(ws, linha_cabecalho: int, cabecalho: list[str], linhas: list[list[Any]]) -> None:
    for coluna, rotulo in enumerate(cabecalho, start=1):
        ws.cell(row=linha_cabecalho, column=coluna, value=rotulo)
    for deslocamento, valores in enumerate(linhas, start=1):
        for coluna, valor in enumerate(valores, start=1):
            ws.cell(row=linha_cabecalho + deslocamento, column=coluna, value=valor)


# --- as 84 colunas viram 27: as que têm destino, as que a regra recusa, e três
# que ninguém mapeou. O resto da largura real não muda nenhuma decisão do
# conversor, e uma fixture de 84 colunas esconde as que importam.
_CADASTRO_CABECALHO = [
    "MATRÍCULA",
    "NOME",
    "ID RH",
    "REGIME",
    "CTPS",
    "SALÁRIO",
    "DATA ÚLTIMO REAJUSTE",
    "ADMISSÃO",
    "CARGO",
    "SUPERVISOR",
    "BANCO",
    "AGÊNCIA",
    "CONTA",
    "PIX",
    "CBO",
    "UNIFORME",
    "NÍVEL",
    "VR",
    "VT",
    "CESTA BÁSICA",
    "PLANO DE SAÚDE",
    "PERICULOSIDADE",
    "CARGO DE CONFIANÇA",
    "UNIDADE DE ATUAÇÃO",
    "E-MAIL CORPORATIVO",
    "TAMANHO DA CAMISA",
    "OBS",
]


def _linha_cadastro(
    matricula: str,
    nome: str,
    indice: int,
    *,
    regime: str = "CLT",
    salario: Any = 2400.00,
    reajuste: date | None = date(2026, 3, 1),
) -> list[Any]:
    return [
        matricula,
        nome,
        f"RH-{indice:03d}",
        regime,
        f"{40000 + indice}/0001",
        salario,
        reajuste,
        date(2024, 5, 10) + timedelta(days=indice * 11),
        "Operador de estacionamento",
        "Ana Almeida",
        "341",
        "1234",
        "56789-0",
        f"{matricula}@exemplo.invalido",
        "5199-05",
        "M",
        "II",
        "R$ 22,00",
        "R$ 8,60",
        "SIM",
        "AMIL 400",
        "NÃO",
        "NÃO",
        "Unidade Centro",
        f"{matricula}@fastpark.invalido",
        "G",
        "—",
    ]


def escrever_planilha(caminho: Path) -> Path:
    """A planilha do cliente, como ela é — e nunca com o que ela tem dentro."""
    wb = Workbook()
    wb.remove(wb.active)

    # 1. DADOS FUNCIONÁRIOS — cabeçalho na 6, com título e legenda em cima.
    ws = wb.create_sheet("DADOS FUNCIONÁRIOS")
    ws["A1"] = "FASTPARK — CONTROLE DE PESSOAL"
    ws["A3"] = "Atualizado por: RH"
    ws["A4"] = "NÃO ALTERAR AS FÓRMULAS"
    linhas = [_linha_cadastro(m, nome, i) for i, (m, nome) in enumerate(PESSOAS, start=1)]
    # Fórmula quebrada onde deveria haver salário.
    linhas[2][5] = "#REF!"
    # Regime fora do catálogo: o valor não entra e a linha continua entrando.
    linhas[3][3] = "EFETIVO"
    # Sem data de reajuste: a vigência inicial cai na admissão.
    linhas[4][6] = None
    # Alguém colou uma linha de outra aba: matrícula que o sistema não conhece.
    linhas.append(_linha_cadastro(FORA_DO_QUADRO, "Pessoa Inexistente", 99))
    # E uma linha sem matrícula nenhuma.
    sem_chave = _linha_cadastro("", "Sem Matrícula", 98)
    sem_chave[0] = None
    linhas.append(sem_chave)
    _preencher(ws, 6, _CADASTRO_CABECALHO, linhas)

    # 2. DESLIGADOS — cabeçalho na 2, e a coluna que a regra 10 recusa.
    ws = wb.create_sheet("DESLIGADOS")
    ws["A1"] = "SAÍDAS 2025/2026"
    _preencher(
        ws,
        2,
        ["MATRÍCULA", "NOME", "DATA DEMISSÃO", "CID", "MOTIVO"],
        [
            # Duas divergências: a planilha diz desligado, o ponto ainda traz.
            [PESSOAS[10][0], PESSOAS[10][1], date(2026, 6, 30), "F32", "Pedido de demissão"],
            [PESSOAS[11][0], PESSOAS[11][1], date(2026, 7, 15), "", "Justa causa"],
            # Estes dois já saíram do quadro ativo: a conferência fecha.
            ["00801", "Já Saiu", date(2025, 2, 1), "", "Fim de contrato"],
            ["00802", "Também Saiu", date(2025, 9, 12), "M54", "Pedido de demissão"],
        ],
    )

    # 3. FALTAS_ATESTADOS — várias linhas por pessoa, e CID de novo.
    ws = wb.create_sheet("FALTAS_ATESTADOS")
    _preencher(
        ws,
        1,
        ["MATRÍCULA", "TIPO", "INÍCIO", "FIM", "CID"],
        [
            [PESSOAS[0][0], "ATESTADO", date(2026, 2, 3), date(2026, 2, 4), "J11"],
            [PESSOAS[0][0], "ATESTADO", date(2026, 5, 18), date(2026, 5, 18), "K52"],
            [PESSOAS[0][0], "LICENÇA", date(2026, 7, 1), date(2026, 7, 20), ""],
            [PESSOAS[1][0], "FALTA", date(2026, 4, 9), date(2026, 4, 9), ""],
            [PESSOAS[2][0], "SUSPENSÃO", date(2026, 6, 2), date(2026, 6, 3), ""],
            [PESSOAS[3][0], "ATESTADO", "#REF!", "#REF!", ""],
        ],
    )

    # 4. MOVIMENTAÇÕES
    ws = wb.create_sheet("MOVIMENTAÇÕES")
    _preencher(
        ws,
        1,
        ["MATRÍCULA", "TIPO", "DATA", "UNIDADE DESTINO", "OBSERVAÇÃO"],
        [
            [PESSOAS[4][0], "TRANSFERÊNCIA", date(2026, 1, 15), "Unidade Norte", "Pedido próprio"],
            [PESSOAS[5][0], "PROMOÇÃO", date(2026, 3, 1), "", "Passou a supervisor"],
            [PESSOAS[6][0], "RETORNO", date(2026, 8, 1), "Unidade Centro", ""],
        ],
    )

    # 5. FÉRIAS — matriz por ano, cabeçalho na 8.
    ws = wb.create_sheet("FÉRIAS")
    ws["A1"] = "PROGRAMAÇÃO DE FÉRIAS"
    ws["A5"] = "Legenda: gozo integral"
    _preencher(
        ws,
        8,
        ["MATRÍCULA", "NOME", "2024 INÍCIO", "2024 FIM", "2025 INÍCIO", "2025 FIM", "2026 INÍCIO"],
        [
            [
                PESSOAS[0][0],
                PESSOAS[0][1],
                date(2024, 7, 1),
                date(2024, 7, 30),
                date(2025, 8, 4),
                date(2025, 9, 2),
                date(2026, 9, 1),
            ],
            [PESSOAS[1][0], PESSOAS[1][1], date(2024, 11, 4), date(2024, 12, 3), None, None, None],
            [PESSOAS[2][0], PESSOAS[2][1], None, None, date(2025, 3, 3), date(2025, 4, 1), None],
        ],
    )

    # 6. CNH — aba oculta com dado vivo dentro.
    ws = wb.create_sheet("CNH")
    ws.sheet_state = "hidden"
    _preencher(
        ws,
        1,
        ["MATRÍCULA", "CATEGORIA", "EMISSÃO", "VALIDADE", "NÚMERO"],
        [
            [PESSOAS[0][0], "AB", date(2021, 4, 2), date(2026, 4, 2), "01234567890"],
            [PESSOAS[3][0], "B", date(2023, 9, 14), HOJE + timedelta(days=18), "09876543210"],
        ],
    )

    # 7. VENCIMENTO ASO — cabeçalho na 2; a coluna de restrição é recusada.
    ws = wb.create_sheet("VENCIMENTO ASO")
    ws["A1"] = "CONTROLE DE EXAMES OCUPACIONAIS"
    _preencher(
        ws,
        2,
        ["MATRÍCULA", "TIPO", "DATA", "VENCIMENTO", "RESULTADO", "RESTRIÇÃO"],
        [
            [PESSOAS[0][0], "PERIÓDICO", date(2025, 9, 2), HOJE + timedelta(days=9), "APTO", ""],
            # O exame anterior da mesma pessoa: a aba guarda histórico, e o
            # modelo carrega um exame por pessoa. Este tem de ser parqueado, não
            # sobrescrever a célula do mais recente.
            [PESSOAS[0][0], "ADMISSIONAL", date(2024, 8, 15), date(2025, 8, 15), "APTO", ""],
            [
                PESSOAS[1][0],
                "ADMISSIONAL",
                date(2024, 5, 20),
                HOJE + timedelta(days=270),
                "APTO",
                "",
            ],
            [
                PESSOAS[2][0],
                "PERIÓDICO",
                date(2025, 8, 1),
                HOJE - timedelta(days=23),
                "APTO COM RESTRIÇÃO",
                "não pode subir escada",
            ],
            [PESSOAS[3][0], "MUDANÇA DE FUNÇÃO", date(2026, 2, 10), None, "APTO", ""],
            [PESSOAS[4][0], "EXAME DE RETORNO", date(2026, 6, 1), None, "APTO", ""],
        ],
    )

    # 8. SINISTROS
    ws = wb.create_sheet("SINISTROS")
    _preencher(
        ws,
        1,
        ["MATRÍCULA", "TIPO", "DESCRIÇÃO", "VALOR", "PARCELAS", "DATA", "SITUAÇÃO"],
        [
            [PESSOAS[0][0], "SINISTRO", "Retrovisor", "R$ 1.200,00", 3, date(2026, 5, 2), "ATIVO"],
            [PESSOAS[5][0], "ADIANTAMENTO", "13º antecipado", 800, 1, date(2026, 6, 1), "QUITADO"],
        ],
    )

    # 9. CONTROLE PARC. — o ponto no fim do nome é do arquivo, não erro de digitação.
    ws = wb.create_sheet("CONTROLE PARC.")
    _preencher(
        ws,
        1,
        ["MATRÍCULA", "PARCELA", "ANO", "MÊS", "VALOR", "SITUAÇÃO"],
        [
            [PESSOAS[0][0], 1, 2026, 6, 400, "DESCONTADA"],
            [PESSOAS[0][0], 2, 2026, 7, 400, "DESCONTADA"],
            [PESSOAS[0][0], 3, 2026, 8, 400, "PENDENTE"],
        ],
    )

    # 10-11. Fora do escopo por decisão, mas presentes no arquivo.
    ws = wb.create_sheet("UNIDADES")
    _preencher(
        ws,
        1,
        ["CÓDIGO", "UNIDADE", "ENDEREÇO"],
        [["01", "Unidade Centro", "Rua A, 100"], ["02", "Unidade Norte", "Av. B, 200"]],
    )
    ws = wb.create_sheet("CÓD POSTOS")
    _preencher(
        ws,
        1,
        ["POSTO", "ENTRADA", "INTERVALO", "SAÍDA"],
        [["P1", "06:00", "12:00", "14:00"], ["P2", "14:00", "18:00", "22:00"]],
    )

    # 12-17. Dashboards: o sistema substitui, não importa.
    for nome, cabecalho, corpo in (
        ("QUADRO GERAL", ["UNIDADE", "ATIVOS", "DESLIGADOS"], ["Centro", 18, 2]),
        ("GERAL", ["MÊS", "HEADCOUNT", "CUSTO"], ["07/2026", 42, "#REF!"]),
        ("FACE GERAL", ["UNIDADE", "BIOMETRIA OK"], ["Centro", "94%"]),
        ("QUADRO_POSTOS", ["POSTO", "PREVISTO", "REALIZADO"], ["P1", 3, 3]),
        ("CESTAS", ["MÊS", "CESTAS ENTREGUES"], ["07/2026", 41]),
        ("Planilha1", ["A", "B"], ["", "#REF!"]),
    ):
        ws = wb.create_sheet(nome)
        _preencher(ws, 1, cabecalho, [list(corpo) for _ in range(3)])

    # 18. A cópia que ficou para trás.
    ws = wb.create_sheet("DADOS FUNCIONÁRIOS (2)")
    copiadas = [_linha_cadastro(m, n, i) for i, (m, n) in enumerate(PESSOAS[:3], start=1)]
    _preencher(ws, 1, _CADASTRO_CABECALHO, copiadas)

    # 19. E a que ninguém mapeou.
    ws = wb.create_sheet("ANIVERSARIANTES")
    _preencher(ws, 1, ["NOME", "DIA"], [["Ana Almeida", "12/03"], ["Bruno Barbosa", "04/11"]])

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def escrever_modelos(
    diretorio: Path,
    *,
    tenant_id: UUID = TENANT,
    gravado: dict[str, dict[str, Any]] | None = None,
) -> Path:
    """Os modelos, como a tela de Importação os entregaria.

    Por padrão vazios nas colunas do RH e preenchidos nas do sistema — o estado
    de quem acabou de rodar o sync e ainda não tem nada de RH gravado.

    `gravado` põe valor nas colunas do RH, por matrícula: é o cliente que **já
    tem** dado no sistema, que é o caso em que o pré-preenchimento pode se
    misturar com a planilha, se o conversor deixar.
    """
    diretorio.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    for tipo, template in TEMPLATES.items():
        linhas = [
            {"registration_number": matricula, "name": nome, **(gravado or {}).get(matricula, {})}
            for matricula, nome in PESSOAS
        ]
        dados = build(
            template,
            linhas,
            tenant_id=tenant_id,
            generated_at=datetime(2026, 8, 24, 9, 30),
        )
        (diretorio / f"modelo-{tipo}.xlsx").write_bytes(dados)
    return diretorio
