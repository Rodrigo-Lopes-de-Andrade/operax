import { ArrowLeft, ShieldOff, TriangleAlert, UserX } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { EmptyState } from "@/components/ui/empty-state";
import { UserDetail } from "@/components/usuarios/user-detail";
import { pageTitle } from "@/lib/brand";
import { isAdmin, loadIdentity } from "@/lib/identity";
import { loadUserDetailScreen } from "@/lib/usuarios/queries";
import { USUARIOS_PATH } from "@/lib/usuarios/url";

export const metadata: Metadata = {
  title: pageTitle("Usuário"),
};

const userIdSchema = z.uuid();

/**
 * O detalhe de um usuário do painel (SPEC-USUARIOS §6, sprint U4).
 *
 * A mesma porta da lista: só `owner`, `hr` e `personnel`, e 404 para os
 * outros. O seletor de papel só se habilita para o owner — o papel do chamador
 * vem de `/me`. A API decide por último em cada ação.
 */
export default async function UsuarioPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = await params;
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  // Um id que não é uuid não é usuário de ninguém: nem chega à API.
  if (!userIdSchema.safeParse(userId).success) {
    notFound();
  }

  const { detail, matrix, units } = await loadUserDetailScreen(userId);

  return (
    <div className="flex flex-col gap-4">
      <header>
        <Link
          href={USUARIOS_PATH}
          className="text-ink-muted hover:text-ink inline-flex items-center gap-1 text-sm font-bold"
        >
          <ArrowLeft aria-hidden className="size-4" />
          Usuários
        </Link>
        <p className="text-2xs text-ink-faint mt-3 font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Detalhe do usuário</h1>
      </header>

      {detail.status === "ok" ? (
        <UserDetail
          user={detail.user}
          matrix={matrix}
          units={units}
          callerIsOwner={identity?.role === "owner"}
        />
      ) : detail.status === "not_found" ? (
        <EmptyState
          icon={UserX}
          tone="neutral"
          title="Usuário não encontrado"
          description="Esse usuário não é deste cliente, ou o link está errado. Volte à lista de usuários."
        />
      ) : detail.status === "forbidden" ? (
        <EmptyState
          icon={ShieldOff}
          tone="neutral"
          title="Sem acesso a este usuário"
          description="Só o owner, o RH e o departamento pessoal administram usuários, e a API não reconheceu o seu papel para isso."
        />
      ) : (
        <EmptyState
          icon={TriangleAlert}
          tone="alert"
          title="O usuário não pôde ser lido"
          description="Os dados do usuário vêm da API do painel, e ela não respondeu agora. Recarregue a página para tentar de novo."
        />
      )}
    </div>
  );
}
