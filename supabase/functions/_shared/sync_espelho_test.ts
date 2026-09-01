// Os dois ciclos de sincronização contra o ESPELHO REAL — o ensaio que nunca
// existiu.
//
// O outro teste daqui (`batida-sync_test.ts`) usa repositório falso e diz isso
// no cabeçalho: "nada toca rede nem banco". Era a única cobertura das Edge
// Functions, e por isso duas coisas passaram verdes sendo impossíveis em
// produção: a `sync-cadastro` gravando `departamento_id` numa `"Estrutura"` que
// perdeu a coluna em 21/08/2026, e a 11b arrastando gatilhos que só produção
// tem. Ver docs/RUNBOOK-JANELA-CONVERGENCIA.md §3b.
//
// Este teste fecha essa lacuna pelo caminho curto: **`column does not exist` é
// erro de parse (42703), levantado antes de qualquer checagem de constraint.**
// Então um ciclo que atravessa as escritas sem 42703/42P01 já prova que todas
// elas são dizíveis contra o schema que produção tem — que é exatamente a
// classe de falha que bloqueou a troca do runner.
//
// A origem é falsa e o banco é real: o Secullum não tem sandbox para este
// cliente, e inventar a resposta dele é a única forma de exercitar a escrita
// sem tocar dado de gente. O alvo é `supabase/fixtures/espelho_secullum.sql`
// aplicado pelo `scripts/testar_migrations.sh`.
//
// São dois ciclos, na ordem em que a realidade os põe: cadastro cria o
// funcionário, batidas se correlaciona a ele. Juntos atravessam as 17 tabelas
// do espelho que os repositórios escrevem, mais `app.batida_marcacao` e os dois
// diários de evento.
//
//   DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \
//     deno test --allow-net --allow-env --no-check _shared/sync_espelho_test.ts
//
// Sem `DATABASE_URL` ele é ignorado, para que `deno task test` siga rodando
// offline.

import { assert, assertEquals } from "jsr:@std/assert@1";

import { runCadastroSync, type SecullumReader } from "./cadastro-sync.ts";
import { SupabaseSyncRepository } from "./supabase-cadastro-repository.ts";
import { runBatidaSync } from "./batida-sync.ts";
import { SupabaseBatidaRepository } from "./supabase-batida-repository.ts";

const TEM_BANCO = Boolean(Deno.env.get("DATABASE_URL"));

/** O dia que os dois ciclos assumem — a carga é montada em cima dele. */
const HOJE = "2026-09-01";

/** Erros que denunciam divergência entre o código e o espelho. */
const DIVERGENCIA_DE_SCHEMA: Record<string, string> = {
  "42703": "coluna inexistente",
  "42P01": "tabela inexistente",
  "42883": "função inexistente",
  "42704": "objeto inexistente",
};

/**
 * Um sufixo por execução.
 *
 * A sincronização é idempotente: numa segunda passada nada é "novo" e os
 * contadores voltam zerados — comportamento certo do produto, e que tornaria
 * a asserção "escreveu 1 empresa" falsa fora de um banco recém-criado. Com
 * identificadores próprios, toda execução é uma primeira execução.
 */
const SEQ = Date.now() % 100_000;

/**
 * A origem, respondendo o mínimo que o parser aceita.
 *
 * Um funcionário só, com todos os nós aninhados preenchidos — é o que faz o
 * ciclo atravessar `"Empresa"`, `"Cidade"`, `"Funcao"`, `"Departamento"`,
 * `"Estrutura"`, `"Funcionario"` e `"FuncionarioCentroCusto"` numa passada.
 */
