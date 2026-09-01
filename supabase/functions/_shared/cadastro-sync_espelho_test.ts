// O ciclo de cadastro contra o ESPELHO REAL — o ensaio que nunca existiu.
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
//   DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \
//     deno test --allow-net --allow-env --no-check _shared/cadastro-sync_espelho_test.ts
//
// Sem `DATABASE_URL` ele é ignorado, para que `deno task test` siga rodando
// offline.

import { assert, assertEquals } from "jsr:@std/assert@1";

import { runCadastroSync, type SecullumReader } from "./cadastro-sync.ts";
import { SupabaseSyncRepository } from "./supabase-cadastro-repository.ts";

const TEM_BANCO = Boolean(Deno.env.get("DATABASE_URL"));

/** Erros que denunciam divergência entre o código e o espelho. */
const DIVERGENCIA_DE_SCHEMA: Record<string, string> = {
  "42703": "coluna inexistente",
  "42P01": "tabela inexistente",
  "42883": "função inexistente",
  "42704": "objeto inexistente",
};

/**
 * A origem, respondendo o mínimo que o parser aceita.
 *
 * Um funcionário só, com todos os nós aninhados preenchidos — é o que faz o
 * ciclo atravessar `"Empresa"`, `"Cidade"`, `"Funcao"`, `"Departamento"`,
 * `"Estrutura"`, `"Funcionario"` e `"FuncionarioCentroCusto"` numa passada.
 */
const FUNCIONARIO = {
  Id: 990001,
  Nome: "Ensaio do Espelho",
  EmpresaId: 9001,
  DepartamentoId: 9101,
  HorarioId: 9201,
  EstruturaId: 9301,
  Cpf: "00000000191",
  NumeroPis: "00000000000",
  Admissao: "2024-01-15",
  Demissao: null,
  Email: "ensaio@exemplo.invalido",
  Empresa: {
    Id: 9001,
    Nome: "Empresa do Ensaio",
    Documento: "00000000000191",
    Desativada: false,
    Cidade: { Id: 9401, Descricao: "Cidade do Ensaio" },
  },
  Departamento: { Id: 9101, Descricao: "Unidade do Ensaio" },
  Estrutura: { Id: 9301, Descricao: "Gestor do Ensaio", EstruturaPaiId: 0 },
  Funcao: { Id: 9501, Descricao: "Função do Ensaio" },
  Cidade: { Id: 9401, Descricao: "Cidade do Ensaio" },
  Horario: { Id: 9201 },
  ListaCentroDeCustos: [{ Descricao: "Centro de Custo do Ensaio" }],
};

/** Uma escala de semana fixa: um dia útil de 8 h e o resto folga. */
const HORARIO = {
  Id: 9201,
  Numero: 1,
  Descricao: "Escala do Ensaio",
  Dias: [
    { Id: 9210, DiaSemana: 1, Carga: 480, Entrada1: "08:00", Saida1: "12:00" },
    { Id: 9211, DiaSemana: 0, Carga: 0 },
  ],
};

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

    let resumo;
    try {
      resumo = await runCadastroSync(origemFalsa(), repo, silencioso, () => "2026-09-01");
    } catch (erro) {
      const codigo = (erro as { code?: string }).code ?? "";
      const nome = DIVERGENCIA_DE_SCHEMA[codigo];
      if (nome) {
        throw new Error(
          `DIVERGÊNCIA CONTRA O ESPELHO (${codigo} — ${nome}): ${
            (erro as Error).message
          }\n\nO código escreve algo que o schema de produção não tem. ` +
            `Foi assim que a troca do runner ficou bloqueada em 31/08.`,
        );
      }
      throw erro;
    }

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
  },
});
