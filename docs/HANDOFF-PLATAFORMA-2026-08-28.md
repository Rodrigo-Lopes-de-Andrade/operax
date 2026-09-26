<!-- verificar-docs: inexistentes-de-proposito secullum.departamento_gestor secullum.estrutura_evento_titular -->

# Handoff da equipe de plataforma — 28/08/2026

Documento **recebido**, não escrito aqui: "Sincronização Secullum → Supabase",
emitido em 28/08/2026 pela equipe que mantém o `kastropark-jobs`. Repositório
deles: `github.com/fdiasoliver/kastropark` (privado, acesso sob convite do
Owner).

Esta página registra o que ele declara, o que ele corrige do que estava escrito
aqui, e as decisões que o dono tomou em cima dele no mesmo dia.

---

## 1. A fronteira que eles declaram

Vale a partir de **27/08/2026**, nas palavras deles: "qualquer trabalho fora da
coluna da esquerda não é mantido por esta equipe".

| Equipe de plataforma/dados | Equipe de produto (nós) |
|---|---|
| Autenticação e consumo da API do Secullum | Motor de detecção de desvio |
| Sincronização cadastral e de batidas | Relatório consolidado (WhatsApp/e-mail) |
| Persistência no schema `secullum` | Dashboard e painel/frontend |
| Infraestrutura de hospedagem dos jobs (Vercel, domínio) | Tudo em `app` |

✅ **Decisão do dono, 28/08/2026, com este documento na mesa: assumimos a
sincronização.** A decisão de trazer o runner para as Edge Functions deste
repositório já existia, e foi tomada **antes** do handoff. Ele é premissa nova,
então a decisão foi refeita em cima dele — que é o que a Regra 0 do `CLAUDE.md`
manda. O passo 4 do `RUNBOOK-JANELA-CONVERGENCIA.md` vale como está escrito.

**A fronteira da tabela acima, portanto, tem prazo de validade.** Depois da
janela, "autenticação e consumo da API do Secullum", "sincronização cadastral e
de batidas" e "persistência no schema `secullum`" passam para este lado. Isso
precisa ser dito a eles pelo Owner — não é mudança que se comunica por
consequência, é a coluna esquerda inteira do documento que eles emitiram
ontem.

O que a decisão obriga, e nesta ordem:

1. **Eles entregam as quatro credenciais do Secullum** (`SECULLUM_USERNAME`,
   `SECULLUM_PASSWORD`, `SECULLUM_CLIENT_ID`, `SECULLUM_BANK_ID`). O §05 deles
   pede para "confirmar antes de reemitir qualquer chave" — a confirmação é
   exatamente esta decisão, e o pedido passa a fazer sentido para eles.
2. **Os dois jobs de `pg_cron` trocam de destino** na janela, deixando de chamar
   o `kastropark-jobs`. Como o agendador é o `pg_cron` do nosso banco (§2 abaixo),
   é a reescrita do comando que desliga a chamada — não há gesto do lado deles.
3. **O exposed schemas volta a ser corrigível**, porque as funções daqui usam
   conexão direta. Deixa de ser nó e vira item 4 do passo 4.
4. **O teto de parada deixa de ser 48 h** depois da troca: `resolveRunOptions` lê
   escopo e janela da invocação, e o `backfill` de 7 dias existe sem redeploy.

⚠️ O que **não** muda: `secullum.departamento_gestor` e
`secullum.estrutura_evento_titular` continuam sendo o desenho deles, e a decisão
A abaixo continua valendo. Assumir a sincronização é assumir o processo, não
reescrever o modelo — a promoção para `app` já é nossa desde sempre.

---

## 2. O que ele resolve de pendências que estavam abertas aqui

**O agendador é do nosso lado.** `pg_cron` + `pg_net` do próprio Supabase,
disparando HTTP autenticado — **não há cron na Vercel**. Então desabilitar os
dois jobs no passo 0 da janela continua sendo suficiente para parar a escrita
concorrente. (Confirmar com uma leitura de `cron.job` na janela; o documento é
declaração, não medição nossa.)

**Cadência confirmada:** cadastro a cada 30 min, batidas a cada 15 — o mesmo que
`DECISAO-CADENCIA-SYNC.md` registra.

