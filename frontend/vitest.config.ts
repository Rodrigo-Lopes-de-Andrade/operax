import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // Stubs, not credentials: the suite never reaches a Supabase project.
    //
    // `TZ` nao e stub: e o que da poder de deteccao aos testes de fuso. Sem
    // ele a suite roda no fuso da maquina, e numa maquina em America/Sao_Paulo
    // um formatador que ESQUECESSE o fuso do tenant passaria verde — foi
    // medido em 12/09/2026. UTC e o fuso do Railway e da Vercel, entao a suite
    // passa a rodar onde o produto roda.
    env: {
      TZ: "UTC",
      NEXT_PUBLIC_SUPABASE_URL: "https://stub.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "stub-anon-key",
      NEXT_PUBLIC_API_URL: "http://api.stub.test",
    },
  },
});
