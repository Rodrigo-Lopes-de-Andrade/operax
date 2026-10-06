/** A lista e o convite de usuários do painel (SPEC-USUARIOS §6). */
export const USUARIOS_PATH = "/dashboard/usuarios";

/** O detalhe de um usuário: papel, escopo, matriz e desativação (U4). */
export function userDetailPath(userId: string): string {
  return `${USUARIOS_PATH}/${encodeURIComponent(userId)}`;
}

/**
 * Onde o link do e-mail de convite aterrissa — `INVITE_LANDING_PATH` do
 * backend. Fora do `/dashboard`: quem chega ainda não tem sessão.
 */
export const CONVITE_PATH = "/convite";

/**
 * A marca do fluxo no `redirectTo` da recuperação de senha. O cliente do
 * navegador do `@supabase/ssr` usa PKCE, e o link de recuperação volta como
 * `/convite?code=…` — sem `type`. Sem a marca, a tela não distingue recuperação
 * de convite.
 */
export const FLOW_PARAM = "fluxo";
export const RECOVERY_FLOW = "recuperacao";

/** Para onde o e-mail de "Esqueci minha senha" leva, a partir da origem do painel. */
export function recoveryRedirect(origin: string): string {
  return `${origin}${CONVITE_PATH}?${FLOW_PARAM}=${RECOVERY_FLOW}`;
}

/**
 * `/login?esqueci` abre "Esqueci minha senha" no lugar do formulário de
 * entrada. É um estado do `/login`, não uma rota: ele já abre sem sessão.
 */
export const FORGOT_PASSWORD_PARAM = "esqueci";
