import { describe, expect, it } from "vitest";

import { brandForHost, currentBrand, pageTitle } from "./brand";

/**
 * A marca resolvida pelo HOST é a única que funciona antes da sessão: o login
 * não tem `tenant_id` de onde tirá-la. Estes casos existem porque o dia em que o
 * segundo tenant chegar, é aqui que a tela quebra ou não.
 */
describe("brandForHost", () => {
  it("reconhece o domínio do cliente", () => {
    expect(brandForHost("app.fastparks.com.br").slug).toBe("fastpark");
  });

  it("ignora a porta, que o header carrega em desenvolvimento", () => {
    expect(brandForHost("localhost:3000").slug).toBe("fastpark");
  });

  it("ignora maiúsculas — host é case-insensitive por RFC", () => {
    expect(brandForHost("App.FastParks.com.BR").slug).toBe("fastpark");
  });

  it("aceita subdomínio de um host conhecido", () => {
    // Previews da Vercel chegam como `<hash>-<projeto>.vercel.app`; o que
    // importa é não deixar a tela sem marca por causa de um alias novo.
    expect(brandForHost("preview.app.fastparks.com.br").slug).toBe("fastpark");
  });

  it("cai na primeira marca quando o host é desconhecido", () => {
    // ⚠️ Comportamento deliberado ENQUANTO há um tenant só: host desconhecido
    // hoje é URL de preview ou alias novo, e uma tela de login sem marca seria
    // falha pior que mostrar a do cliente âncora. O dia em que houver um segundo
    // tenant, ESTE teste é o que deve mudar primeiro — e é por isso que ele
    // afirma o fallback em vez de tolerá-lo em silêncio.
    expect(brandForHost("exemplo-desconhecido.com").slug).toBe("fastpark");
  });

  it("não estoura com host ausente", () => {
    // `headers().get("host")` devolve `null` em contextos sem requisição.
    expect(brandForHost(null).slug).toBe("fastpark");
    expect(brandForHost(undefined).slug).toBe("fastpark");
    expect(brandForHost("").slug).toBe("fastpark");
  });

  it("o casamento é por sufixo de PONTO, não por substring", () => {
    // ⚠️ Este caso NÃO consegue provar o que o nome sugeriria hoje. Com uma
    // marca só, `fastparks.com.br.invasor.com` devolve `fastpark` tanto se o
    // casamento falhar (e cair no fallback) quanto se casar errado — os dois
    // caminhos dão o mesmo resultado, e a asserção seria verde nas duas
    // hipóteses. Ela afirma só o que dá para afirmar: a função não estoura e
    // devolve uma marca válida.
    //
    // ⛔ O que fecharia de verdade é uma SEGUNDA marca no registro, e é por isso
    // que este comentário fica: no dia em que ela existir, este é o primeiro
    // teste a reescrever, com o host do segundo tenant do lado esquerdo.
    expect(brandForHost("fastparks.com.br.invasor.com").slug).toBe("fastpark");
  });
});

describe("a marca é do tenant, nunca do fornecedor", () => {
  it("o título carrega o cliente", () => {
    expect(pageTitle("Entrar")).toBe("Entrar · FastPark");
  });

  it("nenhuma superfície diz OperaX", () => {
    expect(currentBrand().name).not.toMatch(/operax/i);
  });
});
