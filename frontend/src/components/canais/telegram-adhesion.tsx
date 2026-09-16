import type { TelegramAdhesionRow } from "@/lib/canais/queries";
import { formatNumber } from "@/lib/ponto/format";

/**
 * As quatro colunas de contagem, na ordem da tela. `pending` é **não
 * aderiram** — a adesão é voluntária (decisão do dono, 16/09/2026), e
 * "pendentes" ou "faltam" transformaria um número em cobrança.
 */
const COUNTS = [
  { key: "joined", label: "Aderiram" },
  { key: "pending", label: "Não aderiram" },
  { key: "revoked", label: "Revogaram" },
] as const;

type CountKey = (typeof COUNTS)[number]["key"];

/** O total da linha é a soma das três colunas — a RPC não devolve um quarto. */
function total(row: Record<CountKey, number>): number {
  return row.joined + row.pending + row.revoked;
}

const HEAD_CLASS =
  "border-line-subtle text-ink-muted text-2xs border-b py-2.5 font-bold tracking-[0.06em] uppercase";
const NUMBER_CLASS = "px-4 py-2 text-right text-sm tabular-nums";

/**
 * A adesão ao Telegram por unidade — `public.fn_telegram_adhesion()`, o único
 * lugar em que o painel olha para `app.messaging_identity`, e por contagem.
 *
 * Uma linha por unidade visível, com **aderiram**, **não aderiram**,
 * **revogaram** e o total da linha (a soma das três — a função de banco
 * garante que elas partem os colaboradores ativos da unidade), e a soma de
 * cada coluna no rodapé. Sem nome, sem `chat_id`: a RPC não os devolve e o
 * tipo não os tem; a tabela lista unidades, e é só isso que ela sabe listar.
 * As linhas saem na ordem em que a RPC as entregou.
 *
 * `null` é "não pôde ser lida" (a RPC falhou); `[]` é "nenhuma unidade com
 * colaboradores" — dois estados, duas frases, como no resto da tela.
 */
export function TelegramAdhesion({
  rows,
}: {
  rows: TelegramAdhesionRow[] | null;
}) {
  if (rows === null) {
    return (
      <p className="text-ink-muted px-5 py-2 text-sm text-pretty">
        A adesão não pôde ser lida agora.
      </p>
    );
  }

  if (rows.length === 0) {
    return (
      <p className="text-ink-muted px-5 py-2 text-sm text-pretty">
        Nenhuma unidade com colaboradores.
      </p>
    );
  }

  const sum = {
    joined: rows.reduce((acc, row) => acc + row.joined, 0),
    pending: rows.reduce((acc, row) => acc + row.pending, 0),
    revoked: rows.reduce((acc, row) => acc + row.revoked, 0),
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">Adesão ao Telegram por unidade</caption>
        <thead>
          <tr className="bg-muted">
            <th scope="col" className={`${HEAD_CLASS} px-[22px] text-left`}>
              Unidade
            </th>
            {COUNTS.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`${HEAD_CLASS} px-4 text-right`}
              >
                {column.label}
              </th>
            ))}
            <th scope="col" className={`${HEAD_CLASS} px-[22px] text-right`}>
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.unit_id} className="border-line-subtle border-t">
              <th
                scope="row"
                className="text-ink px-[22px] py-2 text-left text-sm font-semibold"
              >
                {row.unit_name}
              </th>
              {COUNTS.map((column) => (
                <td key={column.key} className={`text-ink ${NUMBER_CLASS}`}>
                  {formatNumber(row[column.key])}
                </td>
              ))}
              <td className="text-ink px-[22px] py-2 text-right text-sm font-bold tabular-nums">
                {formatNumber(total(row))}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-line-strong border-t-2">
            <th
              scope="row"
              className="text-ink px-[22px] py-2 text-left text-sm font-extrabold"
            >
              Total
            </th>
            {COUNTS.map((column) => (
              <td
                key={column.key}
                className={`text-ink font-bold ${NUMBER_CLASS}`}
              >
                {formatNumber(sum[column.key])}
              </td>
            ))}
            <td className="text-ink px-[22px] py-2 text-right text-sm font-extrabold tabular-nums">
              {formatNumber(total(sum))}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
