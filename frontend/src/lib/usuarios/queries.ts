import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import { loadUnits, type UnitOption } from "@/lib/ponto/queries";
import { getServerSupabase } from "@/lib/supabase-server";
import type {
  RoleDomainMatrix,
  TenantUser,
  TenantUserList,
} from "@/lib/usuarios/contract";

export type UserListResult =
  | { status: "ok"; list: TenantUserList }
  | { status: "forbidden" }
  | { status: "unavailable" };

export type UsersScreen = {
  list: UserListResult;
  /** Null quando `vw_unit` não respondeu: o convite fica sem seletor, não com um vazio. */
  units: UnitOption[] | null;
};

/**
 * A lista vem do FastAPI (Caminho 2): nome e e-mail vivem em `auth.users`, que
 * não é exposto ao PostgREST. As empresas e unidades do seletor do convite vêm
 * de `vw_unit` (Caminho 1), recortadas pela RLS — o admin enxerga o tenant
 * inteiro pelo papel.
 *
 * 403 vira "sem acesso"; 401, rede e API fora do ar viram "não pôde ser lida".
 * Nenhum dos dois vira lista vazia.
 */
export async function loadUsersScreen(): Promise<UsersScreen> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token ?? null;

  const [list, units] = await Promise.all([
    readList(token),
    loadUnits(supabase).catch(() => null),
  ]);

  return { list, units };
}

async function readList(token: string | null): Promise<UserListResult> {
  if (!token) {
    return { status: "unavailable" };
  }

  try {
    const list = await requestApi<TenantUserList>("/usuarios", {
      accessToken: token,
    });
    return { status: "ok", list };
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return { status: "forbidden" };
    }

    return { status: "unavailable" };
  }
}

export type UserDetailResult =
  | { status: "ok"; user: TenantUser }
  | { status: "not_found" }
  | { status: "forbidden" }
  | { status: "unavailable" };

export type UserDetailScreen = {
  detail: UserDetailResult;
  /** Null quando a matriz não respondeu: a tela diz isso, nunca "nenhum domínio". */
  matrix: RoleDomainMatrix | null;
  units: UnitOption[] | null;
};

/**
 * O detalhe de um usuário. O membro e a matriz vêm do FastAPI (Caminho 2): o
 * nome e o e-mail vivem em `auth.users`, e a matriz é `app.domain_permission`,
 * que não é exposta. As unidades do editor de escopo vêm de `vw_unit`
 * (Caminho 1), como no convite.
 */
export async function loadUserDetailScreen(
  userId: string,
): Promise<UserDetailScreen> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token ?? null;

  const [detail, matrix, units] = await Promise.all([
    readUser(token, userId),
    readMatrix(token),
    loadUnits(supabase).catch(() => null),
  ]);

  return { detail, matrix, units };
}

async function readUser(
  token: string | null,
  userId: string,
): Promise<UserDetailResult> {
  if (!token) {
    return { status: "unavailable" };
  }

  try {
    const user = await requestApi<TenantUser>(
      `/usuarios/${encodeURIComponent(userId)}`,
      { accessToken: token },
    );
    return { status: "ok", user };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { status: "not_found" };
    }

    if (error instanceof ApiError && error.status === 403) {
      return { status: "forbidden" };
    }

    return { status: "unavailable" };
  }
}

async function readMatrix(
  token: string | null,
): Promise<RoleDomainMatrix | null> {
  if (!token) {
    return null;
  }

  try {
    return await requestApi<RoleDomainMatrix>("/usuarios/matriz", {
      accessToken: token,
    });
  } catch {
    return null;
  }
}
