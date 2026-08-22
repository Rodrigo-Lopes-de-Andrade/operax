"""Pydantic schemas — source of truth of the API contract.

The frontend generates its table types from the database; everything the FastAPI
answers is declared here.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from operax.core.tenant import UserRole


class HealthResponse(BaseModel):
    """Liveness of the process. Public, says nothing about the environment."""

    status: Literal["ok"] = "ok"


class AuthenticatedUser(BaseModel):
    """Identity carried by a validated Supabase access token."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str | None = None


class Identity(BaseModel):
    """Who the caller is, plus the tenant and role the backend resolved for them."""

    user_id: UUID
    email: str | None = None
    tenant_id: UUID
    role: UserRole


class EmployeeSummary(BaseModel):
    """Who the person is. No document of identity: that is `app.employee_pii`."""

    employee_id: UUID
    name: str
    registration_number: str | None = None
    cargo: str | None = None
    status: str
    hired_on: date | None = None
    employment_type: str | None = None
    unit_name: str | None = None
    company_name: str | None = None
    department_name: str | None = None
    manager_name: str | None = None


class DeviationIndicators(BaseModel):
    """The cut, for one person. `minutes_balance` is signed; `minutes_abs` is not."""

    events: int
    minutes_abs: int
    minutes_balance: int
    days_with_deviation: int
    pending_cycle: int


class DeviationTypeCount(BaseModel):
    type: str
    description: str
    events: int
    minutes_abs: int


class WorkdayRow(BaseModel):
    """One day of the roster, with the deviation found on it, if any.

    `confidence` comes from `app.expected_workday`: a 12x36 roster inferred from
    the source rarely reaches 100, and a day below the threshold is an
    unconfirmed schedule, not a finding.
    """

    reference_date: date
    day_type: str
    expected_entry: time | None = None
    expected_exit: time | None = None
    confidence: int
    deviation_type: str | None = None
    deviation_description: str | None = None
    direction: str | None = None
    minutes: int | None = None
    expected_time: time | None = None
    actual_time: time | None = None


class JustificationRow(BaseModel):
    reference_date: date
    text: str
    author_name: str | None = None
    source: str


class CompensationBand(BaseModel):
    """Sensitive: `compensation` domain."""

    effective_from: date
    effective_to: date | None = None
    salary: Decimal
    reason: str | None = None


class EmployeeDocument(BaseModel):
    """Sensitive: `pii` domain. The file itself lives in Storage, not here."""

    type_name: str
    valid_until: date | None = None
    status: str


class OccupationalExamRow(BaseModel):
    """Sensitive: `health` domain.

    Fitness and validity only. No diagnosis, no ICD, no description of a
    restriction — the table has no column for any of it (rule 10).
    """

    type: str
    performed_on: date
    valid_until: date | None = None
    result: str | None = None


class EmployeeDetail(BaseModel):
    """Individual consultation.

    The three sensitive blocks are absent — not empty, not masked — when the
    caller's role does not reach that domain. It is the same rule the design
    states for the screen: the role changes what exists, and there is no padlock
    to reason about.
    """

    employee: EmployeeSummary
    indicators: DeviationIndicators
    by_type: list[DeviationTypeCount]
    workdays: list[WorkdayRow]
    justifications: list[JustificationRow]
    compensation: list[CompensationBand] | None = None
    documents: list[EmployeeDocument] | None = None
    exams: list[OccupationalExamRow] | None = None
