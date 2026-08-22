// Client centralizado para a API do Secullum RH (autenticação + webservice de
// Integração Externa). Compatível com Deno (Supabase Edge Functions) — usa
// somente `fetch` nativo, sem dependências Node-only (axios, node-fetch, fs).
// Ver docs/03-integracao-secullum.md para o contrato completo.
//
// Nenhum outro módulo deste projeto deve chamar a API do Secullum diretamente
// com `fetch` — tudo passa por este client (docs/02-arquitetura.md, componente
// "Client Secullum").
//
// ⚠️ Regra de ouro (docs/03-integracao-secullum.md): não há sandbox no
// Secullum deste cliente — toda chamada roda contra produção real. Por isso
// este client expõe SOMENTE leitura (`get`) para o webservice de Integração
// Externa. A única exceção são os `POST` do fluxo de autenticação (`/Token`,
// `/ReinvidicacoesToken`), que não escrevem dado de ponto nenhum. Isso é
// estrutural: a classe `SecullumClient` não declara `post`/`delete` para o
// webservice de integração — um verbo de escrita acidental falha em tempo de
// compilação (o método simplesmente não existe), não em produção.

const AUTH_BASE_URL = "https://autenticador.secullum.com.br";
const INTEGRATION_BASE_URL = "https://pontowebintegracaoexterna.secullum.com.br/IntegracaoExterna";

/** client_id fixo documentado pelo Secullum para o Secullum RH. */
const DEFAULT_CLIENT_ID = "3";

export interface SecullumClientConfig {
  username: string;
  password: string;
  /** client_id do fluxo OAuth password grant. Padrão: "3" (Secullum RH). */
  clientId?: string;
  /**
   * Id do banco (conta) a selecionar quando o usuário tiver acesso a mais de
   * um. Se omitido, o client usa o primeiro banco retornado por
   * `ListarBancos`.
   */
  bankId?: string;
  /** Permite injetar um fetch alternativo (usado nos testes unitários). */
  fetchImpl?: typeof fetch;
  /** Número máximo de tentativas para erros transitórios (5xx/429/rede). */
  maxRetries?: number;
  /** Delay base (ms) do backoff exponencial entre tentativas. */
  retryBaseDelayMs?: number;
}

export interface SecullumBank {
  /** Id tratado (sem "-") — valor enviado no header `secullumidbancoselecionado`. */
  id: string;
  /** Id original retornado pelo Secullum, sem tratamento. */
  rawId: string;
  nome?: string;
  [key: string]: unknown;
}

export interface SecullumTokenClaims {
  email?: string;
  nome?: string;
  revendaId?: string | number;
  [key: string]: unknown;
}

export interface SecullumValidationErrorItem {
  Property: string;
  Message: string;
}

/** Erro estruturado para HTTP 400 do Secullum (corpo `[{Property, Message}]`). */
export class SecullumValidationError extends Error {
  readonly status = 400;
  readonly errors: SecullumValidationErrorItem[];

  constructor(errors: SecullumValidationErrorItem[]) {
    super(
      `Secullum validation error: ${
        errors.map((e) => `${e.Property}: ${e.Message}`).join("; ") ||
        "corpo de erro vazio/inesperado"
      }`,
    );
    this.name = "SecullumValidationError";
    this.errors = errors;
  }
}

/** Falha no fluxo de autenticação/renovação de token. */
export class SecullumAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SecullumAuthError";
  }
}

/** Erro HTTP não tratado especificamente (não é 400 nem 401 renovável). */
export class SecullumHttpError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(status: number, path: string, message: string) {
    super(message);
    this.name = "SecullumHttpError";
    this.status = status;
    this.path = path;
  }
}

/**
 * Limites de requisições documentados por prefixo de rota
 * (docs/03-integracao-secullum.md — ex.: 100 req/hora em `Calcular`).
 * Aplicado apenas como guarda local best-effort: como Edge Functions não
 * garantem estado compartilhado entre invocações, este limitador só protege
 * chamadas feitas dentro da mesma instância "quente"; a defesa real contra
 * estouro de limite é a frequência de agendamento dos Cron Triggers.
 */
const RATE_LIMITS: Record<string, { max: number; windowMs: number }> = {
  Calcular: { max: 100, windowMs: 60 * 60 * 1000 },
};

class LocalRateLimiter {
  private readonly callTimestamps = new Map<string, number[]>();

  constructor(private readonly limits: Record<string, { max: number; windowMs: number }>) {}

  /** Lança `SecullumHttpError` (429) se o limite local já foi atingido. */
  assertWithinLimit(path: string): void {
    const prefix = Object.keys(this.limits).find((p) => path.startsWith(p));
    if (!prefix) return;

    const { max, windowMs } = this.limits[prefix];
    const now = Date.now();
    const recent = (this.callTimestamps.get(prefix) ?? []).filter(
      (timestamp) => now - timestamp < windowMs,
    );

    if (recent.length >= max) {
      const waitMs = windowMs - (now - recent[0]);
      throw new SecullumHttpError(
        429,
        path,
        `Rate limit local excedido para "${prefix}" (${max} req / ${
          Math.round(windowMs / 60000)
        } min). Aguarde ~${Math.ceil(waitMs / 1000)}s antes de tentar novamente.`,
      );
    }

    recent.push(now);
    this.callTimestamps.set(prefix, recent);
  }
}