const FUNCIONARIO = {
  Id: 900_000 + SEQ,
  Nome: "Ensaio do Espelho",
  EmpresaId: 800_000 + SEQ,
  DepartamentoId: 700_000 + SEQ,
  HorarioId: 600_000 + SEQ,
  EstruturaId: 500_000 + SEQ,
  Cpf: "00000000191",
  NumeroPis: "00000000000",
  Admissao: "2024-01-15",
  Demissao: null,
  Email: `ensaio-${SEQ}@exemplo.invalido`,
  Empresa: {
    Id: 800_000 + SEQ,
    Nome: "Empresa do Ensaio",
    Documento: `${String(SEQ).padStart(14, "0")}`,
    Desativada: false,
    Cidade: { Id: 400_000 + SEQ, Descricao: "Cidade do Ensaio" },
  },
  Departamento: { Id: 700_000 + SEQ, Descricao: `Unidade do Ensaio ${SEQ}` },
  Estrutura: { Id: 500_000 + SEQ, Descricao: `Gestor do Ensaio ${SEQ}`, EstruturaPaiId: 0 },
  Funcao: { Id: 300_000 + SEQ, Descricao: `Função do Ensaio ${SEQ}` },
  Cidade: { Id: 400_000 + SEQ, Descricao: "Cidade do Ensaio" },
  Horario: { Id: 600_000 + SEQ },
  ListaCentroDeCustos: [{ Descricao: `Centro de Custo do Ensaio ${SEQ}` }],
};

/** Uma escala de semana fixa: um dia útil de 8 h e o resto folga. */
const HORARIO = {
  Id: 600_000 + SEQ,
  Numero: SEQ,
  Descricao: `Escala do Ensaio ${SEQ}`,
  Dias: [
    { Id: 200_000 + SEQ, DiaSemana: 1, Carga: 480, Entrada1: "08:00", Saida1: "12:00" },
    { Id: 100_000 + SEQ, DiaSemana: 0, Carga: 0 },
  ],
};

/**
 * Roda o ciclo e traduz erro de schema em falha que diz o que aconteceu.
 *
 * Violação de constraint (23502 not-null, 23503 FK) NÃO é falha aqui: quer
 * dizer que o Postgres já parseou a instrução, que é exatamente o que se quer
 * provar. O que reprova é o schema não ter o objeto.
 */
async function semDivergencia<T>(ciclo: () => Promise<T>): Promise<T> {
  try {
    return await ciclo();
  } catch (erro) {
    const codigo = (erro as { code?: string }).code ?? "";
    const nome = DIVERGENCIA_DE_SCHEMA[codigo];
    if (nome) {
      throw new Error(
        `DIVERGÊNCIA CONTRA O ESPELHO (${codigo} — ${nome}): ${(erro as Error).message}\n\n` +
          `O código escreve algo que o schema de produção não tem. Foi assim que a ` +
          `troca do runner ficou bloqueada em 31/08.`,
      );
    }
    throw erro;
  }
}

function origemFalsa(): SecullumReader {
  const respostas: Record<string, unknown> = {
    Funcionarios: [FUNCIONARIO],
    Horarios: [HORARIO],
    FuncionariosAfastamentos: [],
  };
  return {
    get<T>(path: string): Promise<T> {
      if (!(path in respostas)) {
        throw new Error(`rota não prevista no ensaio: ${path}`);
      }
      return Promise.resolve(respostas[path] as T);
    },
  };
}

