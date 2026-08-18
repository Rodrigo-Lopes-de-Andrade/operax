import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Painel · OperaX",
};

export default function DashboardPage() {
  return (
    <section className="bg-card border-line-subtle rounded-[18px] border p-6 shadow-[var(--shadow-sm)]">
      <p className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
        Painel
      </p>
      <h1 className="text-ink mt-1 text-2xl font-extrabold">
        Sua sessão está ativa
      </h1>
      <p className="text-ink-muted mt-2 max-w-xl text-sm">
        A gestão de ponto, o monitor diário e a consulta individual entram nesta
        área. Nenhum indício é exibido até o motor de detecção publicar dados.
      </p>
    </section>
  );
}
