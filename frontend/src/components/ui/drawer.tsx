"use client";

import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

/**
 * Side panel of detail. It is open because the URL says so (`?ev=…`), so every
 * way of closing it is the same navigation — Esc, the scrim and the button all
 * go back to the cut without the occurrence.
 *
 * That is also what makes the link in the WhatsApp alert land straight on the
 * open drawer.
 */
export function Drawer({
  title,
  eyebrow,
  subtitle,
  closeHref,
  footer,
  children,
}: {
  title: string;
  eyebrow?: string;
  subtitle?: string;
  closeHref: string;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const router = useRouter();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panel.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        router.push(closeHref);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closeHref, router]);

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <button
        type="button"
        aria-label="Fechar detalhe"
        onClick={() => router.push(closeHref)}
        className="absolute inset-0 bg-[var(--scrim)]"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="bg-card relative flex h-full w-full max-w-[520px] flex-col shadow-[var(--shadow-lg)] outline-none"
      >
        <header className="border-line-subtle flex items-start justify-between gap-4 border-b px-6 py-5">
          <div>
            {eyebrow ? (
              <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
                {eyebrow}
              </p>
            ) : null}
            <h2 className="text-ink text-xl font-extrabold">{title}</h2>
            {subtitle ? (
              <p className="text-ink-muted mt-1 text-sm">{subtitle}</p>
            ) : null}
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={() => router.push(closeHref)}
            className="text-ink-muted hover:bg-muted flex size-8 items-center justify-center rounded-full transition-colors"
          >
            <X size={18} aria-hidden />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>

        {footer ? (
          <footer className="border-line-subtle border-t px-6 py-4">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}
