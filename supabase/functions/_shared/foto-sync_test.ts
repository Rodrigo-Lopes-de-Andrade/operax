// O motor de fotos, com origem e repositório falsos. Nada toca rede nem banco.
//
// O que estes testes protegem é o ponto cego do módulo: **o formato do payload
// do 6º endpoint não está documentado neste repositório**. O que se sabe está no
// comentário da coluna `foto_mime`, escrito por quem construiu o job da Vercel —
// que a origem devolve uma data URI. Em que chave ela vem, ninguém conferiu.
// Por isso o parser aceita várias formas e o teste fixa cada uma delas.

import { assert, assertEquals } from "jsr:@std/assert@1";

import {
  chavesDe,
  decodificarBase64,
  extrairFoto,
  type FotoPendente,
  type FotoResultado,
  type FotoSyncRepository,
  hashDosBytes,
  mimePorConteudo,
  runFotoSync,
} from "./foto-sync.ts";

// 1x1 JPEG mínimo o bastante para o magic number valer.
const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46]);
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function base64De(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes));
}

const silencioso = { warn() {}, info() {} };

class RepoFalso implements FotoSyncRepository {
  fila: FotoPendente[] = [];
  readonly guardados: { resultado: FotoResultado; binario: boolean }[] = [];
  readonly tentativas: string[] = [];

  listQueue(limit: number): Promise<FotoPendente[]> {
    return Promise.resolve(this.fila.slice(0, limit));
  }
  storePhoto(resultado: FotoResultado, gravarBinario: boolean): Promise<void> {
    this.guardados.push({ resultado, binario: gravarBinario });
    return Promise.resolve();
  }
  touchAttempt(id: string): Promise<void> {
    this.tentativas.push(id);
    return Promise.resolve();
  }
}

function origem(resposta: unknown | (() => never)) {
  return {
    get<T>(): Promise<T> {
      if (typeof resposta === "function") (resposta as () => never)();
      return Promise.resolve(resposta as T);
    },
  };
}

// ---------------------------------------------------------------------------
// Parsing do payload
// ---------------------------------------------------------------------------
Deno.test("data URI com mime declarado: bytes e mime saem separados", () => {
  const r = extrairFoto(`data:image/jpeg;base64,${base64De(JPEG)}`);
  assert(r, "não reconheceu a data URI");
  assertEquals(r.mimeDeclarado, "image/jpeg");
  assertEquals(decodificarBase64(r.base64), JPEG);
});

Deno.test("data URI dentro de objeto, em chave que ninguém documentou", () => {
  // Inventar o nome da chave seria afirmar sobre a origem uma coisa que ninguém
  // conferiu. O parser varre os valores string, e é isto que este teste fixa.
  const r = extrairFoto({ Id: 7, QualquerNome: `data:image/png;base64,${base64De(PNG)}` });
  assert(r, "não achou a data URI dentro do objeto");
  assertEquals(r.mimeDeclarado, "image/png");
});

Deno.test("base64 puro, sem prefixo, é aceito e o mime fica para o conteúdo", () => {
  const longo = base64De(new Uint8Array([...JPEG, ...new Uint8Array(64).fill(1)]));
  const r = extrairFoto(longo);
  assert(r, "recusou base64 sem prefixo");
  assertEquals(r.mimeDeclarado, null);
});

Deno.test("resposta vazia ou sem imagem não vira foto", () => {
  assertEquals(extrairFoto(null), null);
  assertEquals(extrairFoto(""), null);
  assertEquals(extrairFoto({ Id: 7, Nome: "curto" }), null, "string curta virou foto");
});

Deno.test("as chaves são reportáveis sem citar valor — o valor pode ser a imagem", () => {
  assertEquals(chavesDe({ Id: 1, Foto: "..." }), "Id, Foto");
  assertEquals(chavesDe("qualquer coisa"), "(string)");
  assertEquals(chavesDe(null), "(vazio)");
});

