// `app.sync_run` — o diário de execução da sincronização.
//
// Mora fora dos dois repositórios porque as duas Edge Functions gravam a MESMA
// linha pela MESMA busca de integração — e essa busca já tem uma cópia
// declarada fora daqui, de propósito: a guarda de
// `scripts/janela_integracao_secullum.sql` a repete palavra por palavra, porque
// conferir por outro caminho provaria outra coisa. Duas cópias são a
// conferência; uma terceira seria a que sai de sincronia sem ninguém notar.

import type { Sql } from "./postgres-client.ts";

/** As duas palavras que o schema já usa em `app.detection_run.scope` (migration 13). */
export type SyncScope = "incremental" | "backfill";

/** Uma linha de `app.sync_run`, do jeito que a Edge Function a monta. */
export interface SyncRunRecord {
  entity: string;
  scope: SyncScope;
  startedAt: string;
  finishedAt: string;
  status: "completed" | "failed";
  recordsRead: number;
  recordsWritten: number;
  recordsSkipped: number;
  error: string | null;
}

/**
 * Grava o resultado da execução em `app.sync_run`.
 *
 * É o que transforma "o pg_cron entregou o POST" em "a sincronização
 * funcionou". O agendador registra sucesso por ter feito a chamada HTTP, e um
 * 500 e um 200 são indistinguíveis do lado dele — então o sinal verdadeiro
 * tem de ficar numa linha de banco que alguém consegue consultar depois.
 *
 * Falha aqui **não derruba a ingestão**: dado gravado vale mais que telemetria
 * gravada, e um erro ao registrar não pode desfazer o que já entrou. Mas ele é
 * logado alto, porque uma execução sem rastro é exatamente o que o deadman de
 * frescor procura.
 */
export async function writeSyncRun(
  sql: Sql,
  logPrefix: string,
  record: SyncRunRecord,
): Promise<void> {
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
        "execução não registrada em app.sync_run, e o deadman de frescor não a verá.",
    );
    return;
  }
  const { id: integrationId, tenant_id: tenantId } = integration[0];
  await sql`
    insert into app.sync_run (
      tenant_id, integration_id, entity, scope, started_at, finished_at,
      status, records_read, records_written, records_skipped, error
    ) values (
      ${tenantId}, ${integrationId}, ${record.entity}, ${record.scope},
      ${record.startedAt}, ${record.finishedAt}, ${record.status},
      ${record.recordsRead}, ${record.recordsWritten}, ${record.recordsSkipped},
      ${record.error}
    )
  `;
}
