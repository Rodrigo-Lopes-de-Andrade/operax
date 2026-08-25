"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

export type Column = {
  key: string;
  label: string;
  align?: "left" | "right";
  width?: string;
  mono?: boolean;
  numeric?: boolean;
  noWrap?: boolean;
};

export type Row = {
  id: string;
  /** Where the row leads. The drawer is a URL, so a row is a link. */
  href?: string;
  cells: Record<string, ReactNode>;
};

const DENSITY_CLASS = {
  compact: "py-2",
  default: "py-3",
  relaxed: "py-4",
} as const;

/**
 * The backbone of the product: the occurrences list, the daily monitor, the
 * punch history and the import errors are all this component.
 *
 * The row navigates on click for the mouse, and the first cell carries a real
 * link so the keyboard and a screen reader get there too — a `tr` cannot be an
 * anchor, and an `onClick` alone would be a dead end without a pointer.
 *
 * The wrapper scrolls horizontally: no table bleeds past the card on a narrow
 * viewport.
 */
export function Table({
  columns,
  rows,
  density = "default",
  caption,
  empty,
}: {
  columns: Column[];
  rows: Row[];
  density?: keyof typeof DENSITY_CLASS;
  caption?: string;
  empty?: ReactNode;
}) {
  const router = useRouter();

  if (rows.length === 0 && empty) {
    return <>{empty}</>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="bg-muted">
            {columns.map((column, index) => (
              <th
                key={column.key}
                scope="col"
                style={{ width: column.width }}
                className={`border-line-subtle text-ink-muted text-2xs border-b py-2.5 font-bold tracking-[0.06em] uppercase ${
                  column.align === "right" ? "text-right" : "text-left"
                } ${index === 0 || index === columns.length - 1 ? "px-[22px]" : "px-4"}`}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              onClick={
                row.href ? () => router.push(row.href as string) : undefined
              }
              className={`border-line-subtle border-t ${
                row.href
                  ? "hover:bg-muted cursor-pointer transition-colors"
                  : ""
              }`}
            >
              {columns.map((column, index) => (
                <td
                  key={column.key}
                  className={`${DENSITY_CLASS[density]} align-middle ${
                    column.align === "right" ? "text-right" : "text-left"
                  } ${column.numeric ? "tabular-nums" : ""} ${
                    column.mono ? "font-mono text-sm" : "text-sm"
                  } ${column.noWrap ? "whitespace-nowrap" : ""} ${
                    index === 0 || index === columns.length - 1
                      ? "px-[22px]"
                      : "px-4"
                  }`}
                >
                  {row.cells[column.key] ?? (
                    <span className="text-ink-faint">—</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
