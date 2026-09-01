// A regra de vigência de gestor — a única parte deste trabalho que foi INFERIDA
// em vez de lida, porque o ADR-013 não está neste repositório.
//
// Por isso ela mora numa função pura e os casos abaixo são, dois deles, os
// departamentos reais de produção medidos em 01/09/2026. Se o ADR aparecer e
// contradisser, é aqui que a contradição fica visível.

import { assertEquals } from "jsr:@std/assert@1";

import {
  decideDepartmentManagerTransitions,
  type ObservacaoGestor,
  type VigenciaGestor,
} from "./cadastro-sync.ts";

const UNIDADE = "11111111-1111-1111-1111-111111111111";
const GESTOR_A = "aaaaaaaa-0000-0000-0000-000000000001";
const GESTOR_B = "bbbbbbbb-0000-0000-0000-000000000002";

function observacao(estruturas: ObservacaoGestor["estruturas"]): ObservacaoGestor {
  return { unitId: UNIDADE, secullumDepartamentoId: 7101, estruturas };
}

const A = { managerId: GESTOR_A, secullumEstruturaId: 2, ativos: 2 };
const B = { managerId: GESTOR_B, secullumEstruturaId: 6, ativos: 1 };

Deno.test("departamento inequívoco e sem vigente ganha a primeira atribuição", () => {
  const t = decideDepartmentManagerTransitions([observacao([A])], []);
  assertEquals(t.length, 1);
  assertEquals(t[0].closeId, null, "primeira linha do departamento não fecha nada");
  assertEquals(t[0].managerId, GESTOR_A);
  assertEquals(t[0].funcionariosObservados, 2, "a contagem é da Estrutura escolhida");
});

Deno.test("departamento ambíguo que nunca foi inequívoco não ganha linha nenhuma", () => {
  // Caso real `192733c0` em 01/09/2026: duas Estruturas (2 e 1 ativos), zero
  // linhas vigentes. Eleger a de 2 seria eleição por maioria, que o comentário
  // de `funcionarios_observados` proíbe.
  assertEquals(decideDepartmentManagerTransitions([observacao([A, B])], []), []);
});

Deno.test("a vigente gruda quando ainda é observada, mesmo com outra ao lado", () => {
  // Caso real `d9b91b52`: a Estrutura vigente tem hoje 2 ativos, uma segunda
  // apareceu com 1, e a linha vigente continua sendo a primeira.
  const vigente: VigenciaGestor = { id: "c0", unitId: UNIDADE, managerId: GESTOR_A };
  assertEquals(decideDepartmentManagerTransitions([observacao([A, B])], [vigente]), []);
});

Deno.test("a vigente sai de cena e a substituta inequívoca fecha a anterior", () => {
  const vigente: VigenciaGestor = { id: "c0", unitId: UNIDADE, managerId: GESTOR_A };
  const t = decideDepartmentManagerTransitions([observacao([B])], [vigente]);
  assertEquals(t.length, 1);
  assertEquals(t[0].closeId, "c0", "a substituição fecha a linha anterior na mesma transação");
  assertEquals(t[0].managerId, GESTOR_B);
});

Deno.test("vigente fora de cena com ambiguidade não fecha nada", () => {
  // Não existe fechar sem substituto: a RPC exige `p_estrutura_id`. Sem
  // candidato inequívoco a linha antiga permanece aberta, que é o que produção
  // mostra no departamento que hoje não tem nenhum ativo.
  const vigente: VigenciaGestor = { id: "c0", unitId: UNIDADE, managerId: "cccccccc" };
  assertEquals(decideDepartmentManagerTransitions([observacao([A, B])], [vigente]), []);
});

Deno.test("departamento sem nenhuma Estrutura observada mantém o que estava", () => {
  const vigente: VigenciaGestor = { id: "c0", unitId: UNIDADE, managerId: GESTOR_A };
  assertEquals(decideDepartmentManagerTransitions([observacao([])], [vigente]), []);
});
