import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CHANNEL_LABEL,
  CHANNELS,
  label,
  META_STATUS_LABEL,
  PROVIDER_LABEL,
} from "@/lib/canais/labels";

// A raiz do vitest é `frontend/` — o `include` do config já assume isso — e em
// jsdom `import.meta.url` não é `file:`, então o caminho sai do cwd.
const SRC_DIR = join(process.cwd(), "src");
const LABELS_FILE = join(SRC_DIR, "lib", "canais", "labels.ts");

/**
 * Os quatro nomes. Os três de WhatsApp são identificadores que só existem
 * como nome de provedor, e `\b` basta. `telegram` também é canal
 * (`screen.telegram`, `telegram: TelegramChannel | null`), segmento de rota
 * (`/canais/telegram/conectar`, `/webhooks/telegram/`) e nome de arquivo
 * (`telegram-connection`) — por isso ele entra pela regra da SPEC §1.1 ao pé
 * da letra: **como string literal**, entre aspas. É exatamente o que um
 * `if provider === "telegram"` escreveria, e o que o campo, a rota e o
 * import não escrevem.
 */
const PROVIDER_LITERAL = /\b(meta_cloud|z_api|uazapi)\b|["'`]telegram["'`]/;

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
  it("⛔ o Record tem exatamente os quatro provedores — os três de WhatsApp e o Telegram", () => {
    // O par de `CHANNEL_PROVIDERS` do backend: os três do índice
    // `integration_whatsapp_unico_ativo` e o do índice irmão
    // `integration_telegram_unico_ativo`. Um quinto nome aqui sem um quinto
    // nome lá é um rótulo para um canal que a API nunca vai devolver.
    expect(Object.keys(PROVIDER_LABEL).sort()).toEqual([
      "meta_cloud",
      "telegram",
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
    expect(label(PROVIDER_LABEL, "telegram")).toBe("Telegram");
  });

  it("provedor que a matriz não conhece aparece cru em vez de sumir", () => {
    // O backend levanta para provedor desconhecido (fail-closed); se um dia
    // deixar passar, a tela mostra o código — feio, e honesto.
    expect(label(PROVIDER_LABEL, "signal")).toBe("signal");
  });

  it("⛔ nenhum outro arquivo de `src/` escreve o nome de um provedor", () => {
    // SPEC-CANAIS §1: feature nenhuma pergunta *com quem* falamos. Um
    // `if provider === "meta_cloud"` fora daqui é a diferença entre os canais
    // vazando para um `if` espalhado — exatamente o que o quarto canal
    // encontraria pela frente.
    const offenders = sourceFiles(SRC_DIR).filter(
      (file) =>
        file !== LABELS_FILE &&
        PROVIDER_LITERAL.test(readFileSync(file, "utf8")),
    );

    expect(offenders).toEqual([]);
  });

  it("✅ o positivo da varredura: ela enxerga o próprio `labels.ts`", () => {
    // Sem isto, uma varredura que não lesse arquivo nenhum passaria verde.
    const files = sourceFiles(SRC_DIR);

    expect(files).toContain(LABELS_FILE);
    // E os arquivos mais prováveis de ofender — uma varredura reduzida a
    // `lib/canais/` passaria verde sem nunca olhar os componentes.
    expect(files).toContain(
      join(SRC_DIR, "components", "canais", "connections.tsx"),
    );
    expect(files).toContain(
      join(SRC_DIR, "components", "canais", "telegram-connection.tsx"),
    );
    expect(files).toContain(
      join(
        SRC_DIR,
        "app",
        "dashboard",
        "administracao",
        "conexoes",
        "page.tsx",
      ),
    );
    expect(PROVIDER_LITERAL.test(readFileSync(LABELS_FILE, "utf8"))).toBe(true);
  });

  it("✅ o positivo do quarto nome: a varredura casa o literal que um `if` escreveria", () => {
    // Os três de WhatsApp já eram casados; este prende que `telegram` também é
    // — nas três aspas, em comparação, em chave de objeto e em chamada. Até o
    // literal de *canal* cai: todo `telegram` entre aspas sai de `labels.ts`.
    expect(PROVIDER_LITERAL.test('if (provider === "telegram") {')).toBe(true);
    expect(PROVIDER_LITERAL.test("provider: 'telegram',")).toBe(true);
    expect(PROVIDER_LITERAL.test("case `telegram`:")).toBe(true);
    expect(PROVIDER_LITERAL.test('channel === "telegram"')).toBe(true);
    expect(PROVIDER_LITERAL.test('loadCredential("telegram")')).toBe(true);
    expect(PROVIDER_LITERAL.test('provider === "meta_cloud"')).toBe(true);
  });

  it("… e o que não é literal passa: campo, rota e nome de arquivo", () => {
    // O que o `src/` precisa escrever e não é nome de provedor: o campo do
    // contrato, as rotas da API e o import do componente. Nenhum deles é um
    // `if` esperando o quarto canal.
    expect(PROVIDER_LITERAL.test("screen.telegram ?? null")).toBe(false);
    expect(PROVIDER_LITERAL.test("telegram: TelegramChannel | null;")).toBe(
      false,
    );
    expect(PROVIDER_LITERAL.test('"/canais/telegram/conectar"')).toBe(false);
    expect(PROVIDER_LITERAL.test("`${base}/webhooks/telegram/${token}`")).toBe(
      false,
    );
    expect(
      PROVIDER_LITERAL.test('from "@/components/canais/telegram-connection"'),
    ).toBe(false);
    expect(PROVIDER_LITERAL.test('id="channel-telegram"')).toBe(false);
  });
});

describe("os dois canais", () => {
  it("são exatamente dois, nesta ordem, e coexistem — a tela mostra os dois sempre", () => {
    // SPEC §2.1: WhatsApp e Telegram são canais diferentes e devem coexistir.
    // A ordem é a da tela (o que já existe primeiro) e a dos formulários.
    expect(CHANNELS).toEqual(["whatsapp", "telegram"]);
  });

  it("cada canal tem rótulo humano", () => {
    expect(CHANNEL_LABEL.whatsapp).toBe("WhatsApp");
    expect(CHANNEL_LABEL.telegram).toBe("Telegram");
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
