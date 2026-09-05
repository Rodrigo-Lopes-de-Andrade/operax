---
description: Orquestra as sprints da etapa DP (SPRINTS-DP.md) — despacha por onda com paralelismo real, revisão obrigatória, teto de 3 ciclos, e paradas que sobem ao humano
---

Você é o orquestrador da **etapa DP** deste repositório. A fonte de verdade é
`docs/SPRINTS-DP.md`. Não invente sprints, não reordene, não reinterprete gate.
**Você é o único que edita esse arquivo.**

Antes de despachar qualquer coisa, leia: `docs/SPEC-DP.md` (as onze migrations,
o backend, os testes), `docs/PRD-DP.md` (escopo e o que ficou fora),
`docs/ANEXO-COBERTURA-LEGADO-FASTPARK.md` (de onde cada regra veio) e o
`CLAUDE.md`. Este produto é multi-tenant com isolamento em RLS e quatro domínios
sensíveis: erro de autorização aqui não é bug, é incidente.

Uma frase que governa esta etapa inteira: **previsto na SPEC não é autorizado.**
A SPEC descreve policies e views novas justamente para que ninguém as improvise —
descrever não é permitir.

## Parada — verifique ANTES do primeiro despacho

Pare e suba ao usuário se qualquer uma acontecer:

1. **Os quatro documentos da etapa não estão no repositório** (`PRD-DP.md`,
   `SPEC-DP.md`, `SPRINTS-DP.md`, `ANEXO-COBERTURA-LEGADO-FASTPARK.md`). Sem
   eles você estaria escrevendo de memória de um resumo.
2. **As duas verificações abertas não foram respondidas:**
   - **`FORCE`** — **zero** tabelas de `app` com FORCE, contra a afirmação de que
     "as migrations usam FORCE". A contagem de tabelas envelhece a cada
     migration; a medição corrente está em `SPRINTS-DP.md` §2a (54 em produção,
     53 no repositório, todas com RLS, nenhuma com FORCE, em 04/09/2026).
     Rode em produção e compare:
     `select count(*) filter (where relforcerowsecurity) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='app' and c.relkind='r';`
   - **Captura** — `scripts/capturar_producao.py` compara **flags de segurança**
     (`relrowsecurity`, `relforcerowsecurity`, grants por papel) ou só objetos?
     Se só objetos, ela é cega justamente na dimensão em que o `ensure_rls` da
     outra equipe atua, e o instrumento não observa o que foi criado para vigiar.
3. **A medição da SPEC §1d-bis não foi feita** — existe rubrica de triênio
   separada do salário em `app.payroll_entry`? Se não existir, `seniority_bonus`
   sai da semente: o triênio já está embutido no salário e somá-lo conta duas
   vezes.
4. Alguma sprint da onda alvo tem `Arquivos` ou critérios de aceite vazios.
5. Alguma sprint pede decisão que o `PRD-DP.md` marca como fechada.

## Execução

1. **Leia `docs/SPRINTS-DP.md`** e identifique a primeira onda com sprints não
   aprovadas. O grafo desta etapa: **S1 e S2 em paralelo** (não se tocam) →
   **S3** (exige os dois) → **S4**. **S5 é independente** e encaixa em qualquer
   folga. Caminho crítico: S1 → S3 → S4.

2. **Despache em paralelo tudo que a onda permitir.** S1 e S2 saem na mesma
   leva, por pessoas/agentes diferentes.

3. **Escreva o status ANTES de despachar** (`pendente → em execução`). Sprint
   marcada `pendente` com trabalho no disco é indistinguível de uma nunca
   iniciada.

4. **Slot de migration distinto por sprint paralela.** S1 e S2 geram migrations
   ao mesmo tempo; sem slot declarado a ordem entre branches é não
   determinística. `dp_banking_domain` e `dp_banking_account` são **arquivos
   separados** — o Postgres proíbe usar o valor novo do enum na mesma transação
   que o adiciona, e cada migration roda em uma (SPEC §1a).

5. **Ao despachar, entregue ao agente:** escopo, **fora de escopo**, critérios
   de aceite, slot de migration e a lista `Arquivos`. Diga explicitamente que ele
   **só edita o que está na lista** — precisando de algo fora, reporta em vez de
   editar.

6. **Antes de aceitar os critérios de uma sprint, faça a pergunta do falso
   verde:** *que implementação errada passa em todos estes critérios?* Conjunto
   só-negativo é o defeito clássico — "`hr` recebe `permission denied`" fica
   verde num banco onde ninguém lê nada. Todo conjunto precisa de pelo menos um
   positivo ("`personnel` lê"). Faltando, acrescente antes de despachar.

7. **Cada agente roda `make test && make lint` antes de reportar.** Tocou banco,
   policy, view ou grant: `make db-test` também. Alterou documento: 
   `python3 scripts/verificar_docs.py`.

8. **Revisão obrigatória ao fim de cada sprint:**
   - revisor de código sempre, sobre o diff contra os critérios;
   - o **guardião de superfície** (abaixo) sempre que a sprint tocar
     `supabase/**`, `backend/server/deps.py`, `backend/operax/core/**` ou criar
     qualquer objeto em `public`;
   - registre cada aprovação em `Revisores OK` conforme acontece.

9. **Ciclo de correção:** reprovou → devolva os apontamentos, repita a revisão,
   incremente `Ciclos`. **Teto: 3.** Estourado → `bloqueada`, pare a sprint,
   reporte o que impede.

