import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { label, META_STATUS_LABEL, PROVIDER_LABEL } from "@/lib/canais/labels";

// A raiz do vitest é `frontend/` — o `include` do config já assume isso — e em
// jsdom `import.meta.url` não é `file:`, então o caminho sai do cwd.
const SRC_DIR = join(process.cwd(), "src");
const LABELS_FILE = join(SRC_DIR, "lib", "canais", "labels.ts");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);

    if (entry.isDirectory()) {
      return sourceFiles(path);
    }

    return /\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)
      ? [path]
      : [];
  });
}

describe("os nomes dos provedores vivem num lugar só", () => {
  it("⛔ o Record tem exatamente os três provedores de WhatsApp — nem um a mais", () => {
    // O par de `WHATSAPP_PROVIDERS` do backend e do índice
    // `integration_whatsapp_unico_ativo`. Um quarto nome aqui sem um quarto
    // nome lá é um rótulo para um canal que a API nunca vai devolver — e o
    // Telegram, quando entrar, entra pelos dois lados no mesmo PR.
    expect(Object.keys(PROVIDER_LABEL).sort()).toEqual([
      "meta_cloud",
      "uazapi",
      "z_api",
    ]);
  });

  it("o rótulo é humano, e o oficial diz de quem é", () => {
    expect(label(PROVIDER_LABEL, "meta_cloud")).toBe(
      "WhatsApp Cloud API (Meta)",
    );
    expect(label(PROVIDER_LABEL, "z_api")).toBe("Z-API");
    expect(label(PROVIDER_LABEL, "uazapi")).toBe("UAZAPI");
  });

  it("provedor que a matriz não conhece aparece cru em vez de sumir", () => {
    // O backend levanta para provedor desconhecido (fail-closed); se um dia
    // deixar passar, a tela mostra o código — feio, e honesto.
    expect(label(PROVIDER_LABEL, "telegram")).toBe("telegram");
  });

  it("⛔ nenhum outro arquivo de `src/` escreve o nome de um provedor", () => {
    // SPEC-CANAIS §1: feature nenhuma pergunta *com quem* falamos. Um
    // `if provider === "meta_cloud"` fora daqui é a diferença entre os canais
    // vazando para um `if` espalhado — exatamente o que o quarto canal
    // encontraria pela frente.
    const offenders = sourceFiles(SRC_DIR).filter(
      (file) =>
        file !== LABELS_FILE &&
        /\b(meta_cloud|z_api|uazapi)\b/.test(readFileSync(file, "utf8")),
    );

    expect(offenders).toEqual([]);
  });

  it("✅ o positivo da varredura: ela enxerga o próprio `labels.ts`", () => {
    // Sem isto, uma varredura que não lesse arquivo nenhum passaria verde.
    const files = sourceFiles(SRC_DIR);

    expect(files).toContain(LABELS_FILE);
    // E o arquivo mais provável de ofender — uma varredura reduzida a
    // `lib/canais/` passaria verde sem nunca olhar o componente.
    expect(files).toContain(
      join(SRC_DIR, "components", "canais", "connections.tsx"),
    );
    expect(readFileSync(LABELS_FILE, "utf8")).toMatch(/meta_cloud/);
  });
});

describe("o estado do template na Meta", () => {
  it("traduz os cinco estados do `check` da migration 14", () => {
    expect(Object.keys(META_STATUS_LABEL).sort()).toEqual([
      "approved",
      "draft",
      "paused",
      "pending",
      "rejected",
    ]);
    expect(label(META_STATUS_LABEL, "pending")).toBe("pendente");
    expect(label(META_STATUS_LABEL, "rejected")).toBe("rejeitado");
  });

  it("estado novo no banco aparece cru", () => {
    expect(label(META_STATUS_LABEL, "disabled")).toBe("disabled");
  });
});
