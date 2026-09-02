// O segredo compartilhado que fecha o endpoint da sincronização.
//
// POR QUE O GATEWAY NÃO BASTA
// Quem barra uma Edge Function é o `verify_jwt` do gateway, e ele aceita
// **qualquer** JWT do projeto — inclusive a anon key, que é pública por
// desenho: ela vive no bundle do painel. Sem esta conferência, quem abrir o
// DevTools dispara uma sincronização real contra a origem.
//
// ⛔ E não era hipótese. Medido em 02/09/2026: as três funções estavam ACTIVE
// em produção desde 31/08, com `verify_jwt=true`, e portanto invocáveis por
// qualquer um. Ver docs/RUNBOOK-JANELA-CONVERGENCIA.md, passo 4.
//
// POR QUE NÃO SE CONFERE O PAPEL DO JWT
// Seria de graça — o gateway já validou a assinatura, e bastaria ler o claim
// `role` e exigir `service_role`. Mas isso obrigaria a `service_role` a ser
// enviada pelo `pg_cron`, ou seja, a morar no Vault, e a Regra 4 do CLAUDE.md
// diz que ela só vive no backend FastAPI. Um segredo próprio não tem esse
// alcance: quem o rouba dispara sincronização, não lê o banco inteiro.
//
// FALHA FECHADA
// Sem `SYNC_SHARED_SECRET` configurado, tudo é recusado com 503 — e não com
// 401, para que "não configurei" e "mandou errado" não se leiam como a mesma
// coisa às 2h da manhã. Fechar aberto derrotaria o propósito: um secret que
// some devolveria o endpoint ao estado que esta conferência veio corrigir.

/** O header que carrega o segredo. O `pg_cron` o envia — ver scripts/janela_cron_runner.sql. */
export const SYNC_SECRET_HEADER = "x-sync-secret";

/**
 * Devolve `null` quando a chamada está autorizada, ou a `Response` de recusa.
 *
 * A conferência vem ANTES de qualquer trabalho — antes de ler o corpo, de abrir
 * conexão ou de falar com a origem —, porque metade do que ela protege é
 * justamente a carga que uma invocação não autorizada geraria.
 */
export async function requireSyncSecret(
  request: Request,
  logPrefix: string,
): Promise<Response | null> {
  const esperado = Deno.env.get("SYNC_SHARED_SECRET") ?? "";
  if (!esperado) {
    console.error(
      `${logPrefix} SYNC_SHARED_SECRET não configurado — toda invocação será ` +
        "recusada. Configure com `supabase secrets set SYNC_SHARED_SECRET=...`.",
    );
    return recusa(503, "sincronização não configurada");
  }

  const recebido = request.headers.get(SYNC_SECRET_HEADER) ?? "";
  if (!(await digestsIguais(recebido, esperado))) {
    // Sem eco do que veio: um log que repete o valor recebido transforma um
    // erro de configuração de terceiro num segredo de terceiro no nosso log.
    console.warn(`${logPrefix} invocação recusada: ${SYNC_SECRET_HEADER} ausente ou inválido.`);
    return recusa(401, "segredo ausente ou inválido");
  }
  return null;
}

function recusa(status: number, mensagem: string): Response {
  return new Response(JSON.stringify({ ok: false, error: mensagem }, null, 2), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Compara pelos digests, e não pelas strings.
 *
 * Comparar texto sai no primeiro byte diferente: o tempo da resposta vaza o
 * comprimento e o prefixo do segredo, e um endpoint público é exatamente onde
 * isso se explora. Sobre digests de tamanho fixo o laço roda sempre o mesmo
 * número de vezes, e o atacante não controla o prefixo do que está comparando.
 */
async function digestsIguais(a: string, b: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [da, db] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(a)),
    crypto.subtle.digest("SHA-256", enc.encode(b)),
  ]);
  const x = new Uint8Array(da);
  const y = new Uint8Array(db);
  let diferenca = 0;
  for (let i = 0; i < x.length; i++) diferenca |= x[i] ^ y[i];
  return diferenca === 0;
}