Deno.test({
  name: "um ciclo de cadastro atravessa o espelho de produção sem divergência de schema",
  ignore: !TEM_BANCO,
  // O driver mantém o socket vivo entre chamadas; o teste não vaza, o pool é
  // que é de módulo. Fechá-lo aqui quebraria uma segunda execução no mesmo
  // processo, e é por isso que o arquivo tem um teste só.
  sanitizeResources: false,
  sanitizeOps: false,
  async fn() {
    const repo = new SupabaseSyncRepository();
    const silencioso = { info() {}, warn() {}, error() {} };

    const resumo = await semDivergencia(() =>
      runCadastroSync(origemFalsa(), repo, silencioso, () => HOJE)
    );

    // Se chegou aqui, toda escrita do ciclo foi aceita pelo espelho. As
    // contagens provam que ele de fato escreveu, em vez de sair cedo por um
    // caminho vazio que não exercitaria nada.
    assertEquals(resumo.companiesUpserted, 1, "a empresa não foi escrita");
    assertEquals(resumo.unitsUpserted, 1, "o departamento não foi escrito");
    assertEquals(resumo.managersUpserted, 1, "a estrutura (gestor) não foi escrita");
    assertEquals(resumo.employeesUpserted, 1, "o funcionário não foi escrito");
    assertEquals(resumo.employeesSkipped, 0, "o funcionário do ensaio foi descartado pelo parser");
    assertEquals(resumo.schedulesUpserted, 1, "o horário não foi escrito");
    assert(resumo.scheduleDaysUpserted > 0, "nenhum dia de escala foi escrito");
    assert(resumo.citiesUpserted > 0, "a cidade não foi escrita");
    assert(resumo.functionsUpserted > 0, "a função não foi escrita");
    // A vigência de gestor é a escrita mais nova, e a única que passa por uma
    // RPC da outra equipe — `secullum.departamento_gestor_transition`. O
    // funcionário do ensaio é o único ativo da unidade dele e aponta para uma
    // "Estrutura" só, então é o caso inequívoco: uma transição, sem fechar
    // nada.
    assertEquals(
      resumo.departmentManagerTransitions,
      1,
      "a vigência de gestor não foi gravada — a RPC do espelho não foi exercitada",
    );
  },
});

/**
 * Um registro-dia de `/Batidas` para o funcionário que o ciclo acima criou.
 *
 * `FonteDadosEntrada1` existe para o ciclo atravessar
 * `secullum."BatidaFonteDados"` — sem ele a tabela ficaria de fora e o ensaio
 * não diria nada sobre ela.
 */
const BATIDA = {
  Id: 950_000 + SEQ,
  FuncionarioId: 900_000 + SEQ,
  Data: `${HOJE}T00:00:00`,
  Entrada1: "08:00",
  Saida1: "12:00",
  FonteDadosEntrada1: {
    Nsr: String(SEQ),
    Hora: "08:00",
    Data: `${HOJE}T00:00:00`,
    DataInclusao: `${HOJE}T00:00:00`,
    Tipo: 0,
    Origem: 1,
  },
};

function origemFalsaBatidas(): SecullumReader {
  return {
    get<T>(path: string): Promise<T> {
      if (path !== "Batidas") throw new Error(`rota não prevista no ensaio: ${path}`);
      return Promise.resolve([BATIDA] as T);
    },
  };
}

Deno.test({
  // Depende do teste acima, e a dependência é a real: batida se correlaciona a
  // `secullum."Funcionario"` por `FuncionarioId`, e quem cria o funcionário é o
  // ciclo de cadastro. Rodar batidas sozinho só provaria o descarte por
  // funcionário ausente. Deno roda os testes de um arquivo em ordem.
  name: "um ciclo de batidas atravessa o espelho de produção sem divergência de schema",
  ignore: !TEM_BANCO,
  sanitizeResources: false,
  sanitizeOps: false,
  async fn() {
    const repo = new SupabaseBatidaRepository();
    const silencioso = { info() {}, warn() {}, error() {} };

    const resumo = await semDivergencia(() =>
      runBatidaSync(origemFalsaBatidas(), repo, silencioso, () => HOJE)
    );

    assertEquals(resumo.batidasFetched, 1, "a origem falsa não foi lida");
    assertEquals(
      resumo.batidasSkippedMissingFuncionario,
      0,
      "a batida não correlacionou com o funcionário do ciclo de cadastro",
    );
    assertEquals(resumo.batidasUpserted, 1, 'a "Batida" não foi escrita');
    assert(resumo.marcacoesUpserted > 0, "nenhuma marcação foi escrita");
    assert(resumo.fonteDadosInserted > 0, "a fonte de dados da marcação não foi escrita");
  },
});
