import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const API_PORT = 8101;
// `localhost`, not `127.0.0.1`: the dev server blocks cross-origin
// requests to its own /_next resources, and the two are different origins.
const baseURL = `http://localhost:${PORT}`;
const apiURL = `http://127.0.0.1:${API_PORT}`;

/**
 * Runs outside the `make test` gate (`make e2e`). The webServer environment
 * carries stub values so the suite can start without a Supabase project: the
 * unreachable host makes every session check come back empty, which is exactly
 * the anonymous-visitor path this smoke test asserts. Any test that needs a
 * real session also needs a local Supabase (`supabase start`).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // One, and measured rather than picked — três vezes, com a suíte inteira.
  //
  // A suíte renderiza contra um único processo `next dev`, que compila e
  // renderiza em série. A quatro workers a corrida levava 1m12s e três
  // navegações estouravam; a dois levava 48s e passava — até a suíte crescer com
  // as rotas de RH. Com elas, a dois workers **duas navegações não completam nem
  // em 20 segundos**, sempre em teste diferente: quem perde é quem pediu a rota
  // que o outro worker está fazendo o servidor compilar.
  //
  // E o worker a mais não estava comprando tempo: a um worker a suíte leva
  // 2m02s, o mesmo que a dois. O paralelismo está do lado errado do fio — a fila
  // é do servidor, não do navegador.
  //
  // FastAPI não é o que cede: oito consultas individuais simultâneas respondem
  // em 230ms. Subir isto só faz sentido contra um build de produção, que é onde
  // o orçamento de 3 segundos também é medido.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  // O 5s padrão é para uma página já compilada. Contra `next dev` a primeira
  // visita a cada rota **compila**, e a asserção logo depois de uma navegação
  // paga essa conta. Num build de produção a compilação não existe e o valor
  // volta ao padrão — é lá que o orçamento de 3 segundos é medido, e afrouxá-lo
  // ali esconderia justamente o que `e2e/desempenho.spec.ts` existe para pegar.
  expect: { timeout: process.env.E2E_PROD ? 5_000 : 20_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Front and back, because the individual consultation is Caminho 2: the page
  // is rendered on the Next server, which calls FastAPI, which re-checks role
  // and sensitive domain. Asserting that on the screen needs both processes.
  //
  // The API starts without a database (the pools are lazy) and answers /health,
  // so a run without a local Supabase degrades exactly like the frontend does:
  // the session check comes back empty and the seeded tests skip themselves.
  webServer: [
    {
      // `E2E_PROD=1` swaps the dev server for a production build. The 3-second
      // acceptance target of the dashboard sprint is only meaningful there:
      // `next dev` compiles a route on first request, so measuring against it
      // measures the compiler. e2e/desempenho.spec.ts skips itself without it.
      command: process.env.E2E_PROD
        ? `npm run build && npm run start -- --port ${PORT}`
        : `npm run dev -- --port ${PORT}`,
      // A production build from cold takes ~20s here, past the 60s default only
      // on a slow machine — but the default leaves no room, so it is stated.
      timeout: process.env.E2E_PROD ? 180_000 : 60_000,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      env: {
        NEXT_PUBLIC_SUPABASE_URL:
          process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co",
        NEXT_PUBLIC_SUPABASE_ANON_KEY:
          process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "stub-anon-key",
        NEXT_PUBLIC_API_URL: apiURL,
      },
    },
    {
      command: `uv run uvicorn server.main:app --port ${API_PORT}`,
      cwd: "../backend",
      url: `${apiURL}/health`,
      reuseExistingServer: !process.env.CI,
      env: {
        // A tela de RH escreve do navegador (Caminho 2 com PATCH e POST), e aí
        // a origem do servidor de teste tem de estar na allowlist. Sem isto o
        // `fetch` morre no preflight e a interface mostra a mensagem genérica —
        // que é indistinguível de um bug de produto.
        CORS_ORIGINS: baseURL,
        // O assistente é a única parte do produto que depende de um serviço
        // pago e não determinístico. O que o E2E prova nele é transporte — que o
        // `text/event-stream` atravessa o uvicorn e vira texto na tela — e um
        // modelo de verdade só acrescentaria latência e variação a essa prova.
        // A fronteira (catálogo, domínio, RLS) continua inteira no caminho.
        E2E_FAKE_LLM: "1",
      },
    },
  ],
});