/** Resume um erro para log, sem nunca incluir token/senha/payload sensível. */
function describeErrorSafely(error: unknown): string {
  if (error instanceof SecullumHttpError) {
    return `${error.name}(status=${error.status}, path=${error.path})`;
  }
  if (error instanceof SecullumValidationError) {
    return `${error.name}(${error.errors.length} propriedade(s) inválida(s))`;
  }
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`;
  }
  return "erro desconhecido";
}

export class SecullumClient {
  private accessToken: string | null = null;
  private selectedBankId: string | null = null;
  private banks: SecullumBank[] = [];
  private claims: SecullumTokenClaims | null = null;

  private readonly fetchImpl: typeof fetch;
  private readonly maxRetries: number;
  private readonly retryBaseDelayMs: number;
  private readonly rateLimiter = new LocalRateLimiter(RATE_LIMITS);

  constructor(private readonly config: SecullumClientConfig) {
    if (!config.username || !config.password) {
      throw new SecullumAuthError(
        "SecullumClient requer username/password (ver SECULLUM_USERNAME/SECULLUM_PASSWORD).",
      );
    }
    this.fetchImpl = config.fetchImpl ?? fetch;
    this.maxRetries = config.maxRetries ?? 3;
    this.retryBaseDelayMs = config.retryBaseDelayMs ?? 300;
  }

  /** Dados do usuário autenticado retornados por `ReinvidicacoesToken`. */
  getClaims(): SecullumTokenClaims | null {
    return this.claims;
  }

  /** Bancos (contas) disponíveis, carregados no login. */
  getBanks(): SecullumBank[] {
    return this.banks;
  }

  getSelectedBankId(): string | null {
    return this.selectedBankId;
  }

  /**
   * Executa o fluxo de 3 passos de autenticação
   * (docs/03-integracao-secullum.md):
   *   1. POST /Token                              -> access_token
   *   2. POST /ReinvidicacoesToken                 -> claims (email, nome, revendaId)
   *   3. GET  /ContasSecullumExterno/ListarBancos   -> bancos disponíveis
   * Seleciona o banco configurado (`config.bankId`) ou o primeiro da lista.
   */
  async login(): Promise<void> {
    const token = await this.requestAccessToken();
    const claims = await this.fetchClaims(token);
    const banks = await this.fetchBanks(token);

    if (banks.length === 0) {
      throw new SecullumAuthError(
        "Login no Secullum concluído, mas nenhum banco (conta) disponível para este usuário.",
      );
    }

    const chosen = this.config.bankId
      ? banks.find((b) => b.id === this.config.bankId || b.rawId === this.config.bankId)
      : banks[0];

    if (!chosen) {
      throw new SecullumAuthError(
        `Banco configurado (SECULLUM_BANK_ID="${this.config.bankId}") não encontrado na lista retornada pelo Secullum.`,
      );
    }

    // Só atualiza o estado interno depois que todo o fluxo teve sucesso.
    this.accessToken = token;
    this.claims = claims;
    this.banks = banks;
    this.selectedBankId = chosen.id;
  }

  private async requestAccessToken(): Promise<string> {
    const body = new URLSearchParams({
      grant_type: "password",
      username: this.config.username,
      password: this.config.password,
      client_id: this.config.clientId ?? DEFAULT_CLIENT_ID,
    });

    let response: Response;
    try {
      response = await this.fetchImpl(`${AUTH_BASE_URL}/Token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
    } catch {
      // Nunca incluir `body` (contém a senha) na mensagem de erro/log.
      throw new SecullumAuthError("Falha de rede ao chamar POST /Token do Secullum.");
    }

    if (!response.ok) {
      throw new SecullumAuthError(`Falha ao autenticar no Secullum (HTTP ${response.status}).`);
    }

    const data = (await response.json()) as { access_token?: string };
    if (!data.access_token) {
      throw new SecullumAuthError("Resposta de POST /Token sem access_token.");
    }
    return data.access_token;
  }

  private async fetchClaims(token: string): Promise<SecullumTokenClaims> {
    const response = await this.fetchImpl(`${AUTH_BASE_URL}/ReinvidicacoesToken`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ token }),
    });

    if (!response.ok) {
      throw new SecullumAuthError(
        `Falha ao obter claims do token no Secullum (HTTP ${response.status}).`,
      );
    }

    return (await response.json()) as SecullumTokenClaims;
  }

  private async fetchBanks(token: string): Promise<SecullumBank[]> {
    const response = await this.fetchImpl(`${AUTH_BASE_URL}/ContasSecullumExterno/ListarBancos`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      throw new SecullumAuthError(`Falha ao listar bancos no Secullum (HTTP ${response.status}).`);
    }

    const raw = (await response.json()) as Array<Record<string, unknown>>;
    return raw.map((item) => {
      const rawId = String(item.Id ?? item.id ?? "");
      // O id do banco pode vir com "-" (docs/03-integracao-secullum.md) —
      // removido antes de usar no header `secullumidbancoselecionado`.
      const id = rawId.replace(/-/g, "");
      return { ...item, rawId, id } as SecullumBank;
    });
  }

  private async ensureAuthenticated(): Promise<void> {
    if (!this.accessToken || !this.selectedBankId) {
      await this.login();
    }
  }

  /**
   * Única operação exposta para o webservice de Integração Externa
   * (`GET IntegracaoExterna/<path>`). Propositalmente não existe `post`/
   * `delete` aqui — ver regra de ouro no topo deste arquivo.
   *
   * Trata automaticamente:
   *  - 401: reautentica uma vez (novo login) e repete a chamada original.
   *  - 400: lança `SecullumValidationError` com a lista `[{Property, Message}]`.
   *  - 5xx/429/erro de rede: retry com backoff exponencial (até `maxRetries`).
   */
  async get<T>(path: string, query?: Record<string, string | undefined>): Promise<T> {
    await this.ensureAuthenticated();
    this.rateLimiter.assertWithinLimit(path);

    const url = this.buildUrl(path, query);
    return await this.executeWithRetries<T>(url, path);
  }

  private buildUrl(path: string, query?: Record<string, string | undefined>): string {
    const url = new URL(`${INTEGRATION_BASE_URL}/${path}`);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined) url.searchParams.set(key, value);
      }
    }
    return url.toString();
  }

  private async executeWithRetries<T>(
    url: string,
    path: string,
    isReauthRetry = false,
  ): Promise<T> {
    let attempt = 0;
    let lastNetworkError: unknown;

    while (attempt < this.maxRetries) {
      attempt++;

      let response: Response;
      try {
        response = await this.fetchImpl(url, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${this.accessToken}`,
            secullumidbancoselecionado: this.selectedBankId ?? "",
          },
        });
      } catch (networkError) {
        lastNetworkError = networkError;
        if (attempt >= this.maxRetries) break;
        console.warn(
          `[secullum-client] Erro de rede em GET ${path}, tentativa ${attempt}/${this.maxRetries}.`,
        );
        await this.delay(this.retryBaseDelayMs * 2 ** (attempt - 1));
        continue;
      }

      if (response.status === 401) {
        if (isReauthRetry) {
          throw new SecullumAuthError(
            "Reautenticação automática falhou: token continua inválido após novo login.",
          );
        }
        // Renovação automática de token (docs/03-integracao-secullum.md):
        // refaz o login uma vez e repete a chamada original.
        this.accessToken = null;
        this.selectedBankId = null;
        await this.login();
        return await this.executeWithRetries<T>(url, path, true);
      }

      if (response.status === 400) {
        const body = (await response.json().catch(() => [])) as SecullumValidationErrorItem[];
        throw new SecullumValidationError(Array.isArray(body) ? body : []);
      }

      if (!response.ok) {
        const isTransient = response.status >= 500 || response.status === 429;
        if (isTransient && attempt < this.maxRetries) {
          console.warn(
            `[secullum-client] HTTP ${response.status} transitório em GET ${path}, tentativa ${attempt}/${this.maxRetries}.`,
          );
          await this.delay(this.retryBaseDelayMs * 2 ** (attempt - 1));
          continue;
        }
        throw new SecullumHttpError(
          response.status,
          path,
          `Secullum retornou HTTP ${response.status} em GET ${path}.`,
        );
      }

      return (await response.json()) as T;
    }

    const error = new SecullumHttpError(
      0,
      path,
      `Falha de rede ao chamar GET ${path} após ${attempt} tentativa(s).`,
    );
    console.error(
      `[secullum-client] ${describeErrorSafely(error)}`,
      describeErrorSafely(lastNetworkError),
    );
    throw error;
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

/**
 * Cria um `SecullumClient` lendo credenciais das variáveis de ambiente
 * padrão do projeto (`SECULLUM_USERNAME`, `SECULLUM_PASSWORD`,
 * `SECULLUM_CLIENT_ID`, `SECULLUM_BANK_ID` opcional). Uso esperado nas Edge
 * Functions (secrets injetados pelo próprio Supabase).
 */
export function createSecullumClientFromEnv(
  overrides: Partial<SecullumClientConfig> = {},
): SecullumClient {
  return new SecullumClient({
    username: Deno.env.get("SECULLUM_USERNAME") ?? "",
    password: Deno.env.get("SECULLUM_PASSWORD") ?? "",
    clientId: Deno.env.get("SECULLUM_CLIENT_ID") ?? DEFAULT_CLIENT_ID,
    bankId: Deno.env.get("SECULLUM_BANK_ID") ?? undefined,
    ...overrides,
  });
}
