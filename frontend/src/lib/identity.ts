import "server-only";

import { cache } from "react";

import { ApiError, requestApi } from "@/lib/api";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Who the backend says the caller is. `/me` is the only place the panel learns
 * a role, and it learns it from the backend, never from a claim it could read
 * itself: the role lives in `app.tenant_member` and FastAPI resolves it from the
 * validated token.
 *
 * The role decides **navigation** and nothing else. What a screen may show is
 * decided by RLS and by the backend on every read — a role that reaches the
 * Colaboradores tab still sees only the domains and the units its permissions
 * allow, and a role that does not reach the tab is refused by the API even if it
 * types the URL.
 */
export type Identity = {
  user_id: string;
  email: string | null;
  tenant_id: string;
  role: string;
};

/**
 * The roles the HR area is offered to. `owner`, `hr` and `personnel` are the
 * three `util.is_admin` accepts — they read and write. `executive` reads and
 * does not write, which is why the edit button is decided by `can_write` from
 * the API and not by this list.
 */
export const HR_ROLES = ["owner", "hr", "personnel", "executive"] as const;

export function reachesHr(role: string | undefined): boolean {
  return (HR_ROLES as readonly string[]).includes(role ?? "");
}

/**
 * Os três papéis que `util.is_admin` aceita — os que escrevem. `executive` está
 * fora, e essa é a diferença entre esta lista e `HR_ROLES`: ele lê a área de RH
 * e não cura nada. Curadoria é escrita, e escrita é `is_admin`.
 */
export const ADMIN_ROLES = ["owner", "hr", "personnel"] as const;

export function isAdmin(role: string | undefined): boolean {
  return (ADMIN_ROLES as readonly string[]).includes(role ?? "");
}

/**
 * Os papéis a quem a tela de Laudos é oferecida — e ela NÃO é uma tela de RH.
 *
 * Laudo é documento da unidade: `public.vw_unit_compliance` recorta por
 * `util.can_see_unit` e a rota não checa domínio sensível, então o supervisor de
 * unidade lê os laudos da unidade dele — persona nomeada no PRD ("gestor de
 * unidade consulta laudos da sua unidade"). Enquanto o item viveu dentro de
 * `reachesHr`, a única porta dele era digitar a URL.
 *
 * ⚠️ O valor é `unit_supervisor`, como o enum `app.user_role` o escreve e como
 * `/me` o devolve. "supervisor" é o nome da persona nas conversas e não existe
 * no banco: uma lista com ele deixaria a porta fechada exatamente para quem ela
 * foi aberta.
 *
 * ⛔ **Esta lista é um PROXY, e o eixo real é outro.** `util.can_see_unit`
 * (migration 04) libera por papel para `{owner, executive, hr, personnel}` **ou**
 * por existir linha em `app.user_scope` — que qualquer papel pode ter. A sidebar
 * não sabe disso: `/me` devolve papel, não escopo. Então os três papéis de
 * operação de unidade entram juntos: deixar `regional_manager` e
 * `operations_manager` de fora repetiria, calado, o mesmo defeito que
 * `unit_supervisor` teve — porta aberta pelo banco e nenhum link para ela.
 *
 * `accounting` e `viewer` ficam fora de propósito, e não por esquecimento: a
 * porta da contabilidade é o Painel de DP, e `viewer` é leitura sem área
 * própria. Os dois têm teste que prende a ausência.
 *
 * ⏳ O dia em que `/me` devolver o escopo resolvido, isto vira a pergunta certa
 * ("esta pessoa alcança alguma unidade?") e a lista some.
 */
export const COMPLIANCE_REPORT_ROLES = [
  ...HR_ROLES,
  "unit_supervisor",
  "regional_manager",
  "operations_manager",
] as const;

export function reachesComplianceReports(role: string | undefined): boolean {
  return (COMPLIANCE_REPORT_ROLES as readonly string[]).includes(role ?? "");
}

/**
 * Cached per request: the shell asks for it, and so does any page that needs to
 * fail closed on a deep link. `cache` makes that one call, not three.
 */
export const loadIdentity = cache(async (): Promise<Identity | null> => {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    return null;
  }

  try {
    return await requestApi<Identity>("/me", { accessToken });
  } catch (error) {
    // A user with no active membership gets 403 here. That is not an outage —
    // it is somebody who has signed in and belongs to no tenant yet, and the
    // shell has to render without an HR section rather than crash.
    if (
      error instanceof ApiError &&
      (error.status === 403 || error.status === 401)
    ) {
      return null;
    }

    throw error;
  }
});
