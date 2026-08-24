import { Chip } from "@/components/ui/badge";
import { formatClock } from "@/lib/ponto/format";
import { SYNC_FIELD_LABEL, label } from "@/lib/rh/labels";
import type { HrSyncField } from "@/lib/rh/queries";

/**
 * O bloco do que o sistema de ponto governa.
 *
 * Agrupado e rotulado com a origem, em vez de espalhado entre campos editáveis:
 * a pessoa que abre a tela precisa saber, antes de tentar, quais valores não
 * adianta corrigir aqui. Sem cadeado e sem cinza-desabilitado — é um bloco de
 * leitura com a origem escrita em cima, que é a informação de verdade.
 *
 * O horário é o da última leitura da sincronização, o mesmo que a pílula do
 * cabeçalho mostra. Sem ele, "origem: Secullum" não diz se o valor é de hoje ou
 * de anteontem.
 */
export function ProvenanceBlock({
  fields,
  syncedAt,
}: {
  fields: HrSyncField[];
  syncedAt: string | null;
}) {
  return (
    <section className="flex flex-col gap-3">
      <header className="flex flex-wrap items-baseline gap-2">
        <h3 className="text-ink text-sm font-extrabold">
          Vem do sistema de ponto
        </h3>
        <p className="text-ink-muted text-xs">
          {syncedAt
            ? `Secullum · leitura de ${formatClock(syncedAt)}`
            : "Secullum · sem leitura registrada"}
          . Alterar aqui não teria efeito: a próxima sincronização traria o
          valor de volta.
        </p>
      </header>

      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map((field) => (
          <div key={field.column} className="flex flex-col gap-0.5">
            <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
              {label(SYNC_FIELD_LABEL, field.column)}
            </dt>
            <dd className="text-ink text-sm font-semibold">
              {field.value ?? "—"}
            </dd>
            {field.pending ? (
              // Os três campos que ninguém confirmou ainda. Congelados porque
              // congelar é o lado seguro do erro — e rotulados para a tela não
              // afirmar uma origem que não foi checada.
              <Chip>origem a confirmar com o cliente</Chip>
            ) : field.mirror ? (
              <span className="text-ink-faint font-mono text-2xs">
                {field.mirror}
              </span>
            ) : null}
          </div>
        ))}
      </dl>
    </section>
  );
}
