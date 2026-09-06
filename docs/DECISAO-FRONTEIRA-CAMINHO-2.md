<!-- verificar-docs: inexistentes-de-proposito -->
<!-- `app.employee_bank_account` é entidade que a etapa DP vai criar (S2). -->

# OperaX — decisão: a fronteira de isolamento do Caminho 2

**Decisão:** o isolamento do Caminho 2 fica **declarado como sendo de código** —
`backend/operax/core/tenant.py` mais a revalidação de papel e domínio na rota. A
etapa DP anda sobre essa condição, que é a mesma em que as 54 tabelas de `app`
já vivem hoje.
**Quem decidiu:** Rodrigo (owner), 05/09/2026.
**Alternativas recusadas:** trocar o papel de conexão antes da etapa DP (é a
fronteira certa, mas é projeto próprio e a etapa esperaria por ele); e ligar
FORCE em `app` (medido como no-op — ver §1).

---

## 1. O que a medição derrubou

A condição 2a do `SPRINTS-DP.md` bloqueava a etapa com esta frase, que está
certa: *"sem FORCE o dono da tabela não é filtrado pela RLS, e o backend conecta
como `postgres`, que é o dono de `app`"*.

**O que faltava medir é que com FORCE ele também não é.** `postgres` não é só
dono das 54 tabelas: é **`rolbypassrls = true`**, e BYPASSRLS vence FORCE.

Ensaio de 05/09/2026, no banco descartável do `db-test` — tabela em `app`, RLS
ligada, policy `using (false)`, duas linhas gravadas:

| # | Dono da tabela | FORCE | Linhas que o dono lê |
|---|---|---|---|
| A | `postgres` (BYPASSRLS) | off | **2** |
| B | `postgres` (BYPASSRLS) | **ON** | **2** |
| C | papel sem BYPASSRLS | **ON** | **0** |
| D | papel sem BYPASSRLS | off | **2** |

**C contra D prova que FORCE não está quebrada.** Ela faz exatamente o que a
documentação do Postgres diz. **A contra B prova que ela não alcança este
backend.**

⚠️ **Por isso ligar FORCE seria pior que não ligar:** tiraria a pergunta da lista
de auditoria sem tê-la respondido. Verde falso é a falha do incidente de
27/08/2026 com outra roupa — lá uma premissa caiu e a ação seguiu; aqui a ação
pareceria fechar algo que não fecha.

## 2. O que continua verdadeiro, e não depende desta decisão

✅ **O Caminho 1 é protegido pelo banco, não por código.** `anon` e
`authenticated` não têm BYPASSRLS e não são donos de nada — a RLS os filtra com
ou sem FORCE. É o que `scripts/98_teste_isolamento_tenant.sql` e
`scripts/99_verificacao_rls.sql` provam a cada `make db-test`, com os dois
tenants e os quatro papéis.

✅ **As quatro regras de superfície seguem valendo integralmente:** nenhuma tabela
em `public`, toda view com `security_invoker`, toda tabela de `app` com
`tenant_id` e RLS, `service_role` só no backend.

## 3. O que esta decisão assume, explicitamente

Assumir por escrito é o ponto — a alternativa não é "sem risco", é "com o mesmo
risco, não declarado".

1. **Uma consulta do Caminho 2 sem filtro de `tenant_id` lê todos os tenants.** O
   banco não a barra. O que existe entre ela e produção é o `bind_tenant`, e o
   docstring dele já diz o que ele não é: *"lint barato na saída, não a fronteira
   de segurança"*. Três formas passam no lint e ainda leem tudo — placeholder
   dentro de comentário SQL, predicado tautológico, e o lado não filtrado de um
   join ou union.
2. **A revalidação de papel e domínio sensível é do backend.** A rota confere; o
   banco não confere de novo para `postgres`.
3. **As ~10 tabelas novas da etapa DP nascem nessa condição** — inclusive
   `app.employee_bank_account`, do domínio `banking`. Não é regressão: é a
   condição de `app.employee_pii` e das outras 53 desde sempre.

## 4. O item que fica no backlog, com a medição na mão

**Trocar o papel de conexão do backend** por um papel de aplicação **sem
BYPASSRLS e que não seja dono das tabelas**, com o tenant setado por transação.
É a fronteira que o próprio `core/tenant.py` nomeia como pendente.

**Por que é projeto próprio e não sprint:** hoje todo `tenant_scope` atravessa
por bypass. Com o papel trocado, ele passa a depender de policies que assumem um
JWT que ele não carrega — e a falha vira **zero linhas em vez de erro**, que é o
modo de quebra mais caro de diagnosticar. Exige varrer todo acesso do Caminho 2,
não um pedaço.

📌 **FORCE entra junto, e só junto.** Depois da troca ela deixa de ser opcional e
passa a ser obrigatória — antes dela, é decoração.

## 5. O que reverteria esta decisão

Qualquer uma das três:

- **Um segundo tenant real em produção.** Hoje há um (FastPark). O custo de um
  vazamento entre tenants é hipotético enquanto o conjunto tem um elemento; com
  dois, deixa de ser.
- **Acesso do Caminho 2 escrito por quem não conhece a regra.** A fronteira é
  disciplina de código, e disciplina não sobrevive a rotatividade sem o banco
  atrás.
- **Um achado de que o `bind_tenant` já foi burlado** — qualquer das três formas
  da §3.1 encontrada em código de produção. Aí a fronteira de código já falhou
  uma vez, e a discussão acabou.
