import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/kpi-card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { EmployeeSummary } from "@/lib/colaborador/queries";
import { colaboradorHref } from "@/lib/colaborador/url";
import { PERIODS, PERIOD_LABEL, type Period } from "@/lib/ponto/filters";
import { formatDayLong } from "@/lib/ponto/format";

const PERIOD_OPTIONS = PERIODS.map((period) => ({
  value: period,
  label: PERIOD_LABEL[period],
}));

const STATUS_LABEL: Record<string, string> = {
  active: "Ativo",
  vacation: "Em férias",
  afastado: "Afastado",
  desligado: "Desligado",
};

const EMPLOYMENT_LABEL: Record<string, string> = {
  clt: "CLT",
  pj: "PJ",
  internship: "Estágio",
  temporary: "Temporário",
  apprentice: "Aprendiz",
  contractor: "Terceirizado",
};

export function EmployeeHeader({
  employee,
  period,
}: {
  employee: EmployeeSummary;
  period: Period;
}) {
  const line = [
    employee.cargo,
    employee.unit_name,
    employee.department_name,
    employee.registration_number
      ? `matrícula ${employee.registration_number}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Iniciais, nunca foto: o produto não renderiza imagem de pessoa. */}
          <span className="bg-brand-soft/50 text-brand-strong flex size-14 items-center justify-center rounded-full text-lg font-extrabold">
            {initials(employee.name)}
          </span>
          <div>
            <h1 className="text-ink text-2xl font-extrabold">
              {employee.name}
            </h1>
            <p className="text-ink-muted text-sm">{line}</p>
          </div>
        </div>

        <SegmentedControl<Period>
          label="Período"
          options={PERIOD_OPTIONS}
          value={period}
          hrefFor={(next) => colaboradorHref(employee.employee_id, next)}
        />
      </div>

      <dl className="border-line-subtle grid gap-4 border-t pt-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Empresa" value={employee.company_name} />
        <Field label="Gestor" value={employee.manager_name} />
        <Field
          label="Admissão"
          value={employee.hired_on ? formatDayLong(employee.hired_on) : null}
        />
        <div>
          <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            Situação
          </dt>
          <dd className="mt-1 flex flex-wrap items-center gap-2">
            <Badge tone={employee.status === "active" ? "good" : "alert"} dot>
              {STATUS_LABEL[employee.status] ?? employee.status}
            </Badge>
            {employee.employment_type ? (
              <span className="text-ink-muted text-xs font-semibold">
                {EMPLOYMENT_LABEL[employee.employment_type] ??
                  employee.employment_type}
              </span>
            ) : null}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        {label}
      </dt>
      <dd className="text-ink-body mt-1 text-sm font-semibold">
        {value ?? <span className="text-ink-faint font-normal">—</span>}
      </dd>
    </div>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);

  return ((parts[0]?.[0] ?? "") + (parts.at(-1)?.[0] ?? "")).toUpperCase();
}
