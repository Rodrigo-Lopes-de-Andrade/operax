"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { requestApiAsUser } from "@/lib/api";
import { formatDayInTenantZone } from "@/lib/dp/format";
import {
  BY_ROLE_SCOPE_LABEL,
  type InvitationResent,
  refusalMessage,
  RESEND_ERROR_MESSAGE,
  roleLabel,
  type TenantUser,
} from "@/lib/usuarios/contract";
import { userDetailPath } from "@/lib/usuarios/url";

const COLUMNS = [
  "Nome",
  "E-mail",
  "Papel",
  "Escopo",
  "Status",
  "Convidado por",
  "Ações",
];

/**
 * O escopo como a pessoa o enxerga.
 *
 * ⛔ `by_role` escreve a frase do papel e NUNCA lista `scope` (§3.2): para
 * `owner`, `executive`, `hr` e `personnel` o atalho de `util.can_see_*` responde
 * antes da linha de escopo, e "Empresa Alfa" para quem enxerga três é pior que
 * nada.
 */
function ScopeCell({ user }: { user: TenantUser }) {
  if (user.scope_mode === "by_role") {
    return <span>{BY_ROLE_SCOPE_LABEL}</span>;
  }

  if (user.scope.length === 0) {
    return <span className="text-ink-faint">nenhuma unidade</span>;
  }

  return (
    <ul className="flex flex-col gap-0.5">
      {user.scope.map((entry) => (
        <li key={`${entry.company_id}:${entry.unit_id ?? ""}`}>
          {entry.unit_name
            ? `${entry.company_name} · ${entry.unit_name}`
            : `${entry.company_name} · todas as unidades`}
        </li>
      ))}
    </ul>
  );
}

export function StatusCell({ user }: { user: TenantUser }) {
  if (!user.active) {
    return (
      <Badge tone="neutral">
        Inativo desde {formatDayInTenantZone(user.deactivated_at)}
      </Badge>
    );
  }

  return user.invitation_accepted ? (
    <Badge tone="good" dot>
      Ativo
    </Badge>
  ) : (
    <Badge tone="alert" dot>
      Convite pendente
    </Badge>
  );
}

/**
 * "Reenviar convite", em dois cliques — e nunca "resetar senha" (§5.6): a ação
 * só existe para quem está ativo e ainda não aceitou o convite.
 */
export function ResendInvitation({ user }: { user: TenantUser }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<
    | { kind: "sent"; message: string }
    | { kind: "error"; message: string }
    | null
  >(null);

  const who = user.name ?? user.email ?? "esta pessoa";

  async function confirm() {
    setBusy(true);
    setOutcome(null);

    try {
      // O corpo é `{}`, fechado. Da resposta só o e-mail chega à tela.
      const resent = await requestApiAsUser<InvitationResent>(
        `/usuarios/${user.user_id}/reenviar-convite`,
        { method: "POST", body: {} },
      );
      setOutcome({
        kind: "sent",
        message: `Convite reenviado para ${resent.email}.`,
      });
      setConfirming(false);
    } catch (caught) {
      setOutcome({
        kind: "error",
        message: refusalMessage(
          caught,
          RESEND_ERROR_MESSAGE,
          "Não consegui reenviar o convite agora. Tente de novo.",
        ),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      {confirming ? (
        <div
          role="group"
          aria-label={`Confirmar reenvio do convite para ${who}`}
          className="flex flex-col gap-2"
        >
          <p className="text-ink text-sm text-pretty">
            Reenviar o e-mail de convite para <strong>{who}</strong>?
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              onClick={() => void confirm()}
              disabled={busy}
            >
              {busy ? "Reenviando…" : "Confirmar reenvio"}
            </Button>
            <button
              type="button"
              onClick={() => {
                setConfirming(false);
                setOutcome(null);
              }}
              disabled={busy}
              className="text-ink-muted hover:text-ink text-sm font-bold"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="text-brand-strong hover:text-ink text-sm font-bold"
        >
          Reenviar convite
        </button>
      )}

      {outcome?.kind === "error" ? <Alert>{outcome.message}</Alert> : null}
      {outcome?.kind === "sent" ? (
        <p role="status" className="text-good text-sm font-medium">
          {outcome.message}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A lista de usuários do tenant: ativos primeiro (a ordem é da API), inativos
 * em cinza com a data da desativação. Nenhum uuid aparece — o `user_id` é só a
 * chave da linha e o destino da ação.
 */
export function UserList({ users }: { users: TenantUser[] }) {
  if (users.length === 0) {
    return (
      <p className="text-ink-muted px-5 py-6 text-sm">
        Nenhum usuário neste cliente ainda.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">Usuários do painel</caption>
        <thead>
          <tr className="bg-muted">
            {COLUMNS.map((label) => (
              <th
                key={label}
                scope="col"
                className="border-line-subtle text-ink-muted text-2xs border-b px-4 py-2.5 font-bold tracking-[0.06em] uppercase first:pl-[22px] last:pr-[22px]"
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr
              key={user.user_id}
              data-inactive={user.active ? undefined : ""}
              className={`border-line-subtle border-t align-top text-sm ${
                user.active ? "text-ink" : "text-ink-faint"
              }`}
            >
              <td className="py-3 pr-4 pl-[22px] font-bold">
                <Link
                  href={userDetailPath(user.user_id)}
                  className="hover:text-brand-strong underline-offset-2 hover:underline"
                >
                  {user.name ?? <span className="font-normal">sem nome</span>}
                </Link>
              </td>
              <td className="px-4 py-3">{user.email ?? "—"}</td>
              <td className="px-4 py-3 whitespace-nowrap">
                {roleLabel(user.role)}
              </td>
              <td className="px-4 py-3">
                <ScopeCell user={user} />
              </td>
              <td className="px-4 py-3 whitespace-nowrap">
                <StatusCell user={user} />
              </td>
              <td className="px-4 py-3">
                {user.invited_by
                  ? (user.invited_by.name ?? user.invited_by.email ?? "—")
                  : "—"}
              </td>
              <td className="py-3 pr-[22px] pl-4">
                {user.active && !user.invitation_accepted ? (
                  <ResendInvitation user={user} />
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
