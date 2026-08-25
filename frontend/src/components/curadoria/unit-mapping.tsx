"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, requestApiAsUser } from "@/lib/api";
import type {
  UnitMappingRow,
  UnitMappingScreen,
} from "@/lib/curadoria/queries";
import { formatNumber } from "@/lib/ponto/format";

/**
 * Curadoria origem → unidade.
 *
 * O departamento é do Secullum e a unidade é nossa, e ninguém consegue ligar os
 * dois olhando: o nome vem digitado por outra pessoa, em outro sistema, sem
 * combinar nada. Enquanto a ligação não existe, quem está no departamento é
 * promovido **sem unidade** e some de todo recorte por unidade — não aparece
 * como zero, some.
 *
 * A SUGESTÃO NÃO É UM MAPEAMENTO
 * Ela é semelhança de nome, com o número ao lado dizendo o quanto é palpite, e
 * não é gravada até alguém apertar. É o oposto do que a promoção faz de
 * propósito: lá adivinhar é proibido, porque um palpite gravado é
 * indistinguível de um fato lido.
 *
 * O LOTE TEM LIMIAR, E O LIMIAR É DE QUEM CURA
 * "Aplicar tudo" numa lista de quarenta departamentos é assinar embaixo de
 * quarenta palpites. Com limiar, a pessoa decide de onde para cima confia, vê
 * quantas linhas isso alcança **antes** de apertar, e o resto continua na fila.
 *
 * TECLADO
 * Cada linha é um `select` nativo e um botão nativo, na ordem de leitura, então
 * Tab caminha pela fila e Enter confirma a linha em foco. Uma tela de curadoria
 * é usada em rajada por uma pessoa só, e tirar a mão do teclado quarenta vezes
 * é o que faz a fila não ser terminada.
 */
