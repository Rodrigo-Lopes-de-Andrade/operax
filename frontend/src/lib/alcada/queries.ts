import "server-only";

import type { PostingList } from "@/lib/alcada/posting";
import type { ApprovalQueueResponse } from "@/lib/alcada/review";
import { approvalQuery, type ApprovalFilters } from "@/lib/alcada/url";
import { ApiError, requestApi } from "@/lib/api";
import { loadUnits, type UnitOption } from "@/lib/ponto/queries";
import { getServerSupabase } from "@/lib/supabase-server";

type AlcadaRead<T> =
  | { status: "ok"; queue: T }
  | { status: "forbidden" }
  /** 422: o recorte da URL não é um que a API aceite. */
  | { status: "invalid" }
  | { status: "unavailable" };

export type ApprovalQueueResult = AlcadaRead<ApprovalQueueResponse>;

export type PostingListResult = AlcadaRead<PostingList>;

export type PostingScreen = {
  list: PostingListResult;
  units: UnitOption[];
};

export type ApprovalScreen = {
  queue: ApprovalQueueResult;
  units: UnitOption[];
};

/**
 * A fila vem do FastAPI (Caminho 2): nome, texto e autor são dado individual.
 * As unidades do seletor vêm de `vw_unit` (Caminho 1), como em toda tela do
 * painel — agregado não sensível, recortado pela RLS.
 *
 * 403 é recusa deliberada (`not_hr`) e vira "sem acesso"; 422 é o recorte que
 * a API não aceita, e vira "recorte inválido" com o caminho para limpá-lo; 401,
 * rede e API fora do ar viram "não pôde ser lida". Nenhum dos dois vira fila vazia: "nada para
 * aprovar" dito sobre uma leitura que não aconteceu é o falso verde desta tela.
 */
export async function loadApprovalScreen(
  filters: ApprovalFilters,
): Promise<ApprovalScreen> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token ?? null;

  const [queue, units] = await Promise.all([
    readAlcada<ApprovalQueueResponse>("/alcada/fila", filters, token),
    loadUnits(supabase),
  ]);

  return { queue, units };
}

/**
 * A lista do lançamento no Secullum: o mesmo caminho, o mesmo recorte e as
 * mesmas três falhas da fila — e nenhuma delas vira "nada a lançar", que é o
 * falso verde mais caro desta área.
 */
export async function loadPostingScreen(
  filters: ApprovalFilters,
): Promise<PostingScreen> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token ?? null;

  const [list, units] = await Promise.all([
    readAlcada<PostingList>("/alcada/lancamento", filters, token),
    loadUnits(supabase),
  ]);

  return { list, units };
}

async function readAlcada<T>(
  path: string,
  filters: ApprovalFilters,
  token: string | null,
): Promise<AlcadaRead<T>> {
  if (!token) {
    return { status: "unavailable" };
  }

  try {
    const query = approvalQuery(filters);
    const queue = await requestApi<T>(query ? `${path}?${query}` : path, {
      accessToken: token,
    });

    return { status: "ok", queue };
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return { status: "forbidden" };
    }

    if (error instanceof ApiError && error.status === 422) {
      return { status: "invalid" };
    }

    return { status: "unavailable" };
  }
}
