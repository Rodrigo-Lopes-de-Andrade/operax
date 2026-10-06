import { ApiError } from "@/lib/api";

/**
 * Usuários do painel — o contrato de `backend/server/routers/usuarios.py` e
 * dos modelos `TenantUserList`, `UserInvitation` e `InvitationResent`.
 *
 * Os tipos ficam aqui à mão porque não são tabela: são a resposta de uma rota
 * do FastAPI, que lê `auth.users` com `service_role` (SPEC-USUARIOS §6).
 */

export type UserRole =
  | "owner"
  | "executive"
  | "hr"
  | "personnel"
  | "regional_manager"
  | "unit_supervisor"
  | "operations_manager"
  | "accounting"
  | "viewer";

export type TenantUserScope = {
  company_id: string;
  company_name: string;
  unit_id: string | null;
  unit_name: string | null;
};

export type TenantUser = {
  user_id: string;
  email: string | null;
  name: string | null;
  role: UserRole;
  active: boolean;
  deactivated_at: string | null;
  invitation_accepted: boolean;
  invited_by: {
    user_id: string;
    email: string | null;
    name: string | null;
  } | null;
  /**
   * `by_role`: o papel enxerga o tenant inteiro pelo atalho de
   * `util.can_see_*`, e `scope` não diz nada sobre ele (§3.2).
   */
  scope_mode: "by_role" | "by_scope";
  scope: TenantUserScope[];
};

export type TenantUserList = { users: TenantUser[] };

/** Uma entrada do escopo do convite. Sem `unit_id` = a empresa inteira. */
export type InvitationScopeEntry =
  { company_id: string } | { company_id: string; unit_id: string };

export type UserInvitationRequest = {
  name: string;
  email: string;
  scope: InvitationScopeEntry[];
};

export type UserInvitation = {
  user_id: string;
  email: string;
  role: "viewer";
  invitation_sent: boolean;
};

export type InvitationResent = { user_id: string; email: string };

/**
 * Um domínio sensível de `app.sensitive_domain`. `string`, não união: a matriz
 * vem do banco, e um domínio que nascer lá depois desta tela ainda aparece.
 */
export type SensitiveDomain = string;

/**
 * `GET /usuarios/matriz` — os domínios que cada papel enxerga, lidos de
 * `app.domain_permission`. Papel sem domínio vem com a lista vazia.
 */
export type RoleDomainMatrix = {
  roles: { role: UserRole; domains: SensitiveDomain[] }[];
};

/** `PUT /usuarios/{id}/papel`. */
export type RoleUpdateRequest = { role: UserRole };

/** `PUT /usuarios/{id}/escopo` — a mesma forma do escopo do convite. */
export type ScopeUpdateRequest = { scope: InvitationScopeEntry[] };

/**
 * O que cada domínio deixa ver, em palavras de gestor.
 *
 * ⛔ Isto é RÓTULO, não permissão: quem diz que papel enxerga qual domínio é a
 * matriz vinda do banco. Esta tabela só traduz o nome.
 */
export const DOMAIN_LABEL: Record<string, { title: string; detail: string }> = {
  pii: {
    title: "Dados pessoais",
    detail: "enxerga CPF, RG, endereço, filiação",
  },
  compensation: {
    title: "Remuneração",
    detail: "enxerga salário e demais valores pagos",
  },
  health: {
    title: "Saúde ocupacional",
    detail: "enxerga só aptidão e validade do ASO — nunca diagnóstico",
  },
  disciplinary: {
    title: "Disciplinar",
    detail: "enxerga advertências e suspensões",
  },
  banking: {
    title: "Dados bancários",
    detail: "enxerga banco, agência e conta",
  },
};

export function domainLabel(domain: string): {
  title: string;
  detail: string | null;
} {
  return Object.hasOwn(DOMAIN_LABEL, domain)
    ? DOMAIN_LABEL[domain]
    : { title: `Domínio sensível "${domain}"`, detail: null };
}

export const ROLE_LABEL: Record<UserRole, string> = {
  owner: "Owner",
  executive: "Diretoria",
  hr: "RH",
  personnel: "Departamento pessoal",
  regional_manager: "Gerente regional",
  unit_supervisor: "Supervisor de unidade",
  operations_manager: "Gerente de operações",
  accounting: "Contabilidade",
  viewer: "Consulta",
};

export function roleLabel(role: string): string {
  return Object.hasOwn(ROLE_LABEL, role) ? ROLE_LABEL[role as UserRole] : role;
}

/** ⛔ §3.2: a frase de quem enxerga pelo papel — nunca o conteúdo de `scope`. */
export const BY_ROLE_SCOPE_LABEL = "todas as unidades (pelo papel)";

const SESSION_EXPIRED = "Sua sessão expirou. Entre de novo para continuar.";

