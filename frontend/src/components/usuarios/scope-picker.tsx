"use client";

import type { UnitOption } from "@/lib/ponto/queries";
import type { InvitationScopeEntry } from "@/lib/usuarios/contract";

/**
 * Uma escolha do seletor: a empresa inteira, ou uma unidade. A unidade é só o
 * id dela — a empresa que vai junto sai da própria linha de `vw_unit` na hora
 * do envio, nunca de uma escolha separada. É isso que impede montar unidade
 * sem empresa ou o par trocado (§3.3).
 */
export type ScopeKey = `company:${string}` | `unit:${string}`;

type Company = { id: string; name: string; units: UnitOption[] };

function companiesOf(units: UnitOption[]): Company[] {
  const byId = new Map<string, Company>();

  for (const unit of units) {
    if (!unit.companyId) {
      continue;
    }

    const company = byId.get(unit.companyId) ?? {
      id: unit.companyId,
      name: unit.companyName,
      units: [],
    };
    company.units.push(unit);
    byId.set(unit.companyId, company);
  }

  return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * As escolhas viram o corpo. "Todas as unidades" vai como `{company_id}` sem a
 * chave `unit_id` — `unit_id: null` é recusado pela API, de propósito. A
 * unidade vai com o `company_id` da própria linha.
 */
export function scopeEntries(
  keys: string[],
  units: UnitOption[],
): InvitationScopeEntry[] {
  const entries: InvitationScopeEntry[] = [];

  for (const key of keys) {
    if (key.startsWith("company:")) {
      entries.push({ company_id: key.slice("company:".length) });
      continue;
    }

    const unit = units.find(
      (option) => option.unitId === key.slice("unit:".length),
    );
    if (unit && unit.companyId) {
      entries.push({ company_id: unit.companyId, unit_id: unit.unitId });
    }
  }

  return entries;
}

/**
 * O seletor de escopo do convite e do detalhe: empresa inteira ou unidades,
 * agrupadas por empresa. Não tem estado vazio válido — quem o usa recusa zero
 * escolha antes de enviar.
 */
export function ScopePicker({
  units,
  value,
  onChange,
  error,
  errorId,
}: {
  units: UnitOption[];
  value: string[];
  onChange: (keys: string[]) => void;
  error?: string;
  errorId: string;
}) {
  const companies = companiesOf(units);
  const selected = new Set(value);

  function toggleCompany(company: Company, on: boolean) {
    const unitKeys = new Set(
      company.units.map((unit) => `unit:${unit.unitId}`),
    );
    // A empresa inteira absorve as unidades dela: elas saem da seleção.
    const rest = value.filter(
      (key) => key !== `company:${company.id}` && !unitKeys.has(key),
    );
    onChange(on ? [...rest, `company:${company.id}`] : rest);
  }

  function toggleUnit(unit: UnitOption, on: boolean) {
    const key: ScopeKey = `unit:${unit.unitId}`;
    const rest = value.filter((candidate) => candidate !== key);
    onChange(on ? [...rest, key] : rest);
  }

  return (
    <fieldset
      className="flex flex-col gap-3"
      aria-describedby={error ? errorId : undefined}
      aria-invalid={error ? true : undefined}
    >
      <legend className="text-2xs text-ink-muted mb-1 font-bold tracking-[0.08em] uppercase">
        Escopo
      </legend>
      <p className="text-ink-muted text-sm text-pretty">
        Marque a empresa inteira ou as unidades que a pessoa vai enxergar.
        Empresa nova não entra sozinha no escopo: quando o cliente abrir outra
        empresa, ela precisa ser incluída aqui.
      </p>

      {companies.length === 0 ? (
        <p className="text-ink-muted text-sm">
          Nenhuma unidade ativa para escolher. Sem escopo, não há convite.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {companies.map((company) => {
            const whole = selected.has(`company:${company.id}`);

            return (
              <li
                key={company.id}
                className="border-line-subtle rounded-[12px] border p-3"
              >
                <label className="text-ink flex items-center gap-2 text-sm font-bold">
                  <input
                    type="checkbox"
                    checked={whole}
                    onChange={(event) =>
                      toggleCompany(company, event.target.checked)
                    }
                  />
                  {company.name} · todas as unidades
                </label>
                {whole ? null : (
                  <ul className="mt-2 grid gap-1.5 pl-6 sm:grid-cols-2">
                    {company.units.map((unit) => (
                      <li key={unit.unitId}>
                        <label className="text-ink flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={selected.has(`unit:${unit.unitId}`)}
                            onChange={(event) =>
                              toggleUnit(unit, event.target.checked)
                            }
                          />
                          {unit.name}
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {error ? (
        <p id={errorId} className="text-bad text-xs font-medium">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}

/** Quantas empresas o seletor oferece — zero desabilita o envio. */
export function hasCompanies(units: UnitOption[]): boolean {
  return companiesOf(units).length > 0;
}
