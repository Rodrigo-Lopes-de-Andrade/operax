// Motor da sincronização de fotos — o 6º endpoint do Secullum
// (`GET Funcionarios/fotos?funcionarioId=<Id>`).
//
// POR QUE ELE EXISTE AQUI
// A outra equipe subiu um job `sync-fotos` na Vercel em 02/09/2026, junto das
// seis colunas de foto em `secullum."Funcionario"`. Enquanto ele falar
// PostgREST, tirar `app`/`secullum` dos exposed schemas derruba a
// sincronização — foi o incidente de 27/08. Trazendo o job para cá, com
// conexão direta, a troca de runner fica completa e os exposed schemas voltam
// ao que o CLAUDE.md exige.
//
// ⚠️ O CONTRATO NÃO FOI INVENTADO: ele está escrito nos comentários das colunas
// que a outra equipe criou, e este módulo os segue à risca:
//
//   "Foto"                 bytes JÁ DECODIFICADOS, sem o prefixo da data URI
//   foto_hash              sha256 hex dos BYTES DECODIFICADOS, nunca do base64
//   foto_mime              prefixo da data URI é a fonte; magic number confere
//   foto_sincronizada_em   só em SUCESSO — e "não tem foto" é sucesso
//   foto_tentativa_em      SEMPRE, com ou sem sucesso; é o que ordena a fila
//
// 🔴 `"Foto"` é a coluna mais restrita do schema: nunca em view exposta, nunca
// em log, nunca em relatório. Nada aqui loga bytes, e os avisos referenciam
// funcionário por id.

/** O que o motor exige do client do Secullum. */
export interface FotoReader {
  get<T>(path: string, query?: Record<string, string | undefined>): Promise<T>;
}

/** Uma linha da fila: quem ainda precisa (ou pode precisar) de foto. */
export interface FotoPendente {
  /** `secullum."Funcionario".id` — a chave da escrita. */
  id: string;
  /** `FuncionarioId` do Secullum — é com ele que a origem é chamada. */
  secullumFuncionarioId: number;
  /** O hash já gravado, para pular o UPDATE do binário quando nada mudou. */
  fotoHash: string | null;
}

/** O desfecho de um funcionário, do jeito que o repositório o grava. */
export interface FotoResultado {
  id: string;
  /** `null` = a origem confirmou que não há foto. Continua sendo sucesso. */
  bytes: Uint8Array | null;
  hash: string | null;
  mime: string | null;
}

export interface FotoSyncRepository {
  /** A fila: `"PossuiFoto"`, mais velho primeiro (`foto_tentativa_em` nulls first). */
  listQueue(limit: number): Promise<FotoPendente[]>;
  /** Sucesso: grava o binário (quando mudou) e carimba as DUAS datas. */
  storePhoto(resultado: FotoResultado, gravarBinario: boolean): Promise<void>;
  /** Falha: carimba SÓ `foto_tentativa_em`. Erro nunca apaga dado real. */
  touchAttempt(id: string): Promise<void>;
}

export interface FotoSyncWarning {
  code: string;
  message: string;
}

export interface FotoSyncLogger {
  warn(message: string): void;
  info(message: string): void;
}

export const consoleFotoSyncLogger: FotoSyncLogger = {
  warn: (m) => console.warn(`[sync-fotos] ${m}`),
  info: (m) => console.info(`[sync-fotos] ${m}`),
};

export interface FotoSyncSummary {
  /** Quantos entraram na fila desta passada. */
  queued: number;
  /** Fotos efetivamente gravadas (binário novo). */
  stored: number;
  /** Já estavam iguais: hash bateu, binário não foi reescrito. */
  unchanged: number;
  /** A origem confirmou que o funcionário não tem foto — sucesso, não falha. */
  absent: number;
  /** Erros por funcionário. Não derrubam a passada. */
  failed: number;
  warnings: FotoSyncWarning[];
}

/** Teto de avisos do mesmo código mantidos no resumo — mesma disciplina do cadastro. */
const WARNING_SAMPLE_CAP = 20;

/** Quantos funcionários por passada, quando a invocação não disser. */
export const FOTOS_BATCH_DEFAULT = 25;

/**
 * Extrai bytes e mime de um payload do 6º endpoint.
 *
 * A origem devolve uma data URI (`data:image/jpeg;base64,...`) — é o que o
 * comentário de `foto_mime` registra, confirmado por payload real em
 * 31/08/2026. O que NÃO está registrado é em que chave ela vem, e inventar um
 * nome seria afirmar sobre a origem uma coisa que ninguém conferiu. Então:
 * string solta serve, e dentro de objeto vale o primeiro valor string que se
 * pareça com data URI ou base64. Não achando, o aviso nomeia as CHAVES vistas —
 * nunca os valores, que podem ser a imagem.
 */
export function extrairFoto(
  bruto: unknown,
): { base64: string; mimeDeclarado: string | null } | null {
  const candidatos: string[] = [];
  if (typeof bruto === "string") candidatos.push(bruto);
  else if (bruto && typeof bruto === "object") {
    for (const v of Object.values(bruto as Record<string, unknown>)) {
      if (typeof v === "string") candidatos.push(v);
    }
  }
  for (const c of candidatos) {
    const limpo = c.trim();
    if (!limpo) continue;
    const dataUri = /^data:([^;,]+)?(?:;[^,]*)?,(.*)$/s.exec(limpo);
    if (dataUri) return { base64: dataUri[2], mimeDeclarado: dataUri[1] || null };
    // Base64 puro, sem prefixo: aceito porque a origem pode devolver os dois, e
    // o mime então sai só do magic number.
    if (limpo.length > 64 && /^[A-Za-z0-9+/\r\n]+={0,2}$/.test(limpo)) {
      return { base64: limpo, mimeDeclarado: null };
    }
  }
  return null;
}