const NOT_ADMIN =
  "Só o owner, o RH e o departamento pessoal administram usuários, e a API não reconheceu o seu papel para isso.";

/** As recusas de `POST /usuarios/convites`, pelo código que vem no `detail`. */
export const INVITE_ERROR_MESSAGE: Record<string, string> = {
  not_admin: NOT_ADMIN,
  conta_em_outro_cliente:
    "Esse e-mail já é usado em outro cliente do painel. Use outro e-mail para esta pessoa.",
  ja_e_membro:
    "Esse e-mail já é de um usuário deste cliente — ativo ou desativado. Procure-o na lista; nenhum convite foi enviado.",
  escopo_vazio: "Escolha pelo menos uma empresa ou unidade.",
  escopo_invalido:
    "O escopo escolhido não é válido. Recarregue a página e escolha de novo; nenhum convite foi enviado.",
  escopo_sem_empresa:
    "Toda unidade precisa ir com a empresa dela. Recarregue a página e escolha de novo; nenhum convite foi enviado.",
  empresa_fora_do_tenant:
    "Uma das empresas escolhidas não é deste cliente. Recarregue a página e escolha de novo; nenhum convite foi enviado.",
  unidade_fora_da_empresa:
    "Uma das unidades escolhidas não pertence à empresa dela. Recarregue a página e escolha de novo; nenhum convite foi enviado.",
  convite_nao_enviado:
    "O e-mail de convite não pôde ser enviado agora, e ninguém foi cadastrado. Tente de novo em alguns minutos.",
};

/** As recusas de `POST /usuarios/{id}/reenviar-convite`. */
export const RESEND_ERROR_MESSAGE: Record<string, string> = {
  not_admin: NOT_ADMIN,
  member_not_found:
    "Esse usuário não está mais neste cliente. Recarregue a lista.",
  membro_inativo:
    "Esse usuário está desativado, e convite não é reenviado a quem está desativado.",
  convite_ja_aceito:
    "Essa pessoa já aceitou o convite. Se ela não lembra a senha, pode usar 'Esqueci minha senha' na tela de entrada.",
  convite_nao_enviado:
    "O e-mail de convite não pôde ser reenviado agora. Tente de novo em alguns minutos.",
};

const MEMBER_GONE =
  "Esse usuário não está mais neste cliente. Volte à lista e recarregue.";

/** As recusas de `PUT /usuarios/{id}/papel`. */
export const ROLE_ERROR_MESSAGE: Record<string, string> = {
  not_owner: "Só o owner muda o papel de alguém. Nada foi alterado.",
  member_not_found: MEMBER_GONE,
  ultimo_owner:
    "Esta pessoa é o último owner ativo deste cliente, e o cliente não pode ficar sem owner. Promova outra pessoa a owner antes de mudar este papel.",
};

/** As recusas de `PUT /usuarios/{id}/escopo`. */
export const SCOPE_ERROR_MESSAGE: Record<string, string> = {
  not_admin: NOT_ADMIN,
  member_not_found: MEMBER_GONE,
  escopo_vazio: "Escolha pelo menos uma empresa ou unidade.",
  escopo_invalido:
    "O escopo escolhido não é válido. Recarregue a página e escolha de novo; nada foi alterado.",
  escopo_sem_empresa:
    "Toda unidade precisa ir com a empresa dela. Recarregue a página e escolha de novo; nada foi alterado.",
  empresa_fora_do_tenant:
    "Uma das empresas escolhidas não é deste cliente. Recarregue a página e escolha de novo; nada foi alterado.",
  unidade_fora_da_empresa:
    "Uma das unidades escolhidas não pertence à empresa dela. Recarregue a página e escolha de novo; nada foi alterado.",
};

/** As recusas de `POST /usuarios/{id}/desativar`. */
export const DEACTIVATE_ERROR_MESSAGE: Record<string, string> = {
  not_admin: NOT_ADMIN,
  member_not_found: MEMBER_GONE,
  owner_so_por_owner: "Só um owner desativa outro owner. Nada foi alterado.",
  e_voce_mesmo:
    "Você não pode desativar a própria conta. Peça a outro administrador.",
  ultimo_owner:
    "Esta pessoa é o último owner ativo deste cliente, e o cliente não pode ficar sem owner. Nada foi alterado.",
};

/**
 * A frase de uma recusa: o código do `detail` na tabela, senão o 401, senão a
 * frase padrão. O `detail` cru nunca é mostrado — um código desconhecido
 * cai na padrão, não na tela.
 */
export function refusalMessage(
  caught: unknown,
  table: Record<string, string>,
  fallback: string,
): string {
  if (caught instanceof ApiError) {
    if (caught.detail && Object.hasOwn(table, caught.detail)) {
      return table[caught.detail];
    }

    if (caught.status === 401) {
      return SESSION_EXPIRED;
    }
  }

  return fallback;
}
