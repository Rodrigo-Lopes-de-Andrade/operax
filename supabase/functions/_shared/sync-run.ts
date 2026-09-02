// `app.sync_run` — o diário de execução da sincronização, e o lock dela.
//
// Mora fora dos dois repositórios porque as duas Edge Functions escrevem a
// MESMA linha pela MESMA busca de integração — e essa busca já tem uma cópia
// declarada fora daqui, de propósito: a guarda de
// `scripts/janela_integracao_secullum.sql` a repete palavra por palavra, porque
// conferir por outro caminho provaria outra coisa. Duas cópias são a
// conferência; uma terceira seria a que sai de sincronia sem ninguém notar.
//
// SÃO DUAS ESCRITAS, E NÃO UMA
// `claimSyncRun` grava `running` ANTES de a origem ser lida; `closeSyncRun`
// fecha a mesma linha no fim. Enquanto era uma escrita só, no fim, com status
// terminal, o índice único parcial da migration 34 seria um lock que nunca
// tranca — `app.sync_run.status` tem default `'running'` e o check aceita os
// quatro estados justamente porque o schema previa reivindicar antes.
//
// A ordem também é o que dá sentido ao lock: reivindicar depois de ler a origem
// protegeria o banco e deixaria o Secullum tomar as duas chamadas.

import type { Sql } from "./postgres-client.ts";

/** As duas palavras que o schema já usa em `app.detection_run.scope` (migration 13). */
export type SyncScope = "incremental" | "backfill";

/**
 * Por quanto tempo uma reivindicação segura o lock sem dar sinal de vida.
 *
 * Um lock que não expira transforma um crash em parada permanente: a linha
 * `running` fica, e toda execução seguinte é recusada. Antes de reivindicar,
 * `claimSyncRun` encerra como `failed` o que passou deste tempo.
 *
 * O número é medido, não escolhido: no diário de produção de 02/09/2026, sobre
 * 954 execuções, `sync_batidas` levou 3,5 s em média (máx 27 s) e
 * `sync_cadastro` 7,4 s (máx 31 s). Dez minutos são 20x o pior caso medido e
 * ainda menos que a menor cadência (15 min) — então um `running` abandonado
 * nunca sobrevive para bloquear o ciclo seguinte.
 */
const LEASE_MINUTES = 10;

/** O desfecho de uma execução, do jeito que a Edge Function o conhece. */
export interface SyncRunOutcome {
  status: "completed" | "failed";
  recordsRead: number;
  recordsWritten: number;
  recordsSkipped: number;
  error: string | null;
}

/**
 * O que saiu da reivindicação.
 *
 * `em_andamento` e `sem_integracao` são desfechos diferentes e a diferença
 * decide se a origem é chamada: no primeiro caso outra execução está rodando e
 * esta não deve fazer nada; no segundo não há diário nem lock, e a
 * sincronização segue assim mesmo — dado gravado vale mais que telemetria
 * gravada, e recusar a sincronizar por falta de uma linha de configuração seria
 * parada auto-infligida.
 */
export type SyncRunClaim =
  | { ok: true; id: string }
  | { ok: false; reason: "em_andamento" }
  | { ok: false; reason: "sem_integracao" };

/**
 * Reivindica a execução: grava `running` em `app.sync_run` e devolve o id.
 *
 * Devolve `em_andamento` quando outra execução da mesma entidade já segura o
 * lock — o índice `sync_run_em_andamento_key` (migration 34) é quem decide, e
 * por isso duas invocações simultâneas não conseguem passar as duas, mesmo
 * chegando no mesmo milissegundo.
 */
export async function claimSyncRun(
  sql: Sql,
  logPrefix: string,
  entity: string,
  scope: SyncScope,
): Promise<SyncRunClaim> {
  const integration = await sql<{ id: string; tenant_id: string }[]>`
    select id, tenant_id
    from app.integration
    where provider = 'secullum' and active
    order by created_at
    limit 1
  `;
  if (!integration.length) {
    console.error(
      `${logPrefix} app.integration não tem provedor 'secullum' ativo — ` +
        "execução não registrada em app.sync_run, sem lock de sobreposição, " +
        "e o deadman de frescor não a verá.",
    );
    return { ok: false, reason: "sem_integracao" };
  }
  const { id: integrationId, tenant_id: tenantId } = integration[0];

  // O reaper roda em statement separado de propósito: dentro de uma CTE, o
  // `insert` enxergaria o snapshot anterior ao `update` e o índice ainda veria
  // a linha velha — o lock morto continuaria trancando.
  const abandonadas = await sql`
    update app.sync_run
       set status = 'failed',
           finished_at = now(),
           error = ${`execução abandonada: reivindicada e nunca fechada (lease de ${LEASE_MINUTES} min)`}
     where tenant_id = ${tenantId}
       and entity = ${entity}
       and status = 'running'
       and started_at < now() - make_interval(mins => ${LEASE_MINUTES})
  `;
  if (abandonadas.count > 0) {
    console.error(
      `${logPrefix} ${abandonadas.count} execução(ões) de ${entity} estavam ` +
        `'running' há mais de ${LEASE_MINUTES} min e foram encerradas como 'failed'.`,
    );
  }

  const claimed = await sql<{ id: string }[]>`
    insert into app.sync_run (
      tenant_id, integration_id, entity, scope, started_at, status
    ) values (
      ${tenantId}, ${integrationId}, ${entity}, ${scope}, now(), 'running'
    )
    on conflict (tenant_id, entity) where status = 'running' do nothing
    returning id
  `;
  if (!claimed.length) {
    return { ok: false, reason: "em_andamento" };
  }
  return { ok: true, id: claimed[0].id };
}

/**
 * Fecha a execução reivindicada, com o desfecho dela.
 *
 * É o que transforma "o pg_cron entregou o POST" em "a sincronização
 * funcionou": o agendador registra sucesso por ter feito a chamada HTTP, e um
 * 500 e um 200 são indistinguíveis do lado dele.
 *
 * Falha aqui **não derruba a ingestão**: dado gravado vale mais que telemetria
 * gravada. Mas é logado alto, porque uma execução sem rastro é exatamente o que
 * o deadman de frescor procura.
 *
 * O `where status = 'running'` não é defensivo: se o reaper já tiver declarado
 * esta execução abandonada, a linha não é mais nossa, e sobrescrevê-la apagaria
 * o registro de que alguém rodou por mais tempo que o lease.
 */
export async function closeSyncRun(
  sql: Sql,
  logPrefix: string,
  id: string,
  outcome: SyncRunOutcome,
): Promise<void> {
  const fechadas = await sql`
    update app.sync_run
       set finished_at     = now(),
           status          = ${outcome.status},
           records_read    = ${outcome.recordsRead},
           records_written = ${outcome.recordsWritten},
           records_skipped = ${outcome.recordsSkipped},
           error           = ${outcome.error}
     where id = ${id} and status = 'running'
  `;
  if (fechadas.count === 0) {
    console.error(
      `${logPrefix} a execução ${id} já não estava 'running' ao ser fechada — ` +
        `o reaper a declarou abandonada (lease de ${LEASE_MINUTES} min) com ela ainda viva.`,
    );
  }
}
