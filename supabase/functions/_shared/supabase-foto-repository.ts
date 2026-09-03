// Persistência da sincronização de fotos — conexão direta, como as outras.
//
// Escreve SÓ as seis colunas de foto de `secullum."Funcionario"`, e nunca o
// resto da linha: o cadastro é dono dos outros campos e reescrevê-los daqui
// desfaria o que a passada de cadastro acabou de gravar.
//
// ⚠️ Conferido em 02/09/2026: `secullum."Funcionario"` não tem trigger nenhum em
// produção — então o UPDATE não dispara `atualizado_em` sozinho, e este módulo
// tampouco o toca. Carimbar `atualizado_em` daqui faria a foto parecer alteração
// de cadastro para quem lê aquela coluna.

import { getSql, type Sql } from "./postgres-client.ts";
import type { FotoPendente, FotoResultado, FotoSyncRepository } from "./foto-sync.ts";

export class SupabaseFotoRepository implements FotoSyncRepository {
  private readonly sql: Sql;

  constructor(sql: Sql = getSql()) {
    this.sql = sql;
  }

  /**
   * A fila, na ordem que o índice `funcionario_foto_fila_idx` serve:
   * `"PossuiFoto"`, mais velho primeiro, nulos na frente.
   *
   * `nulls first` não é detalhe: quem nunca foi tentado tem `foto_tentativa_em`
   * nulo, e sem isso ele ficaria eternamente no fim. E é `foto_tentativa_em`,
   * não `foto_sincronizada_em`, porque um funcionário cuja busca falha sempre
   * travaria a cabeça da fila — está escrito no comentário da coluna.
   */
  async listQueue(limit: number): Promise<FotoPendente[]> {
    const rows = await this.sql<
      { id: string; FuncionarioId: number; foto_hash: string | null }[]
    >`
      select id, "FuncionarioId", foto_hash
        from secullum."Funcionario"
       where "PossuiFoto"
       order by foto_tentativa_em asc nulls first
       limit ${limit}
    `;
    return rows.map((r) => ({
      id: r.id,
      secullumFuncionarioId: r.FuncionarioId,
      fotoHash: r.foto_hash,
    }));
  }

  /**
   * Sucesso. Carimba as DUAS datas; grava o binário só quando ele mudou.
   *
   * `gravarBinario = false` cobre dois casos que são o mesmo para esta tabela:
   * o hash bateu (nada a reescrever) e a origem confirmou que não há foto.
   * ⛔ Nenhum dos dois apaga `"Foto"` — ausência de resposta não é remoção, e
   * quem tira a foto de cena é `"PossuiFoto"` virando falso no cadastro.
   */
  async storePhoto(resultado: FotoResultado, gravarBinario: boolean): Promise<void> {
    if (!gravarBinario) {
      await this.sql`
        update secullum."Funcionario"
           set foto_sincronizada_em = now(),
               foto_tentativa_em    = now()
         where id = ${resultado.id}
      `;
      return;
    }
    await this.sql`
      update secullum."Funcionario"
         set "Foto"               = ${resultado.bytes},
             foto_hash            = ${resultado.hash},
             foto_mime            = ${resultado.mime},
             foto_bytes           = ${resultado.bytes ? resultado.bytes.length : null},
             foto_sincronizada_em = now(),
             foto_tentativa_em    = now()
       where id = ${resultado.id}
    `;
  }

  /** Falha: só a tentativa. Erro nunca apaga nem mascara dado real. */
  async touchAttempt(id: string): Promise<void> {
    await this.sql`
      update secullum."Funcionario"
         set foto_tentativa_em = now()
       where id = ${id}
    `;
  }
}

export function createSupabaseFotoRepositoryFromEnv(): SupabaseFotoRepository {
  return new SupabaseFotoRepository();
}
