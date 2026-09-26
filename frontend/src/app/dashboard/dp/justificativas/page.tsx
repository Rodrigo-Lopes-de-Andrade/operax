import { CalendarOff } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LeaveJustifications } from "@/components/dp/leave-justifications";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadLeaveJustifications } from "@/lib/dp/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Justificativas de afastamento"),
};

/**
 * Curadoria de justificativa de afastamento — cadastro, e não operação.
 *
 * ⚠️ ESTA NÃO É A TELA DE JUSTIFICATIVAS DE `/dashboard/justificativas`. Aquela
 * é o gestor explicando o indício de uma pessoa num dia; aqui o
 * `JustificativaNome` que o Secullum manda ganha categoria de domínio, uma vez,
 * para todos os afastamentos que carregam a mesma string.
 *
 * ✅ A PORTA É `isAdmin`, E AQUI ELA NÃO É CÓPIA DE MATRIZ NENHUMA
 * As três rotas exigem `util.is_admin` sozinho — sem domínio sensível ao lado,
 * ao contrário de Rubricas. `isAdmin` é a cópia de `util.is_admin`, lista fixa
 * de papéis nos dois lados, então a página e a API concordam por construção. O
 * 403 continua tratado: quando as duas listas divergirem, quem manda é a API, e
 * é a frase dela que a pessoa lê.
 */
export default async function JustificativasDeAfastamentoPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const result = await loadLeaveJustifications();

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Departamento pessoal
        </p>
        <h1 className="text-ink text-2xl font-extrabold">
          Justificativas de afastamento
        </h1>
        <p className="text-ink-muted mt-1 max-w-3xl text-sm text-pretty">
          Cada justificativa que o Secullum escreve num afastamento vira uma
          categoria do domínio, e é ela que decide quem perde cesta e quantos
          dias de vale transporte. São dois atos: classificar propõe, validar é
          o que libera a apuração da competência. Enquanto houver uma sem aval,
          a apuração recusa o mês inteiro — e a string aparece aqui como a
          origem a escreveu, truncada e tudo, porque é ela a chave.
        </p>
      </header>

      {result?.status === "ok" ? (
        <LeaveJustifications screen={result.list} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={CalendarOff}
            tone="neutral"
            title={
              result?.status === "forbidden"
                ? "Este papel não classifica justificativa de afastamento"
                : "A fila de curadoria não pôde ser lida"
            }
            description={
              result?.status === "forbidden"
                ? (result.detail ??
                  "A API recusou a leitura para o seu papel, sem dizer por quê.")
                : "A fila vem da API do painel, e ela não respondeu agora. Nada foi alterado."
            }
          />
        </Card>
      )}
    </div>
  );
}
