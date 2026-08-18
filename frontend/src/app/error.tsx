"use client";

import { useEffect } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type ErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    // Reaches Sentry once it is wired; the console keeps it visible until then.
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-dvh items-center justify-center px-6">
      <div className="bg-card border-line-subtle flex max-w-md flex-col gap-4 rounded-[18px] border p-6 shadow-[var(--shadow-md)]">
        <h1 className="text-ink text-xl font-extrabold">
          Não foi possível carregar esta tela
        </h1>
        <Alert>
          Algo falhou ao buscar os dados. Nenhuma informação foi perdida.
        </Alert>
        <Button onClick={reset}>Tentar de novo</Button>
      </div>
    </div>
  );
}
