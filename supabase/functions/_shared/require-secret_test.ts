// A conferência do segredo compartilhado. Nada toca rede nem banco.
//
// Ela é a única coisa entre a anon key — que é pública — e uma sincronização
// real contra a origem, então o que importa aqui não é só "deixa passar quem
// tem": é **recusar em todos os outros caminhos**, inclusive nos dois que
// passariam despercebidos (segredo não configurado, e prefixo certo com
// comprimento errado).

import { assert, assertEquals } from "jsr:@std/assert@1";

import { requireSyncSecret, SYNC_SECRET_HEADER } from "./require-secret.ts";

const SEGREDO = "um-segredo-de-ensaio-com-mais-de-32-chars";

function pedido(headers: Record<string, string> = {}): Request {
  return new Request("https://exemplo.invalido/sync-batidas", { method: "POST", headers });
}

function comSegredo<T>(valor: string | null, corpo: () => Promise<T>): Promise<T> {
  const antes = Deno.env.get("SYNC_SHARED_SECRET");
  if (valor === null) Deno.env.delete("SYNC_SHARED_SECRET");
  else Deno.env.set("SYNC_SHARED_SECRET", valor);
  return corpo().finally(() => {
    if (antes === undefined) Deno.env.delete("SYNC_SHARED_SECRET");
    else Deno.env.set("SYNC_SHARED_SECRET", antes);
  });
}

Deno.test("sem SYNC_SHARED_SECRET configurado, recusa TUDO — e com 503, não 401", async () => {
  await comSegredo(null, async () => {
    // 503 e 401 separam "não configurei" de "mandou errado". Lidos como a mesma
    // coisa às 2h da manhã, custam a rodada inteira de diagnóstico.
    const r = await requireSyncSecret(pedido({ [SYNC_SECRET_HEADER]: SEGREDO }), "[teste]");
    assert(r, "uma invocação passou sem o segredo estar configurado");
    assertEquals(r.status, 503);
  });
});

Deno.test("sem o header, recusa com 401", async () => {
  await comSegredo(SEGREDO, async () => {
    const r = await requireSyncSecret(pedido(), "[teste]");
    assert(r, "uma invocação sem o header passou");
    assertEquals(r.status, 401);
  });
});

Deno.test("com o header errado, recusa com 401", async () => {
  await comSegredo(SEGREDO, async () => {
    const r = await requireSyncSecret(pedido({ [SYNC_SECRET_HEADER]: "outro-valor" }), "[teste]");
    assert(r, "uma invocação com segredo errado passou");
    assertEquals(r.status, 401);
  });
});

Deno.test("o prefixo certo não basta — é o valor inteiro", async () => {
  await comSegredo(SEGREDO, async () => {
    const r = await requireSyncSecret(
      pedido({ [SYNC_SECRET_HEADER]: SEGREDO.slice(0, -1) }),
      "[teste]",
    );
    assert(r, "um segredo truncado num caractere passou");
    assertEquals(r.status, 401);
  });
});

Deno.test("com o segredo certo, deixa passar", async () => {
  await comSegredo(SEGREDO, async () => {
    const r = await requireSyncSecret(pedido({ [SYNC_SECRET_HEADER]: SEGREDO }), "[teste]");
    assertEquals(r, null, "o segredo certo foi recusado");
  });
});

Deno.test("o header não distingue maiúscula de minúscula, como manda o HTTP", async () => {
  await comSegredo(SEGREDO, async () => {
    const r = await requireSyncSecret(pedido({ "X-Sync-Secret": SEGREDO }), "[teste]");
    assertEquals(r, null, "o header em outra caixa foi recusado");
  });
});
