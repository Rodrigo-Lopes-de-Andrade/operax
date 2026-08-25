import { publicEnv } from "@/lib/env";
import { createBrowserSupabaseClient } from "@/lib/supabase";

/**
 * A non-2xx answer from FastAPI. `detail` carries the message the API sent in
 * its standard `{"detail": …}` body when there is one; the caller decides what
 * the user reads, so no user-facing copy is built here.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, detail: string | null) {
    super(`FastAPI responded with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type ApiRequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
};

type AuthenticatedApiRequestOptions = ApiRequestOptions & {
  accessToken: string;
};

/**
 * Caminho 2 do contrato — individual data, sensitive data or writes go to
 * FastAPI, never straight to Supabase. The Supabase access token travels in
 * `Authorization: Bearer`; the backend validates it against the project JWKS
 * and re-checks tenant, role and sensitive domain before answering.
 */
export async function requestApi<T>(
  path: string,
  options: AuthenticatedApiRequestOptions,
): Promise<T> {
  const { method = "GET", body, signal, accessToken } = options;

  const response = await fetch(`${publicEnv().NEXT_PUBLIC_API_URL}${path}`, {
    method,
    signal,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // Check the status before touching the body: 401, 403 and 429 arrive as the
  // standard FastAPI JSON, and reading a body that was never a payload hides
  // the real failure.
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }

  return (await response.json()) as T;
}

/**
 * Same request, taking the token from the session of the signed-in browser.
 * A missing session surfaces as 401, exactly like the backend would answer.
 */
export async function requestApiAsUser<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const supabase = createBrowserSupabaseClient();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    throw new ApiError(401, null);
  }

  return requestApi<T>(path, { ...options, accessToken });
}

export async function readDetail(response: Response): Promise<string | null> {
  try {
    const payload: unknown = await response.json();

    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as { detail: unknown }).detail;

      if (typeof detail === "string") {
        return detail;
      }
    }
  } catch {
    // Not every error answer is JSON — a proxy timeout is plain text.
  }

  return null;
}

/**
 * Um envio de arquivo, com a mesma sessão das demais chamadas.
 *
 * `Content-Type` fica de fora de propósito: quem monta o boundary do multipart é
 * o navegador, e declará-lo à mão produz um corpo que o servidor não consegue
 * separar.
 */
export async function uploadApiAsUser<T>(
  path: string,
  form: FormData,
): Promise<T> {
  const supabase = createBrowserSupabaseClient();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    throw new ApiError(401, null);
  }

  const response = await fetch(`${publicEnv().NEXT_PUBLIC_API_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: form,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }

  return (await response.json()) as T;
}

/**
 * Um download autenticado. O `.xlsx` do template é dado individual, então não
 * pode sair por um link direto: ele viaja pelo mesmo `Authorization` das outras
 * chamadas, e o arquivo chega como blob para o navegador salvar.
 */
export async function downloadApiAsUser(
  path: string,
  fallbackName: string,
): Promise<{ blob: Blob; filename: string }> {
  const supabase = createBrowserSupabaseClient();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    throw new ApiError(401, null);
  }

  const response = await fetch(`${publicEnv().NEXT_PUBLIC_API_URL}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }

  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);

  return { blob: await response.blob(), filename: match?.[1] ?? fallbackName };
}
