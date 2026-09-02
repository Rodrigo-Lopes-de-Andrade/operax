// Edge Function de diagnóstico da Sprint 0 (docs/sprints/sprint-00-fundacao.md).
//
// Executa o fluxo de autenticação do Secullum (login -> claims -> bancos) e
// uma chamada de teste (`GET /IntegracaoExterna/Horarios`), confirmando que o
// client funciona fim a fim. `Horarios` é usado aqui (em vez de `Empresas`,
// que não é mais chamada por nenhum fluxo deste projeto — `company` é
// derivada de `Funcionario.Empresa` aninhado, ver cadastro-sync.ts) porque
// está na lista definitiva de endpoints do projeto e não retorna PII de
// funcionário, diferente de `/Funcionarios`. Não persiste nada no Supabase —
// é só um teste de conectividade/entregável demonstrável. As sincronizações
// reais de dados cadastrais chegam na Sprint 1.
//
// Como rodar localmente (Supabase CLI + Docker, ver docs/07-supabase.md):
//   supabase functions serve secullum-test-auth --env-file .env --no-verify-jwt
//   curl -s -X POST http://127.0.0.1:54321/functions/v1/secullum-test-auth | jq
//
// Como invocar num projeto já com os secrets configurados (`supabase secrets set`):
//   supabase functions invoke secullum-test-auth
//
// Para rodar só o client (sem subir o runtime completo de Edge Function),
// útil em desenvolvimento local, ver `local-run.ts` neste mesmo diretório:
//   deno run --allow-net --allow-env supabase/functions/secullum-test-auth/local-run.ts

import {
  createSecullumClientFromEnv,
  SecullumHttpError,
  SecullumValidationError,
} from "../_shared/secullum-client.ts";
import { requireSyncSecret } from "../_shared/require-secret.ts";

interface HorarioResumo {
  Id?: number | string;
  Descricao?: string;
  [key: string]: unknown;
}

/** Descreve o erro para a resposta/log, sem nunca incluir token/senha. */
function describeErrorSafely(error: unknown): string {
  if (error instanceof SecullumValidationError) {
    return `Erro de validação do Secullum: ${
      error.errors.map((e) => `${e.Property}: ${e.Message}`).join("; ")
    }`;
  }
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`;
  }
  return "Erro desconhecido.";
}

async function handleRequest(request: Request): Promise<Response> {
  // Diagnóstico também gasta credencial e chamada na origem — o mesmo segredo
  // das duas funções de sincronização vale aqui.
  const recusa = await requireSyncSecret(request, "[secullum-test-auth]");
  if (recusa) return recusa;

  try {
    const client = createSecullumClientFromEnv();
    await client.login();

    const claims = client.getClaims();
    const banks = client.getBanks();

    const horarios = await client.get<HorarioResumo[]>("Horarios");

    const result = {
      ok: true,
      login: {
        email: claims?.email ?? null,
        revendaId: claims?.revendaId ?? null,
      },
      bancosDisponiveis: banks.length,
      bancoSelecionado: client.getSelectedBankId(),
      horarios: {
        total: Array.isArray(horarios) ? horarios.length : 0,
        // Nunca devolver o payload completo (pode conter dados cadastrais) —
        // só uma amostra mínima para confirmar que a chamada funcionou.
        amostra: Array.isArray(horarios)
          ? horarios.slice(0, 1).map((h) => ({ Id: h.Id, Descricao: h.Descricao }))
          : [],
      },
    };

    return new Response(JSON.stringify(result, null, 2), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const status = error instanceof SecullumValidationError
      ? 400
      : error instanceof SecullumHttpError
      ? 502
      : 500;

    // Log estruturado sem token/senha — só a descrição do erro.
    console.error(
      "[secullum-test-auth] Falha no teste de autenticação:",
      describeErrorSafely(error),
    );

    return new Response(
      JSON.stringify({ ok: false, error: describeErrorSafely(error) }, null, 2),
      { status, headers: { "Content-Type": "application/json" } },
    );
  }
}

Deno.serve((request) => handleRequest(request));
