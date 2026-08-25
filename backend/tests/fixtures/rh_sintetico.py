"""Planilha sintética de RH — inventada, nunca a do cliente.

Regra 7 da etapa: dado real não entra em teste. A planilha do cliente só é lida
pelo conversor, na implantação, fora do repositório. Estas linhas existem para
que os validadores tenham contra o que falhar, e cada uma foi desenhada em cima
de um erro que a planilha real de fato produz — cabeçalho remontado à mão,
matrícula colada de outra aba, vigência retroagindo para o ano passado.

Os CPFs são os inválidos canônicos de teste (`000.000.001-91` e vizinhos), os
nomes são de personagens, e nenhuma matrícula corresponde a pessoa nenhuma.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

# Quem existe no tenant, do ponto de vista do import: o espelho já criou estas
# pessoas e o template de vínculo já preencheu o ID RH de duas delas.
ANA = UUID("aaaa0000-0000-4000-8000-000000000001")
BRUNO = UUID("bbbb0000-0000-4000-8000-000000000002")
CARLA = UUID("cccc0000-0000-4000-8000-000000000003")

POR_MATRICULA: dict[str, UUID] = {"1001": ANA, "1002": BRUNO, "1003": CARLA}
POR_HR_CODE: dict[str, UUID] = {"RH-01": ANA, "RH-02": BRUNO}

# O que o banco tem hoje para a Ana — o lado "atual" da comparação de dono.
ATUAL_ANA: dict[str, Any] = {
    "registration_number": "1001",
    "name": "Ana Personagem",
    "hired_on": date(2024, 3, 1),
    "status": "active",
    "hr_code": "RH-01",
    "employment_type": "clt",
}

# Linha boa: mexe só no que é do RH.
LINHA_OK: dict[str, Any] = {
    "registration_number": "1001",
    "hr_code": "RH-01",
    "name": "Ana Personagem",
    "employment_type": "pj",
}

# As duas chaves apontando para pessoas diferentes — o caso que nunca pode virar
# escolha silenciosa.
LINHA_CHAVES_DIVERGEM: dict[str, Any] = {"registration_number": "1001", "hr_code": "RH-02"}

# Fase inicial do vínculo: o ID RH ainda está vazio para todo mundo.
LINHA_SEM_HR_CODE: dict[str, Any] = {"registration_number": "1003", "hr_code": ""}

# Alguém reescreveu o nome que vem do ponto.
LINHA_MEXE_NO_SYNC: dict[str, Any] = {
    "registration_number": "1001",
    "name": "Ana P. Personagem",
    "status": "desligado",
}

LINHA_ENUM_INVALIDO: dict[str, Any] = {
    "registration_number": "1001",
    "employment_type": "efetivo",
}

# Acordo de 1.200 em 3 parcelas — e as três formas de ele não fechar.
ACORDO_OK: dict[str, Any] = {
    "type": "vehicle_damage",
    "status": "active",
    "total_amount": Decimal("1200.00"),
    "installment_count": 3,
}
PARCELAS_OK: list[dict[str, Any]] = [
    {"number": 1, "amount": Decimal("400.00")},
    {"number": 2, "amount": Decimal("400.00")},
    {"number": 3, "amount": Decimal("400.00")},
]
PARCELAS_NAO_SOMAM: list[dict[str, Any]] = [
    {"number": 1, "amount": Decimal("400.00")},
    {"number": 2, "amount": Decimal("400.00")},
    {"number": 3, "amount": Decimal("300.00")},
]
PARCELAS_NUMERACAO_PULADA: list[dict[str, Any]] = [
    {"number": 1, "amount": Decimal("400.00")},
    {"number": 2, "amount": Decimal("400.00")},
    {"number": 4, "amount": Decimal("400.00")},
]

# Afastamentos já registrados para a Ana, um deles em aberto.
AFASTAMENTOS_ANA: list[tuple[date, date | None]] = [
    (date(2026, 3, 2), date(2026, 3, 20)),
    (date(2026, 7, 1), None),
]
