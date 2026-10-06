"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useController, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import {
  hasCompanies,
  ScopePicker,
  scopeEntries,
} from "@/components/usuarios/scope-picker";
import { ResendInvitation, StatusCell } from "@/components/usuarios/user-list";
import { requestApiAsUser } from "@/lib/api";
import type { UnitOption } from "@/lib/ponto/queries";
import {
  BY_ROLE_SCOPE_LABEL,
  DEACTIVATE_ERROR_MESSAGE,
  domainLabel,
  refusalMessage,
  ROLE_ERROR_MESSAGE,
  ROLE_LABEL,
  roleLabel,
  type RoleDomainMatrix,
  type RoleUpdateRequest,
  SCOPE_ERROR_MESSAGE,
  type ScopeUpdateRequest,
  type TenantUser,
  type TenantUserScope,
  type UserRole,
} from "@/lib/usuarios/contract";

type Outcome =
  { kind: "saved"; message: string } | { kind: "error"; message: string };

const ROLES = Object.keys(ROLE_LABEL) as UserRole[];

function Feedback({ outcome }: { outcome: Outcome | null }) {
  if (outcome?.kind === "error") {
    return <Alert>{outcome.message}</Alert>;
  }

  return outcome?.kind === "saved" ? (
    <p role="status" className="text-good text-sm font-medium">
      {outcome.message}
    </p>
  ) : null;
}

/**
 * Os domínios sensíveis do papel, como a matriz do banco os declara.
 *
 * ⛔ Nada aqui sabe que papel enxerga o quê: a lista vem de `GET
 * /usuarios/matriz`. Três estados diferentes, e nenhum vira o outro: a matriz
 * não respondeu, o papel não veio nela, o papel veio sem domínio.
 */
