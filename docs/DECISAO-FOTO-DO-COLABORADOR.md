<!-- verificar-docs: inexistentes-de-proposito app.job_execucao -->

# Decisão — foto do colaborador no painel

**Decisão:** a foto entra, exibida pelo **Caminho 2** (FastAPI), sob o domínio
sensível **`pii`**.
**Quem decidiu:** Rodrigo (owner), **04/09/2026**, a pedido do cliente.
**Condição de destrave:** o `PRD-DP.md` §5 excluía a foto com a condição escrita
*"fica de fora até o cliente pedir"*. O cliente pediu. A exclusão era **um padrão
com destrave nomeado, não uma proibição**.

⚠️ **Atualização de 04/09/2026 — deixa de ser bloqueio e passa a ser risco
carregado.** O cliente declarou a foto **requisito**, não conveniência. Isso não
muda o risco; muda o **custo de não fazer**, que antes estava implícito em zero. A
construção começou; a §4 corre em paralelo, com prazo.

---

## 1. As três barreiras, e o que cada uma realmente diz

A sessão de engenharia encontrou três bloqueios independentes e parou. **Parou
certo.** Mas as três não dizem a mesma coisa:

| Camada | O que impede | O que isso significa |
|---|---|---|
| Banco | `secullum` não é exposto ao PostgREST | o navegador não alcança — continua verdade, e **deve continuar** |
| Backend | nenhum endpoint referenciava a coluna | **ausência**, não proibição |
| Frontend | dois componentes com "iniciais, nunca foto" | decisão de produto anterior, **reversível por decisão de produto** |

A regra citada é sobre **superfície**, não sobre **visibilidade**. *"Nunca em view
exposta ao painel, nunca em log, nunca em relatório"* proíbe o caminho
descuidado: a foto trafegando pela chave anônima, caindo em log de aplicação, ou
saindo num Excel. Um endpoint do Caminho 2 — papel revalidado, domínio checado,
escopo aplicado, resposta não logada — **honra a regra em vez de violá-la**. A
frase nunca disse "nenhum humano pode ver".

Isso não dispensa a verificação da §4. Dispensa apenas a leitura de que a regra
proíbe qualquer exibição.

## 2. O fato que muda a avaliação de risco

**O sistema que o cliente usa hoje já exibe a foto** — na ficha cadastral do
FastPark, com a ação "Alterar foto" ao lado. As mesmas pessoas, para as mesmas
equipes de DP, todo dia.

Exibir a foto no OperaX para DP/RH **não cria exposição nova**: reproduz uma que
já existe na ferramenta que o OperaX vai substituir. O risco a avaliar não é *"o
cliente pode ver o rosto"* (já pode), é *"o OperaX pode **ampliá-la**"* — mais
papéis, mais superfícies, mais persistência. É por isso que a forma da §5 é
estreita.

## 3. As colunas de foto não estão neste repositório

As colunas existem **só em produção**, criadas fora das migrations deste
repositório — pela outra equipe, como o próprio ADR-018. É o **terceiro objeto
fora de banda**, depois de `app.job_execucao` e do serviço `sync-fotos`. Os três
são o mesmo fenômeno: outra equipe escreve neste banco por fora.

Consequência imediata: qualquer `supabase db push` corre contra um schema com
objetos que o repo não conhece — e isso vale para as onze migrations da etapa DP.

⚠️ **Correção de medição, 04/09/2026.** A versão original desta seção afirmava
que `secullum."Funcionario"` tem 17 colunas, que não há `bytea` no schema, e que
nenhum `.sql` do repositório menciona foto. **Medido, os três estão errados:**
`scripts/_baseline.sql` descreve 82 colunas e `supabase/fixtures/espelho_secullum.sql`
descreve 83, ambos **com** as seis colunas de foto e o índice da fila.

A **conclusão continua de pé, e por um caminho mais preciso**: nenhuma
*migration* cria a tabela ou as colunas. O baseline e a fixture são **captura**,
escrita depois do fato para acompanhar produção — que é exatamente por que a
verificação contra eles não detecta deriva. Ver `PLANO-RECONCILIACAO-NUVEM.md`
§3d.

## 4. O que falta verificar — e é do owner

⏱️ **Prazo: 7 dias a partir de 04/09/2026.** Sem resposta, o risco é aceito por
escrito aqui, com dono e data — **nunca por silêncio**.

A pergunta à outra equipe, em duas linhas:

