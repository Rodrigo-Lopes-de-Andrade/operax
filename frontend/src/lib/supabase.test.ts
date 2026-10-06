import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createBrowserSupabaseClient,
  createInviteSupabaseClient,
} from "@/lib/supabase";

const createBrowserClient = vi.fn<(...args: unknown[]) => object>(() => ({}));

vi.mock("@supabase/ssr", () => ({
  createBrowserClient: (...args: unknown[]) => createBrowserClient(...args),
}));

vi.mock("@/lib/env", () => ({
  publicEnv: () => ({
    NEXT_PUBLIC_SUPABASE_URL: "https://projeto.supabase.test",
    NEXT_PUBLIC_SUPABASE_ANON_KEY: "anon-key",
    NEXT_PUBLIC_API_URL: "https://api.test",
  }),
}));

/** As chaves de opção do `@supabase/ssr` que mudam onde a sessão é guardada. */
const STORAGE_KEYS = ["cookies", "cookieOptions", "cookieEncoding"] as const;

function optionsOf(call: number): Record<string, unknown> {
  return (createBrowserClient.mock.calls[call][2] ?? {}) as Record<
    string,
    unknown
  >;
}

beforeEach(() => {
  createBrowserClient.mockClear();
});

/**
 * O cliente do `/convite`. O `accept-invite.test.tsx` o substitui inteiro,
 * então as opções dele só são vigiadas aqui — e cada uma tem um motivo:
 * `detectSessionInUrl: true` deixaria o SDK consumir o `?code=` antes da tela
 * (ou recusar o `#access_token` com o PKCE forçado), e o singleton devolveria
 * um cliente criado antes, com a detecção ligada.
 */
describe("createInviteSupabaseClient", () => {
  it("⛔ desliga a detecção automática da URL e não é o singleton", () => {
    createInviteSupabaseClient();

    const options = optionsOf(0);
    expect(options.isSingleton).toBe(false);
    expect(options.auth).toEqual({ detectSessionInUrl: false });
  });

  it("usa o mesmo projeto e os mesmos cookies do cliente do painel", () => {
    createBrowserSupabaseClient();
    createInviteSupabaseClient();

    const [painel, convite] = createBrowserClient.mock.calls;
    expect(convite[0]).toBe(painel[0]);
    expect(convite[1]).toBe(painel[1]);

    // A sessão aberta pelo link precisa cair onde o painel a lê: nenhuma opção
    // de armazenamento diferente da do cliente do painel.
    for (const key of STORAGE_KEYS) {
      expect(optionsOf(1)[key]).toEqual(optionsOf(0)[key]);
    }
  });
});
