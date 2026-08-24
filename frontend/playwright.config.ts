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
  // Two, and measured rather than picked. The whole suite renders against a
  // single `next dev` process, which compiles and renders serially: at four
  // workers the run took 1m12s and three navigations timed out waiting on the
  // dev server, at two it takes 48s and passes. More workers here make the run
  // slower, not faster — the parallelism is on the wrong side of the wire.
  //
  // FastAPI is not what gives: eight concurrent individual-consultation calls
  // answer in 230ms. Raising this is worth revisiting only against a production
  // build, which is also where the 3-second acceptance target is measured.
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
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
    },
  ],
});
