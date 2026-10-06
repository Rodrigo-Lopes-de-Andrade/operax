import { ShieldOff, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { InviteForm } from "@/components/usuarios/invite-form";
import { UserList } from "@/components/usuarios/user-list";
import { pageTitle } from "@/lib/brand";
import { isAdmin, loadIdentity } from "@/lib/identity";
import { loadUsersScreen } from "@/lib/usuarios/queries";

export const metadata: Metadata = {
  title: pageTitle("Usuários"),
};

/**
 * Usuários do painel — lista e convite (SPEC-USUARIOS §6, sprint U3).
 *
 * Quem administra usuários é `util.is_admin`: `owner`, `hr` e `personnel`.
 * Outro papel recebe 404, como nas outras telas de administração — a porta não
 * é oferecida. A API decide por último: o 403 dela vira "sem acesso".
 */
export default async function UsuariosPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const { list, units } = await loadUsersScreen();

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Usuários</h1>
        <p className="text-ink-muted mt-1 max-w-3xl text-sm text-pretty">
          Quem entra no painel, com que papel e enxergando quais unidades.
          Convidar dá acesso de consulta; papel com dado sensível só o owner
          concede.
        </p>
      </header>

      <Card>
        <CardHeader
          eyebrow="Convite"
          title="Convidar usuário"
          note="O convite vai por e-mail, e a pessoa define a própria senha."
        />
        <div className="px-5 py-5">
          {units ? (
            <InviteForm units={units} />
          ) : (
            <EmptyState
              icon={TriangleAlert}
              tone="alert"
              title="As unidades não puderam ser lidas"
              description="Sem a lista de empresas e unidades não há como escolher o escopo, e convite sem escopo não existe. Recarregue a página para tentar de novo."
            />
          )}
        </div>
      </Card>

      <Card>
        <CardHeader eyebrow="Lista" title="Usuários deste cliente" />
        {list.status === "ok" ? (
          <UserList users={list.list.users} />
        ) : (
          <div className="p-6">
            {list.status === "forbidden" ? (
              <EmptyState
                icon={ShieldOff}
                tone="neutral"
                title="Sem acesso à lista de usuários"
                description="Só o owner, o RH e o departamento pessoal administram usuários, e a API não reconheceu o seu papel para isso."
              />
            ) : (
              <EmptyState
                icon={TriangleAlert}
                tone="alert"
                title="A lista de usuários não pôde ser lida"
                description="A lista vem da API do painel, e ela não respondeu agora. Recarregue a página para tentar de novo."
              />
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
