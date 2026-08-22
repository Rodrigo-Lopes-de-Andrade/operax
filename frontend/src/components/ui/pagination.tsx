import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { formatNumber } from "@/lib/ponto/format";
import { PAGE_SIZES, type PageSize } from "@/lib/ponto/url";

const NAV_CLASS =
  "border-line flex size-[30px] items-center justify-center rounded-[8px] border transition-colors";

export function Pagination({
  page,
  pageCount,
  total,
  pageSize,
  hrefForPage,
  hrefForSize,
  label = "ocorrências",
}: {
  page: number;
  pageCount: number;
  total: number;
  pageSize: PageSize;
  hrefForPage: (page: number) => string;
  hrefForSize: (size: PageSize) => string;
  label?: string;
}) {
  return (
    <nav
      aria-label="Paginação das ocorrências"
      className="border-line-subtle flex flex-wrap items-center justify-between gap-4 border-t px-5 py-3"
    >
      <p className="text-ink-muted text-xs tabular-nums">
        {formatNumber(total)} {label}
      </p>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1">
          {PAGE_SIZES.map((size) => (
            <Link
              key={size}
              href={hrefForSize(size)}
              aria-current={size === pageSize ? "true" : undefined}
              className={`rounded-full px-2.5 py-1 font-mono text-xs transition-colors ${
                size === pageSize
                  ? "bg-brand-soft/40 text-brand-strong font-bold"
                  : "text-ink-muted hover:bg-muted"
              }`}
            >
              {size}
            </Link>
          ))}
        </div>

        <p className="text-ink-body text-xs font-semibold tabular-nums">
          Página {page} de {Math.max(pageCount, 1)}
        </p>

        <div className="flex items-center gap-1.5">
          {page > 1 ? (
            <Link
              href={hrefForPage(page - 1)}
              aria-label="Página anterior"
              className={NAV_CLASS}
            >
              <ChevronLeft size={16} aria-hidden />
            </Link>
          ) : (
            <span
              aria-disabled
              className={`${NAV_CLASS} text-ink-faint bg-muted`}
            >
              <ChevronLeft size={16} aria-hidden />
            </span>
          )}
          {page < pageCount ? (
            <Link
              href={hrefForPage(page + 1)}
              aria-label="Próxima página"
              className={NAV_CLASS}
            >
              <ChevronRight size={16} aria-hidden />
            </Link>
          ) : (
            <span
              aria-disabled
              className={`${NAV_CLASS} text-ink-faint bg-muted`}
            >
              <ChevronRight size={16} aria-hidden />
            </span>
          )}
        </div>
      </div>
    </nav>
  );
}