**O tropeço do exposed schemas não foi só nosso.** O §04.3 deles diz, com todas
as letras, que já derrubaram o acesso a `secullum` por engano ao adicionar `app`
naquele campo. É lista única do projeto inteiro, e editar **substitui**. Dois
times, o mesmo alçapão, com quinze dias de diferença.

---

## 3. As decisões do dono, 28/08/2026

### A. `secullum.departamento_gestor` — fica a que já existe

Eles mantêm a tabela que responde "qual `Estrutura` responde por qual
`Departamento`", com histórico de vigência. Não construímos outra.

⚠️ **Não é refatoração da migration 27**, e a diferença importa: `app.manager`
responde "a quem **esta pessoa** responde", vinda de `Funcionario.EstruturaId`;
a deles é a mesma origem **agregada por departamento**, gravada como observação
(`observado_desde`, `observado_ate`, `funcionarios_observados`). São perguntas
diferentes, e a nossa é mais fina — trocar o vínculo por pessoa pelo do
departamento erraria em quem tem `EstruturaId` diferente do dominante, que é a
classe de erro que a regra 5 evita para empresa.

O que a decisão fecha é para frente: quando precisarmos de "quem responde pela
unidade" — e o primeiro lugar é `app.unit_responsible`, hoje preenchida à mão e
que decide para quem o relatório vai —, a resposta vem da tabela deles.

### B. O ledger de migrations é compartilhado — avisar antes

Eles aplicam o que é deles via `supabase db query --file` justamente para não
tocar `supabase_migrations.schema_migrations`, e avisam que
`supabase migration list` mostra migrations "órfãs" dos dois lados. O passo 3 da
janela registra 21 versões nossas ali. Continua certo fazer — sem isso um
`db push` reaplica o lote —, mas passa a ser combinado, e
`supabase migration repair` não se roda sem alinhar.

### C. Base legal do tratamento de dado pessoal

O §06 deles lista como pendente o "instrumento escrito com finalidade,
categorias e prazo". O dono declarou em 28/08 que **o cliente autorizou
contratualmente**.

⚠️ As duas afirmações são do mesmo dia. Ou o documento deles está desatualizado,
ou "autorização contratual" e "instrumento com finalidade/categorias/prazo" são
coisas diferentes — e a segunda é a que descreve o tratamento. Vale alinhar com
eles, porque é a equipe que grava a PII: o `"Funcionario"` sincronizado inclui
RG, endereço, filiação, nascimento e contato, **com retenção permanente e sem
expurgo automático**, autorizado pelo Owner.

Para nós isso não muda nada de código — `secullum` nunca é exposto, e nenhuma
view de `public` seleciona dessas colunas. É risco de contrato, não de schema.

---

## 4. O que eles ainda esperam de nós

- **Rotação da `service_role`** está parada esperando as duas equipes
  confirmarem que nenhum backend depende da chave atual. Pela nossa parte, dá
  para responder: o backend no Railway usa a chave do **staging**, não a de
  produção.
- **Destino final de `operax.ia.br`.** Hoje aponta para um projeto Vercel vazio
  (`kastropark-painel`), e eles perguntam se deve apontar para a infraestrutura
  de produto. A decisão de 28/08 pôs o painel em `operaxfonted.vercel.app` e a
  API no Railway — então a resposta existe e falta ser dada a eles.

---

## 5. Duas coisas do documento que valem para quem escrever query

Não são novidade para este repositório, e estão aqui porque a equipe deles as
descreve como "cinco coisas que custaram tempo real pra descobrir":

- **O schema padrão da API é `public`.** Cliente Supabase que precise ler
  `secullum.*` tem de declarar o schema na criação, senão o erro é "Could not
  find the table 'public.X' in the schema cache" — que parece permissão e é
  schema errado. Aqui isso não acontece porque o Caminho 2 usa conexão direta
  com `search_path` por schema.
- **GRANT e RLS são independentes.** Tabela com RLS ligada e zero policy não é
  legível por `service_role` — RLS decide linha, GRANT decide a tabela. Toda
  tabela nova precisa do grant explícito na própria migration, que é o que as
  nossas fazem.
