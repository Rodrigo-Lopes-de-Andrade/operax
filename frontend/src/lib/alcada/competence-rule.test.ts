import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * A regra da competência (do dia 21 do mês anterior ao dia 20 do mês) vive em
 * `util.competencia_janela`, no banco, e chega à tela na resposta de
 * `GET /alcada/fila`. Uma cópia dela no front só conseguiria ser comparada
 * consigo mesma — foi por isso que a primeira versão desta tela foi reprovada.
 *
 * O teste procura os dois números como literal isolado no código da tela, fora
 * dos testes. `2026`, `2000` e `2100` não casam (`\b20\b` exige o número
 * sozinho); um `<= 20` ou um `-21` casam.
 */
const SRC = join(__dirname, "..", "..");
const DIRS = [
  "lib/alcada",
  "components/alcada",
  "app/dashboard/justificativas/aprovacao",
  "app/dashboard/justificativas/lancamento",
];

function sources(): string[] {
  return DIRS.flatMap((dir) =>
    readdirSync(join(SRC, dir))
      .filter((name) => /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name))
      .map((name) => join(SRC, dir, name)),
  );
}

describe("a regra 21→20 não mora no front", () => {
  it("há arquivo para vigiar", () => {
    expect(sources().length).toBeGreaterThanOrEqual(9);
  });

  it.each(sources().map((file) => [file.slice(SRC.length + 1), file]))(
    "%s não tem 20 nem 21 como literal",
    (_name, file) => {
      const hits = readFileSync(file, "utf8")
        .split("\n")
        .map((line, index) => ({ line, number: index + 1 }))
        .filter(({ line }) => /\b(20|21)\b/.test(line));

      expect(hits).toEqual([]);
    },
  );
});