> A restrição do ADR-018 §6.3 é sobre **superfície** (não trafegar por view
> pública, log ou relatório) ou sobre **visibilidade** (nenhum operador pode ver
> o rosto)? E a origem dela é **LGPD**, **contrato com o cliente**, ou **decisão
> de produto de vocês**?

- **Superfície** → esta decisão vale como está.
- **Visibilidade por contrato ou base legal** → a decisão **cai**, e o motivo
  entra aqui. O cliente pedir não supera uma restrição contratual dele mesmo.
- **Decisão de produto da outra equipe** → é conversa entre equipes, e a decisão
  do owner deste produto prevalece no escopo deste produto.

**Por que isso deixou de travar a construção.** Três coisas na mesma direção:

1. **O sistema do próprio cliente já exibe a foto**, todo dia, para o mesmo DP, e
   foi a outra equipe que o construiu. Se §6.3 proibisse qualquer exibição, ela
   estaria sendo violada agora, **por quem escreveu a regra**. Isso torna a
   leitura "é regra de superfície" muito mais provável que "é proibição legal".
2. **A exposição marginal é pequena.** Quem tem `pii` já vê CPF, RG, endereço e
   filiação da mesma pessoa. O rosto não é categoria nova.
3. **É reversível e não cria dado.** A foto já está no espelho. O que se constrói
   é um **caminho de leitura** — remover endpoint e componente desfaz.

⛔ **E se a resposta vier "é contrato ou base legal":** a tela sai, **e o cliente
precisa saber que a ferramenta que ele usa hoje faz algo que o contrato dele não
permite.** Essa informação é dele, e é mais valiosa que a tela.

## 4-bis. São DUAS decisões, e este documento tratava como uma

Registrado em **04/09/2026**, a partir de achado da sessão de engenharia.

**Exibir** a foto que já está no espelho e **imputar** uma foto nova são decisões
com posturas de LGPD diferentes. Os argumentos de risco da §4 foram escritos para
a primeira:

| Argumento da §4 | Vale para exibir | Vale para imputar |
|---|---|---|
| o sistema do cliente já faz isso | ✅ | ⚠️ **enfraquece** — eles exibem e alteram, mas quem guarda é o Secullum, não um terceiro |
| exposição marginal pequena (papéis `pii` já veem CPF, RG, endereço) | ✅ | ✅ |
| reversível, não cria dado | ✅ | ❌ **cai inteiro** — upload cria dado biométrico novo no nosso sistema |

**Consequência:** a decisão de **exibir** segue como está — risco carregado,
prazo de 7 dias para o ADR-018. A decisão de **imputar** é nova, e a pergunta do
ADR-018 fica **mais urgente para ela, não menos**.

⛔ **E uma pergunta que o ADR-018 não responde, porque é de outro eixo:** com
upload, a **EURECA passa a guardar dado biométrico que o cliente inseriu** — não
a espelhar o que a origem já tinha. Isso é **posição contratual entre EURECA e
cliente**, assunto separado das regras da outra equipe. **Precisa de resposta
antes do primeiro byte gravado.**

📌 **A ordem de grandeza torna a separação barata:** dos **80 ativos, 76 já têm
foto na origem**. A exibição atende **95% do requisito imediatamente**; a
imputação existe para **4 pessoas**. Separar não adia o que o cliente pediu —
entrega quase tudo agora e põe atrás da resposta a parte que carrega peso
jurídico diferente.

⚠️ **Antes de qualquer das duas: o cliente precisa VER ou precisa INSERIR?** Se
for só ver, esta seção e a §4-ter deixam de existir.

## 4-ter. Se a imputação for confirmada — a forma

⛔ **PARADA OBRIGATÓRIA: tabela nova em `app` com policy de RLS. Escrito aqui não
é autorizado aqui.**

- **Tabela nossa: `app.employee_photo`**, com `tenant_id`, RLS e domínio `pii`.
  **Nunca escrever em `secullum`** — o espelho é cópia literal da origem, e
  escrita de terceiro nele é a mesma classe de erro que a outra equipe comete
  conosco.
- **`bytea`, não bucket.** Bucket é mais uma superfície com política própria para
  acertar, e este produto já tem superfícies demais. **Sem grant para
  `authenticated`**: leitura e escrita só pelo Caminho 2, como a conta bancária.
- **Imputação só onde a origem declara não ter** (`"PossuiFoto" = false`). Assim
  as duas fontes **não se sobrepõem por construção**, e precedência deixa de ser
  questão no caso normal.
- **Precedência quando as duas existirem:** a **origem vence na exibição**, e a
  manual **nunca é apagada**. O espelho é o registro de identidade; a foto
  enviada é tapa-buraco de uma lacuna da origem, e quando a origem preenche, ela
  é mais provavelmente a atual. O inverso — rosto desatualizado sobrevivendo a
  uma origem corrigida — é o pior dos dois erros.