function DomainMatrix({
  matrix,
  role,
}: {
  matrix: RoleDomainMatrix | null;
  role: UserRole;
}) {
  const entry = matrix?.roles.find((candidate) => candidate.role === role);

  return (
    <section
      aria-label={`Domínios sensíveis de ${roleLabel(role)}`}
      aria-live="polite"
      className="border-line-subtle bg-muted/40 flex flex-col gap-2 rounded-[12px] border p-4"
    >
      <h3 className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
        O que {roleLabel(role)} enxerga
      </h3>
      {!matrix ? (
        <p className="text-alert text-sm text-pretty">
          A matriz de domínios não pôde ser lida agora. Recarregue a página
          antes de conceder um papel.
        </p>
      ) : !entry ? (
        <p className="text-alert text-sm text-pretty">
          A matriz não trouxe este papel. Recarregue a página antes de
          concedê-lo.
        </p>
      ) : entry.domains.length === 0 ? (
        <p className="text-ink text-sm">nenhum domínio sensível</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {entry.domains.map((domain) => {
            const label = domainLabel(domain);

            return (
              <li key={domain} className="text-ink text-sm">
                <strong>{label.title}</strong>
                {label.detail ? ` — ${label.detail}` : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const roleSchema = z.object({
  role: z.enum(ROLES as [UserRole, ...UserRole[]]),
});

type RoleValues = z.input<typeof roleSchema>;

/**
 * Papel e a matriz ao lado. O seletor muda a matriz antes de salvar: quem
 * concede vê o que concede no momento de conceder (§6).
 *
 * Só o owner muda papel. Para os outros o seletor fica desabilitado e explica
 * por quê — e a rota recusa do mesmo jeito (`not_owner`).
 */
function RoleSection({
  user,
  matrix,
  callerIsOwner,
  onSaved,
}: {
  user: TenantUser;
  matrix: RoleDomainMatrix | null;
  callerIsOwner: boolean;
  onSaved: (user: TenantUser) => void;
}) {
  const idPrefix = useId();
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const { register, handleSubmit, control, reset, formState } =
    useForm<RoleValues>({
      resolver: zodResolver(roleSchema),
      defaultValues: { role: user.role },
    });
  const selected = useWatch({ control, name: "role" });
  const editable = callerIsOwner && user.active;

  const onSubmit = handleSubmit(async ({ role }) => {
    setOutcome(null);
    const body: RoleUpdateRequest = { role };

    try {
      const saved = await requestApiAsUser<TenantUser>(
        `/usuarios/${encodeURIComponent(user.user_id)}/papel`,
        { method: "PUT", body },
      );
      setOutcome({
        kind: "saved",
        message: `Papel salvo: ${roleLabel(saved.role)}.`,
      });
      reset({ role: saved.role });
      onSaved(saved);
    } catch (caught) {
      setOutcome({
        kind: "error",
        message: refusalMessage(
          caught,
          ROLE_ERROR_MESSAGE,
          "Não consegui salvar o papel agora. Tente de novo.",
        ),
      });
    }
  });

  const selectId = `${idPrefix}role`;
  const hintId = `${idPrefix}role-hint`;

  return (
    <Card>
      <CardHeader eyebrow="Papel" title="Papel e domínios sensíveis" />
      <form
        onSubmit={onSubmit}
        noValidate
        aria-label="Papel"
        className="grid gap-5 px-5 py-5 md:grid-cols-2"
      >
        <div className="flex flex-col gap-3">
          <label
            htmlFor={selectId}
            className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase"
          >
            Papel
          </label>
          <select
            id={selectId}
            disabled={!editable}
            aria-describedby={hintId}
            className="bg-control border-control-line text-ink h-10 rounded-[10px] border px-3 text-base disabled:cursor-not-allowed disabled:opacity-70"
            {...register("role")}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {roleLabel(role)}
              </option>
            ))}
          </select>
          <p id={hintId} className="text-ink-muted text-sm text-pretty">
            {!user.active
              ? "Usuário desativado: o papel fica como estava."
              : callerIsOwner
                ? "A matriz ao lado muda conforme o papel escolhido, antes de salvar."
                : "Só o owner muda o papel de alguém. Você vê o papel e o que ele concede, sem poder alterá-lo."}
          </p>
          {editable ? (
            <div>
              <Button
                type="submit"
                disabled={
                  formState.isSubmitting || !matrix || selected === user.role
                }
              >
                {formState.isSubmitting ? "Salvando…" : "Salvar papel"}
              </Button>
            </div>
          ) : null}
          <Feedback outcome={outcome} />
        </div>
        <DomainMatrix matrix={matrix} role={selected} />
      </form>
    </Card>
  );
}

function ScopeList({ scope }: { scope: TenantUserScope[] }) {
  if (scope.length === 0) {
    return <p className="text-ink-faint text-sm">nenhuma unidade</p>;
  }

  return (
    <ul className="text-ink flex flex-col gap-0.5 text-sm">
      {scope.map((entry) => (
        <li key={`${entry.company_id}:${entry.unit_id ?? ""}`}>
          {entry.unit_name
            ? `${entry.company_name} · ${entry.unit_name}`
            : `${entry.company_name} · todas as unidades`}
        </li>
      ))}
    </ul>
  );
}

const scopeSchema = z.object({
  // ⛔ Sem estado vazio válido: zero entrada não submete.
  scope: z
    .array(z.string())
    .min(1, "Escolha pelo menos uma empresa ou unidade."),
});

type ScopeValues = z.input<typeof scopeSchema>;

/** O escopo salvo como as chaves do seletor: empresa inteira ou unidade. */
function keysOf(scope: TenantUserScope[]): string[] {
  return scope.map((entry) =>
    entry.unit_id ? `unit:${entry.unit_id}` : `company:${entry.company_id}`,
  );
}

/**
 * O editor de escopo, com o mesmo seletor do convite. Uma linha salva que o
 * seletor não oferece (unidade inativa, empresa sem unidade ativa) sairia ao
 * salvar — a tela diz quais, em vez de apagá-las calada.
 */
function ScopeEditor({
  user,
  units,
  onSaved,
}: {
  user: TenantUser;
  units: UnitOption[];
  onSaved: (user: TenantUser) => void;
}) {
  const idPrefix = useId();
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const { handleSubmit, control, reset, formState } = useForm<ScopeValues>({
    resolver: zodResolver(scopeSchema),
    defaultValues: { scope: keysOf(user.scope) },
  });
  const { field, fieldState } = useController({ control, name: "scope" });

  const offered = new Set([
    ...units.map((unit) => `unit:${unit.unitId}`),
    ...units.map((unit) => `company:${unit.companyId}`),
  ]);
  const lost = user.scope.filter((entry) => !offered.has(keysOf([entry])[0]));

  const onSubmit = handleSubmit(async ({ scope }) => {
    setOutcome(null);
    const body: ScopeUpdateRequest = { scope: scopeEntries(scope, units) };

    try {
      const saved = await requestApiAsUser<TenantUser>(
        `/usuarios/${encodeURIComponent(user.user_id)}/escopo`,
        { method: "PUT", body },
      );
      setOutcome({ kind: "saved", message: "Escopo salvo." });
      reset({ scope: keysOf(saved.scope) });
      onSaved(saved);
    } catch (caught) {
      setOutcome({
        kind: "error",
        message: refusalMessage(
          caught,
          SCOPE_ERROR_MESSAGE,
          "Não consegui salvar o escopo agora. Tente de novo.",
        ),
      });
    }
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Editar escopo"
      className="flex flex-col gap-4"
    >
      <ScopePicker
        units={units}
        value={field.value}
        onChange={field.onChange}
        error={fieldState.error?.message}
        errorId={`${idPrefix}scope-error`}
      />
      {lost.length > 0 ? (
        <div role="note" className="text-alert text-sm text-pretty">
          <p>
            Estas linhas do escopo atual não estão entre as unidades ativas e
            sairão do escopo ao salvar:
          </p>
          <ScopeList scope={lost} />
        </div>
      ) : null}
      <Feedback outcome={outcome} />
      <div>
        <Button
          type="submit"
          disabled={formState.isSubmitting || !hasCompanies(units)}
        >
          {formState.isSubmitting ? "Salvando…" : "Salvar escopo"}
        </Button>
      </div>
    </form>
  );
}

/**
 * ⛔ §3.2: para `owner`, `executive`, `hr` e `personnel` o atalho de
 * `util.can_see_*` responde antes da linha de escopo — a tela diz a frase do
 * papel e nunca lista `scope`, nem oferece editá-lo.
 */
function ScopeSection({
  user,
  units,
  onSaved,
}: {
  user: TenantUser;
  units: UnitOption[] | null;
  onSaved: (user: TenantUser) => void;
}) {
  return (
    <Card>
      <CardHeader eyebrow="Escopo" title="Unidades que a pessoa enxerga" />
      <div className="flex flex-col gap-4 px-5 py-5">
        {user.scope_mode === "by_role" ? (
          <>
            <p className="text-ink text-sm font-bold">{BY_ROLE_SCOPE_LABEL}</p>
            <p className="text-ink-muted text-sm text-pretty">
              {roleLabel(user.role)} enxerga todas as unidades do cliente pelo
              próprio papel, então escopo não se aplica a ele. Para limitar a
              unidades, o owner precisa trocar o papel.
            </p>
          </>
        ) : !user.active ? (
          <>
            <ScopeList scope={user.scope} />
            <p className="text-ink-muted text-sm">
              Usuário desativado: o escopo fica como estava.
            </p>
          </>
        ) : units ? (
          <ScopeEditor user={user} units={units} onSaved={onSaved} />
        ) : (
          <>
            <ScopeList scope={user.scope} />
            <Alert>
              As unidades não puderam ser lidas, então o escopo não pode ser
              editado agora. Recarregue a página para tentar de novo.
            </Alert>
          </>
        )}
      </div>
    </Card>
  );
}

/**
 * Desativar, com confirmação explícita. É definitivo pela tela: reativar é
 * procedimento de operador (SPEC-USUARIOS §8.5). A linha fica — nada é
 * apagado.
 */
function DeactivateSection({
  user,
  onSaved,
}: {
  user: TenantUser;
  onSaved: (user: TenantUser) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const who = user.name ?? user.email ?? "esta pessoa";

  async function confirm() {
    setBusy(true);
    setError(null);

    try {
      const saved = await requestApiAsUser<TenantUser>(
        `/usuarios/${encodeURIComponent(user.user_id)}/desativar`,
        { method: "POST", body: {} },
      );
      setConfirming(false);
      onSaved(saved);
    } catch (caught) {
      setError(
        refusalMessage(
          caught,
          DEACTIVATE_ERROR_MESSAGE,
          "Não consegui desativar agora. Tente de novo.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader eyebrow="Acesso" title="Desativar usuário" />
      <div className="flex flex-col items-start gap-3 px-5 py-5">
        <p className="text-ink-muted text-sm text-pretty">
          A pessoa perde o acesso ao painel na hora. Desativar é definitivo pela
          tela: reativar é procedimento do operador do sistema, fora do painel.
        </p>
        {confirming ? (
          <div
            role="group"
            aria-label={`Confirmar desativação de ${who}`}
            className="flex flex-col gap-2"
          >
            <p className="text-ink text-sm text-pretty">
              Desativar <strong>{who}</strong> definitivamente?
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                onClick={() => void confirm()}
                disabled={busy}
              >
                {busy ? "Desativando…" : "Confirmar desativação"}
              </Button>
              <button
                type="button"
                onClick={() => {
                  setConfirming(false);
                  setError(null);
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
            className="text-bad hover:text-ink text-sm font-bold"
          >
            Desativar usuário
          </button>
        )}
        {error ? <Alert>{error}</Alert> : null}
      </div>
    </Card>
  );
}

/**
 * O detalhe de um usuário: quem é, papel com a matriz, escopo, reenvio do
 * convite e desativação. O estado é o `TenantUser` que a API devolveu por
 * último — cada ação salva troca ele inteiro, e a tela nunca deduz o
 * resultado.
 */
export function UserDetail({
  user: initial,
  matrix,
  units,
  callerIsOwner,
}: {
  user: TenantUser;
  matrix: RoleDomainMatrix | null;
  units: UnitOption[] | null;
  callerIsOwner: boolean;
}) {
  const router = useRouter();
  const [user, setUser] = useState(initial);

  function saved(next: TenantUser) {
    setUser(next);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader eyebrow="Usuário" title={user.name ?? "sem nome"} />
        <dl className="grid gap-4 px-5 py-5 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              E-mail
            </dt>
            <dd className="text-ink mt-1">{user.email ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Status
            </dt>
            <dd className="mt-1">
              <StatusCell user={user} />
            </dd>
          </div>
          <div>
            <dt className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Convidado por
            </dt>
            <dd className="text-ink mt-1">
              {user.invited_by
                ? (user.invited_by.name ?? user.invited_by.email ?? "—")
                : "—"}
            </dd>
          </div>
          {user.active && !user.invitation_accepted ? (
            <div>
              <dt className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
                Convite
              </dt>
              <dd className="mt-1">
                <ResendInvitation user={user} />
              </dd>
            </div>
          ) : null}
        </dl>
        {!user.active ? (
          <p className="text-ink-muted border-line-subtle border-t px-5 py-4 text-sm text-pretty">
            Usuário desativado. Reativar é procedimento do operador do sistema,
            fora do painel.
          </p>
        ) : null}
      </Card>

      <RoleSection
        user={user}
        matrix={matrix}
        callerIsOwner={callerIsOwner}
        onSaved={saved}
      />

      <ScopeSection user={user} units={units} onSaved={saved} />

      {user.active ? <DeactivateSection user={user} onSaved={saved} /> : null}
    </div>
  );
}