/** As chaves de um payload, para o aviso poder dizer o que veio sem citar valor. */
export function chavesDe(bruto: unknown): string {
  if (bruto === null || bruto === undefined) return "(vazio)";
  if (typeof bruto === "string") return "(string)";
  if (Array.isArray(bruto)) return `(array de ${bruto.length})`;
  if (typeof bruto === "object") return Object.keys(bruto as object).join(", ") || "(objeto vazio)";
  return `(${typeof bruto})`;
}

/** Decodifica base64 em bytes. Devolve `null` quando não é base64 válido. */
export function decodificarBase64(base64: string): Uint8Array | null {
  try {
    const bin = atob(base64.replace(/\s+/g, ""));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  } catch {
    return null;
  }
}

/**
 * O mime pelo *magic number* dos bytes.
 *
 * Serve de CONFERÊNCIA, não de fonte: quando diverge do declarado na data URI,
 * vence o conteúdo real — é o que o comentário de `foto_mime` manda. ⛔ Nunca
 * inferir por nome de arquivo, nunca assumir JPEG por padrão.
 */
export function mimePorConteudo(bytes: Uint8Array): string | null {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "image/jpeg";
  }
  if (
    bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 &&
    bytes[2] === 0x4e && bytes[3] === 0x47
  ) {
    return "image/png";
  }
  return null;
}

/** sha256 em hex dos BYTES — nunca da string base64. */
export async function hashDosBytes(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function runFotoSync(
  secullum: FotoReader,
  repo: FotoSyncRepository,
  logger: FotoSyncLogger = consoleFotoSyncLogger,
  limit: number = FOTOS_BATCH_DEFAULT,
): Promise<FotoSyncSummary> {
  const summary: FotoSyncSummary = {
    queued: 0,
    stored: 0,
    unchanged: 0,
    absent: 0,
    failed: 0,
    warnings: [],
  };
  const contagem = new Map<string, number>();
  const warn = (code: string, message: string) => {
    const n = (contagem.get(code) ?? 0) + 1;
    contagem.set(code, n);
    if (n > WARNING_SAMPLE_CAP) return;
    summary.warnings.push({ code, message });
    logger.warn(message);
  };

  const fila = await repo.listQueue(limit);
  summary.queued = fila.length;
  if (!fila.length) {
    logger.info("fila vazia: ninguém com PossuiFoto aguardando.");
    return summary;
  }

  for (const pendente of fila) {
    try {
      const bruto = await secullum.get<unknown>("Funcionarios/fotos", {
        funcionarioId: String(pendente.secullumFuncionarioId),
      });

      const extraido = extrairFoto(bruto);
      if (!extraido) {
        // Ausência CONFIRMADA pela origem é sucesso — o comentário de
        // `foto_sincronizada_em` diz isso com todas as letras.
        summary.absent++;
        await repo.storePhoto({ id: pendente.id, bytes: null, hash: null, mime: null }, false);
        if (bruto !== null && bruto !== undefined && bruto !== "") {
          warn(
            "foto_payload_sem_imagem",
            `Funcionario id=${pendente.id}: resposta sem data URI reconhecível — chaves: ${
              chavesDe(bruto)
            }. Tratado como "sem foto".`,
          );
        }
        continue;
      }

      const bytes = decodificarBase64(extraido.base64);
      if (!bytes || bytes.length === 0) {
        summary.failed++;
        await repo.touchAttempt(pendente.id);
        warn(
          "foto_base64_invalido",
          `Funcionario id=${pendente.id}: conteúdo não decodificou como base64.`,
        );
        continue;
      }

      const doConteudo = mimePorConteudo(bytes);
      if (doConteudo && extraido.mimeDeclarado && doConteudo !== extraido.mimeDeclarado) {
        warn(
          "foto_mime_divergente",
          `Funcionario id=${pendente.id}: data URI declara ${extraido.mimeDeclarado} e os ` +
            `bytes são ${doConteudo} — vence o conteúdo real.`,
        );
      }
      const mime = doConteudo ?? extraido.mimeDeclarado;

      const hash = await hashDosBytes(bytes);
      const mudou = hash !== pendente.fotoHash;
      await repo.storePhoto({ id: pendente.id, bytes, hash, mime }, mudou);
      if (mudou) summary.stored++;
      else summary.unchanged++;
    } catch (erro) {
      // Um funcionário que falha não derruba a passada: a fila é ordenada por
      // `foto_tentativa_em`, então carimbar a tentativa é o que impede ele de
      // travar a cabeça da fila para sempre.
      summary.failed++;
      const mensagem = erro instanceof Error ? erro.message : "erro desconhecido";
      warn("foto_falha_na_origem", `Funcionario id=${pendente.id}: ${mensagem}`);
      try {
        await repo.touchAttempt(pendente.id);
      } catch (segundo) {
        logger.warn(`Funcionario id=${pendente.id}: falha também ao carimbar a tentativa.`);
        throw segundo;
      }
    }
  }

  for (const [code, n] of contagem) {
    if (n <= WARNING_SAMPLE_CAP) continue;
    summary.warnings.push({
      code: `${code}_suppressed_count`,
      message: `Aviso "${code}" ocorreu ${n} vez(es); exibidas as primeiras ${WARNING_SAMPLE_CAP}.`,
    });
  }
  return summary;
}