- **A substituição é visível, nunca silenciosa.** A ficha diz *"origem: Secullum ·
  substituiu a foto enviada em DD/MM por [autor]"*. Trocar em silêncio o rosto
  que o DP escolheu é o erro que a sessão apontou.

## 5. A forma da decisão

- **Domínio `pii`.** Quem tem `pii` vê: `owner`, `personnel`, `hr` — a matriz já
  semeada. `regional_manager`, `unit_supervisor`, `executive` e `accounting`
  **não**. Ampliar depois é decisão nova.
- **Caminho 2, endpoint dedicado.** `GET` por colaborador, revalidando papel,
  domínio e escopo; devolve **a imagem**, não JSON com bytes. O navegador nunca
  fala com `secullum`.
- **Nunca em lista.** Requisição individual, na ficha aberta. Não entra em
  listagem, não vira `data:` URI, não é pré-carregada. Lista com 176 rostos é
  **exportação de biometria com outro nome**.
- **Nunca em exportação, log, relatório, WhatsApp ou painel de TV.**
- **Sem URL pública.** Nada de link assinado de longa duração, bucket público ou
  URL que sobreviva à sessão.
- **Acesso registrado.** 🔴 **CORREÇÃO de 04/09/2026 — esta cláusula era FALSA
  quando escrita, e o gate de superfície a derrubou.** O texto dizia "abrir a
  ficha já é evento auditável; a foto anda com ela em `app.audit_log`". **Não
  anda, e a ficha também não.** Medido: nenhum call site de `audit()` em
  `operax/rh/` é de leitura — os seis são `insert` ou `update`. **Nenhuma leitura
  é auditada neste produto hoje**, nem a ficha, nem a foto.

  A intenção continua válida: *não se registra byte, registra-se quem abriu a
  ficha de quem*. Mas ela é **trabalho a fazer**, não proteção existente — e
  descrever como existente uma mitigação que não está lá é pior que não tê-la,
  porque alguém decide o risco contando com ela.

  ⛔ **Auditar leitura é decisão em aberto**, e não é pequena: muda o volume de
  `app.audit_log` (toda abertura de ficha vira linha) e é escrita numa tabela de
  auditoria. Fica nomeada aqui em vez de silenciada.

## 6. Fonte da foto — RESOLVIDO por medição (04/09/2026)

A dúvida era se havia duas fontes concorrentes. **Não há.** A varredura do schema
por `bytea` e por nome de imagem devolveu **uma tabela só**, no espelho, e nenhum
bucket de Storage.

Existem **dois escritores na mesma coluna**: o `sync_fotos` da Vercel (40 por
execução) e a Edge Function deste repositório. Somados, **121 de 153** no dia da
medição, com a fila enchendo a ~40/dia.

Duas consequências de tela, que não são detalhe:

1. **A ficha distingue "sem foto" de "sem foto ainda".** ~32 pessoas não teriam
   rosto no dia da medição, e vazio sem explicação numa tela de identificação
   parece defeito. `foto_sincronizada_em` nulo é o discriminador.
2. **A idade do rosto é dado de tela**, pela mesma disciplina de idade do dado do
   resto do produto. Rosto de dois anos numa ficha de identificação é pior que
   rosto nenhum, e só a data revela.

## 7. O que foi construído (04/09/2026)

| Peça | Onde |
|---|---|
| Leitura em dois passos | `backend/operax/rh/foto.py` |
| Rota binária | `GET /rh/employees/{id}/foto` |
| Metadado na ficha | `HrPhoto` em `backend/server/models.py` |
| Componente | `frontend/src/components/rh/employee-photo.tsx` |
| Testes | 7 em `backend/tests/test_rh_employees.py` |

📌 **Por que a leitura tem dois passos.** `authenticated` **não tem `usage` em
`secullum`**, então a leitura não cabe inteira sob `user_scope`. A saída não foi
subir o privilégio da consulta toda, e sim separar as perguntas: *"quem pergunta
pode ver esta pessoa?"* é respondida pela **RLS**, sob `user_scope`; só depois de
ela dizer sim é que os bytes saem por `tenant_scope`. Uma consulta única com
`service_role` faria a autorização virar código em vez de policy.

**404 cobre três casos de propósito:** pessoa inexistente, pessoa fora de
alcance, e pessoa sem foto. Distinguir os dois primeiros confirmaria que alguém
existe noutra unidade.
