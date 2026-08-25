import type { Metadata } from "next";

import { Conversation } from "@/components/assistente/conversation";
import { pageTitle } from "@/lib/brand";

export const metadata: Metadata = {
  title: pageTitle("Assistente"),
};

/**
 * Assistente — Caminho 2, e o mais estrito deles.
 *
 * A página é server component e não carrega dado nenhum: a conversa inteira
 * passa pelo FastAPI, que roda a métrica **como o usuário**. Buscar qualquer
 * coisa aqui abriria um segundo caminho para o mesmo dado, e a garantia do
 * assistente é justamente não existir um segundo caminho.
 */
export default function AssistentePage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Operação
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Assistente</h1>
        <p className="text-ink-muted pt-1 text-sm">
          Pergunte em português. A resposta vem das métricas do painel e mostra
          o período e os filtros que foram usados — e o seu acesso continua
          valendo: o assistente não alcança nada que você já não alcance.
        </p>
      </header>

      <Conversation />
    </div>
  );
}