Deno.test("magic number reconhece JPEG e PNG, e não chuta o resto", () => {
  assertEquals(mimePorConteudo(JPEG), "image/jpeg");
  assertEquals(mimePorConteudo(PNG), "image/png");
  assertEquals(mimePorConteudo(new Uint8Array([1, 2, 3, 4])), null, "chutou um mime");
});

Deno.test("o hash é dos BYTES, não da string base64", async () => {
  // Vetor conhecido: sha256("abc").
  const abc = new TextEncoder().encode("abc");
  assertEquals(
    await hashDosBytes(abc),
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  );
});

// ---------------------------------------------------------------------------
// O ciclo
// ---------------------------------------------------------------------------
Deno.test("foto nova é gravada, com o mime do conteúdo", async () => {
  const repo = new RepoFalso();
  repo.fila = [{ id: "u1", secullumFuncionarioId: 10, fotoHash: null }];

  const s = await runFotoSync(
    origem(`data:image/jpeg;base64,${base64De(JPEG)}`),
    repo,
    silencioso,
  );
  assertEquals(s.stored, 1);
  assertEquals(s.unchanged, 0);
  assertEquals(repo.guardados.length, 1);
  assert(repo.guardados[0].binario, "não pediu para gravar o binário de uma foto nova");
  assertEquals(repo.guardados[0].resultado.mime, "image/jpeg");
});

Deno.test("hash igual não reescreve o binário, mas carimba a data", async () => {
  const repo = new RepoFalso();
  const hash = await hashDosBytes(JPEG);
  repo.fila = [{ id: "u1", secullumFuncionarioId: 10, fotoHash: hash }];

  const s = await runFotoSync(origem(`data:image/jpeg;base64,${base64De(JPEG)}`), repo, silencioso);
  assertEquals(s.unchanged, 1);
  assertEquals(s.stored, 0);
  assertEquals(repo.guardados[0].binario, false, "reescreveu binário que não mudou");
});

Deno.test("a origem dizendo que não há foto é SUCESSO, e não apaga nada", async () => {
  const repo = new RepoFalso();
  repo.fila = [{ id: "u1", secullumFuncionarioId: 10, fotoHash: null }];

  const s = await runFotoSync(origem(null), repo, silencioso);
  assertEquals(s.absent, 1);
  assertEquals(s.failed, 0, "ausência confirmada virou falha");
  assertEquals(repo.guardados[0].binario, false, "ausência pediu escrita de binário");
  assertEquals(repo.tentativas.length, 0, "ausência caiu no caminho de falha");
});

Deno.test("falha na origem carimba SÓ a tentativa, e não derruba a passada", async () => {
  const repo = new RepoFalso();
  repo.fila = [
    { id: "u1", secullumFuncionarioId: 10, fotoHash: null },
    { id: "u2", secullumFuncionarioId: 11, fotoHash: null },
  ];
  let primeira = true;
  const origemInstavel = {
    get<T>(): Promise<T> {
      if (primeira) {
        primeira = false;
        throw new Error("503 da origem");
      }
      return Promise.resolve(`data:image/png;base64,${base64De(PNG)}` as T);
    },
  };

  const s = await runFotoSync(origemInstavel, repo, silencioso);
  assertEquals(s.failed, 1);
  assertEquals(s.stored, 1, "a segunda não foi processada depois da falha da primeira");
  assertEquals(repo.tentativas, ["u1"], "não carimbou a tentativa de quem falhou");
  assertEquals(repo.guardados.length, 1, "gravou binário de quem falhou");
});

Deno.test("o lote limita as chamadas à origem", async () => {
  const repo = new RepoFalso();
  repo.fila = Array.from({ length: 10 }, (_, i) => ({
    id: `u${i}`,
    secullumFuncionarioId: i,
    fotoHash: null,
  }));
  const s = await runFotoSync(
    origem(`data:image/png;base64,${base64De(PNG)}`),
    repo,
    silencioso,
    3,
  );
  assertEquals(s.queued, 3, "o limite não foi respeitado");
});
