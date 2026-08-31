import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PayrollImport } from "@/components/folha/payroll-import";
import { pageTitle } from "@/lib/brand";
import { isAdmin, loadIdentity } from "@/lib/identity";
import { IMPORTACAO_PATH } from "@/lib/rh/url";

export const metadata: Metadata = {
  title: pageTitle("Folha"),
};

/**
 * Importação da folha de pagamento.
 *
 * A integração com a contabilidade na v1 é arquivo, não API: o escritório manda
 * a planilha da competência e alguém a envia aqui. É a mesma esteira de quatro
 * passos do import de RH, com o destino trocado — `app.payroll_period` e
 * `app.payroll_entry`, no domínio sensível de remuneração.
 *
 * `isAdmin` e não `reachesHr`: esta tela só escreve. O `executive` alcança a
 * área de RH para ler e não publica folha, então recebe 404 em vez de uma tela
 * cujos dois botões respondem 403. A segurança não é essa — é o backend
 * perguntar `util.is_admin` e `util.can_see_domain(tenant, 'compensation')` ao
 * banco em toda chamada.
 */
export default async function FolhaPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            Administração
          </p>
          <h1 className="text-ink text-xl font-extrabold">Folha</h1>
        </div>
        <Link
          href={IMPORTACAO_PATH}
          className="text-brand-strong text-sm font-bold underline"
        >
          Importação de RH
        </Link>
      </header>

      <PayrollImport />
    </div>
  );
}