export function UnitMapping({ screen }: { screen: UnitMappingScreen }) {
  const router = useRouter();
  const [threshold, setThreshold] = useState(80);
  const [chosen, setChosen] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<string | null>(null);

  const noLote = screen.rows.filter(
    (row) =>
      row.validated_at === null &&
      row.suggestion !== null &&
      row.suggestion.confidence >= threshold,
  );

  async function apply(mappings: { department: number; unitId: string }[]) {
    if (mappings.length === 0) {
      return;
    }

    setSaving(true);
    setError(null);
    setApplied(null);

    try {
      const result = await requestApiAsUser<{
        validated: number;
        employees_allocated: number;
      }>("/curadoria/unidades", {
        method: "POST",
        body: {
          mappings: mappings.map((each) => ({
            secullum_department_id: each.department,
            unit_id: each.unitId,
          })),
        },
      });

      setChosen({});
      setApplied(
        `${formatNumber(result.validated)} ${result.validated === 1 ? "mapeamento validado" : "mapeamentos validados"} · ` +
          `${formatNumber(result.employees_allocated)} ${
            result.employees_allocated === 1
              ? "colaborador alocado"
              : "colaboradores alocados"
          }`,
      );
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.detail
          ? caught.detail
          : "Não foi possível gravar agora. Nada foi alterado.",
      );
    } finally {
      setSaving(false);
    }
  }

  function unitFor(row: UnitMappingRow): string {
    return (
      chosen[row.secullum_department_id] ??
      row.unit_id ??
      row.suggestion?.unit_id ??
      ""
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Progress screen={screen} />

      <section className="border-line-subtle bg-card flex flex-wrap items-end gap-4 rounded-2xl border p-5">
        <label className="flex flex-col gap-1">
          <span className="text-ink-muted text-xs font-bold">
            Confiança mínima
          </span>
          <input
            type="number"
            min={50}
            max={100}
            step={5}
            value={threshold}
            onChange={(event) =>
              setThreshold(
                Math.min(100, Math.max(50, Number(event.target.value))),
              )
            }
            className="border-line text-ink h-10 w-24 rounded-xl border px-3 text-sm font-bold tabular-nums"
          />
        </label>

        <Button
          onClick={() =>
            apply(
              noLote.map((row) => ({
                department: row.secullum_department_id,
                unitId: row.suggestion!.unit_id,
              })),
            )
          }
          disabled={saving || noLote.length === 0}
        >
          {saving
            ? "Gravando…"
            : `Aplicar ${formatNumber(noLote.length)} ${noLote.length === 1 ? "sugestão" : "sugestões"} ≥ ${threshold}%`}
        </Button>

        <p className="text-ink-faint max-w-md text-xs text-pretty">
          O lote só alcança o que ainda não foi curado, e grava como validado
          por você. Quem já tem unidade não é movido — alocação existente é
          trabalho de alguém.
          <span className="mt-1 block">
            No teclado: <kbd className="font-mono font-bold">Tab</kbd> percorre
            a fila · <kbd className="font-mono font-bold">Enter</kbd> confirma a
            linha em foco.
          </span>
        </p>
      </section>

      {error ? <Alert>{error}</Alert> : null}
      {/* `Alert` é vermelho e vermelho é falha — o sucesso não empresta a caixa
          dela. `role="status"` para o leitor de tela anunciar sem interromper. */}
      {applied ? (
        <p
          role="status"
          className="bg-good-bg text-good rounded-[10px] px-3 py-2 text-sm font-medium"
        >
          {applied}
        </p>
      ) : null}

      <div className="border-line-subtle bg-card overflow-x-auto rounded-2xl border">
        <table className="w-full min-w-[860px] border-collapse text-sm">
          <caption className="sr-only">
            Departamentos da origem e a unidade de cada um
          </caption>
          <thead>
            <tr className="border-line-subtle border-b">
              <Th>Departamento na origem</Th>
              <Th>Empresa</Th>
              <Th align="right">Sem unidade</Th>
              <Th>Unidade</Th>
              <Th>Estado</Th>
              <Th>
                <span className="sr-only">Confirmar</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {screen.rows.map((row) => (
              <tr
                key={row.secullum_department_id}
                className="border-line-subtle border-b last:border-0"
              >
                <Td>
                  <span className="text-ink font-semibold">
                    {row.department}
                  </span>
                  <span className="text-ink-faint block font-mono text-xs">
                    #{row.secullum_department_id} ·{" "}
                    {formatNumber(row.employees)} ativos
                  </span>
                </Td>
                <Td>
                  <span className="text-ink-muted">{row.company_name}</span>
                </Td>
                <Td align="right">
                  <span
                    className={`font-bold tabular-nums ${row.unmapped > 0 ? "text-alert" : "text-ink-faint"}`}
                  >
                    {formatNumber(row.unmapped)}
                  </span>
                </Td>
                <Td>
                  <select
                    aria-label={`Unidade de ${row.department}`}
                    value={unitFor(row)}
                    disabled={saving}
                    onChange={(event) =>
                      setChosen((current) => ({
                        ...current,
                        [row.secullum_department_id]: event.target.value,
                      }))
                    }
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && unitFor(row)) {
                        event.preventDefault();
                        void apply([
                          {
                            department: row.secullum_department_id,
                            unitId: unitFor(row),
                          },
                        ]);
                      }
                    }}
                    className="border-line text-ink h-9 w-full max-w-[220px] rounded-xl border px-2 text-sm"
                  >
                    <option value="">Escolher unidade…</option>
                    {screen.units.map((unit) => (
                      <option key={unit.unit_id} value={unit.unit_id}>
                        {unit.name} · {unit.company_name}
                      </option>
                    ))}
                  </select>
                  {row.suggestion ? (
                    <span className="text-ink-faint mt-1 block text-xs">
                      Sugestão: {row.suggestion.unit_name} ·{" "}
                      {row.suggestion.confidence}%
                    </span>
                  ) : null}
                </Td>
                <Td>
                  <State row={row} />
                </Td>
                <Td align="right">
                  <Button
                    onClick={() =>
                      apply([
                        {
                          department: row.secullum_department_id,
                          unitId: unitFor(row),
                        },
                      ])
                    }
                    disabled={saving || !unitFor(row)}
                    className="h-9 px-4 text-xs"
                  >
                    Confirmar
                  </Button>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * A barra da curadoria, e o provisório é uma faixa própria nela.
 *
 * Somar "com unidade validada" e "provisório" faria a barra chegar ao fim com o
 * trabalho pela metade — que é exatamente o modo mais eficiente de encerrar uma
 * curadoria sem ela estar feita.
 */
function Progress({ screen }: { screen: UnitMappingScreen }) {
  const partes = [
    { label: "Validado", value: screen.validated, tone: "bg-good" },
    { label: "Provisório", value: screen.provisional, tone: "bg-brand" },
    { label: "Sem unidade", value: screen.without_unit, tone: "bg-alert" },
  ];

  return (
    <section className="border-line-subtle bg-card flex flex-col gap-4 rounded-2xl border p-5">
      <div>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Curadoria
        </p>
        <p className="text-ink text-3xl leading-none font-extrabold tabular-nums">
          {formatNumber(screen.validated)}{" "}
          <span className="text-ink-muted text-base font-bold">
            de {formatNumber(screen.active)} ativos com unidade validada
          </span>
        </p>
      </div>

      {screen.active > 0 ? (
        <div className="flex h-2 overflow-hidden rounded-full" aria-hidden>
          {partes
            .filter((parte) => parte.value > 0)
            .map((parte) => (
              <span
                key={parte.label}
                className={parte.tone}
                style={{ width: `${(parte.value / screen.active) * 100}%` }}
              />
            ))}
        </div>
      ) : null}

      <dl className="grid grid-cols-3 gap-4">
        {partes.map((parte) => (
          <div key={parte.label} className="flex flex-col gap-0.5">
            <dt className="text-ink-muted flex items-center gap-1.5 text-xs font-semibold">
              <span
                aria-hidden
                className={`size-2 shrink-0 rounded-full ${parte.tone}`}
              />
              {parte.label}
            </dt>
            <dd className="text-ink text-xl leading-none font-extrabold tabular-nums">
              {formatNumber(parte.value)}
            </dd>
          </div>
        ))}
      </dl>

      <p className="text-ink-faint text-xs text-pretty">
        &quot;Provisório&quot; é mapeamento que existe e ninguém confirmou. Ele
        não entra em &quot;validado&quot; de propósito: quem está nele já
        aparece nos relatórios, e ninguém respondeu se aparece no lugar certo.
      </p>
    </section>
  );
}

function State({ row }: { row: UnitMappingRow }) {
  if (row.validated_at) {
    return <Badge tone="good">validado</Badge>;
  }

  return row.unit_id ? (
    <Badge tone="neutral">provisório</Badge>
  ) : (
    <Badge tone="alert">sem unidade</Badge>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      scope="col"
      className={`text-ink-faint text-2xs px-4 py-3 font-bold tracking-[0.06em] uppercase ${align === "right" ? "text-right" : "text-left"}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <td
      className={`px-4 py-3 align-top ${align === "right" ? "text-right" : "text-left"}`}
    >
      {children}
    </td>
  );
}