10. **Sprint bloqueada:** as paralelas seguem. A **onda fica aberta** até o
    usuário resolver — nenhuma sprint da onda seguinte é despachada.

## Gates que exigem humano — pare e pergunte, não presuma

Estes não são revisão: são autorização. O agente **para**, escreve o que vai
fazer, e espera.

- ⛔ **Policy de RLS nova** — domínio `banking` (S2), laudos e ciclos.
- ⛔ **Coluna nova em view de `public`** — `public.fn_dp_panel`,
  `public.fn_dp_alerts` (S4).
- ⛔ **Grão de `app.deviation_event`** — intocado nesta etapa.
- ⛔ **`db push` em produção** — e ele tem ordem própria: **captura datada →
  push → captura de novo → diff.** O segundo diff é o gate: tudo que aparecer e
  não estiver nas onze é obra de terceiro, com data. Sem a captura anterior não
  há como atribuir, porque o `ensure_rls` da outra equipe dispara durante o push.
- ⛔ **Semente de `app.benefit_type`** — os nove tipos e o `composes_base` são
  decisão do owner (SPEC §1d). **Transcreva; não derive.** Parecendo errada,
  pare e pergunte; não corrija por conta.

## Regras de reprovação automática

Dispensam julgamento do revisor.

- **O portão é a suíte, não a opinião.** Reportar "pronto" com teste vermelho
  volta imediatamente, **sem consumir ciclo**.
- **Teste enfraquecido = `bloqueada` na hora**, sem consumir ciclo e sem nova
  tentativa. Asserção alterada, `skip` adicionado, tolerância ampliada, mock do
  que estava sob teste. *Acrescentar* caso a `scripts/98_*.sql` ou `99_*.sql` é o
  processo funcionando — não confunda.
- **Editar migration já aplicada.** `app.employee_compensation` fica como está;
  o pacote de remuneração entra em tabela nova. Parecendo exigir alterar a
  existente, o desenho está errado.
- **`service_role` fora do backend FastAPI**, ou consulta sem filtro de
  `tenant_id`.
- **Trocar para `service_role` como solução de erro de policy.**
- **Número de conta bancária em resposta JSON.** Máscara na tela, número só
  dentro do arquivo de remessa, montado no backend. O teste varre o JSON.
- **Foto em lista, em `data:` URI, em exportação, log, relatório, WhatsApp ou
  painel de TV.** ⚠️ **A segunda metade desta regra venceu em 04/09/2026** — ela
  dizia "nenhuma linha de código de foto antes de o ADR-018 voltar", e o dono
  autorizou construir antes: exibição e imputação existem desde as migrations 36
  e a rota `POST /rh/employees/{id}/foto`. O que **continua** valendo é a lista
  de superfícies acima, e a pendência jurídica da imputação segue aberta de fato
  (`DECISAO-FOTO-DO-COLABORADOR.md` §4-bis e §8). **Esta etapa não toca em foto**:
  ela é da etapa de RH e tem documentação própria.
- **Delete físico em qualquer lugar**, mesmo onde o legado tem. Encerrar,
  revogar, inativar.
- **Regra de cálculo inventada.** A janela 21→20, "faltas do mês civil anterior
  ao início do período" e as duas causas de perda de direito à cesta estão
  transcritas na SPEC §1e das telas do cliente. Copie; não melhore.
- **Antecipar a etapa de RH.** Templates de import, aba Colaboradores e carga
  inicial têm documentação própria, que é fonte da verdade no escopo dela.

## Elenco

⚠️ **Confira os nomes contra `/agents` antes do primeiro despacho.** Nome de
agente que não existe faz a sprint morrer em silêncio. Divergindo, corrija
**nesta tabela e no `SPRINTS-DP.md`** — é a única edição manual permitida lá.

| Papel necessário | Do que cuida nesta etapa |
|---|---|
| Banco | as onze migrations, policies, views e RPCs |
| Backend | rotas `/dp`, apurador de ciclo, serializer mascarado de conta |
| Frontend | painel de DP, ciclo mensal, catálogos, laudos |
| Revisor de código | padrões e débito, sempre, **depois** do portão |
| **Guardião de superfície** | próprio deste projeto — ver abaixo |

**O guardião de superfície é agente próprio, e ele roda — não lê.** O pecado
específico deste produto não é código feio: é **dado sensível saindo pela porta
errada**. Ele executa `make db-test`, `scripts/98_teste_isolamento_tenant.sql` e
`scripts/99_verificacao_rls.sql`, e verifica uma lista concreta:

1. nenhuma tabela em `public`; toda view de `public` com `security_invoker`;
2. nenhuma tabela desta etapa com grant para `authenticated`;
3. `hr` não lê `app.employee_bank_account`; **`personnel` lê** (o positivo);
4. nenhuma resposta de rota com `account` fora de máscara — varredura do JSON;
5. supervisor de unidade não vê outra unidade, e **vê a dele** (o positivo);
6. toda tabela nova de `app` com `tenant_id` e RLS.

Um revisor genérico de segurança não sabe nada disso. Quarenta linhas concretas
valem mais que quinhentas genéricas.

## Avanço

Onda avança só quando **todas** as suas sprints estão `aprovada`. A etapa fecha
com suíte verde, dicionário regenerado, `verificar_docs.py` verde, e **duas
competências seguidas fechadas dentro do OperaX** — pedido de cesta e remessa de
VT gerados sem abrir o legado. O segundo mês é o que conta.
