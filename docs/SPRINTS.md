# OperaX — Plano de sprints

Uma linha do tempo só, com quatro trilhas: **banco**, **backend** (FastAPI no
Railway — sync, motor, alertas, assistente), **frontend** (Next.js na Vercel) e
**produto/comercial**. O que estava separado como "sprint de banco" e "sprint de
produto" vira sequência única, porque as dependências são reais e ignorá-las é o
que produz retrabalho.

Estimativas em dias úteis, para uma pessoa dedicada. Contagem começa a partir do
recebimento dos acessos.

---

## Estado em 24/08/2026

Conferido contra o repositório e contra o projeto de produção, não de memória.
Este bloco registra **andamento**; o plano abaixo permanece como foi escrito.

| Sprint | Estado |
|---|---|
| S0 · Diagnóstico e blindagem | ✅ fechada |
| S1 · Isolamento e ajuste do worker | ✅ fechada — a sincronização virou Edge Function (22/08) |
| S2 · Modelo completo e superfície de API | ✅ fechada |
| **S3 · Jornada esperada** | **em andamento** — o motor existe e está testado; falta rodar contra produção |
| S4 · Motor em modo sombra | não começou |
| **S5 · Dashboard** | ✅ **fechada** — os quatro critérios de aceite com teste |
| S6 · Alertas e relatório | não começou — travada em G4 |
| S7 · Assistente de IA | ✅ fechada — 25/08 |
| S8 · Homologação e produção | não começou |

**Números que mudaram desde que este plano foi escrito.** São **22 migrations**
(entraram a `11b`, que renomeia o schema da nuvem de pt para en, a `15` do
rebrand FastPark, a `16` e a `17` de RH, a `18` da idempotência da sombra, e a
`19` e a `20` do assistente). A suíte de banco tem **quatro** conjuntos:
motor de jornada (24 asserções), regras de alerta e cadência (24), isolamento
multi-tenant (21) e verificações estruturais (13).

**A fronteira de segurança passou a ser provada também por HTTP**, contra o
PostgREST do projeto de staging: `anon` toma 401 em toda view, `app`/`secullum`/
`util` respondem 406 mesmo para a chave de serviço, e cada sessão vê só o seu
recorte. `scripts/provar_postgrest.sh` reproduz.

### O que trava o caminho crítico

**Falta o elo entre o espelho e o domínio.** Produção tem 172 pessoas em
`secullum."Funcionario"` e 3.211 marcações em `app.batida_marcacao`, e tem
**zero** linha em `app.employee`, `app.unit` e `app.expected_workday` — e zero
usuário em `auth.users`. Nada promove o espelho para o domínio: não há função de
promoção, e `app.unit_secullum_map` está vazia. Enquanto isso não existir, o
motor de jornada roda sobre uma base vazia e o dashboard abre sem dado.

O S1 já previa essa curadoria ("cadastrar unidades reais; preencher o mapeamento
Departamento → unidade"). Ela não foi feita, e é ela que destrava S3 e S4.

**Atualização de 24/08/2026 — o elo existe agora.**
`backend/operax/motor/cadastro.py` promove `Empresa`, `Departamento` e
`Funcionario` para `app.company`, `app.department` e `app.employee`, e roda como
passo zero de `python -m operax.motor`. Duas decisões que o `make db-test` prova:

- **A empresa vem da pessoa, nunca do departamento.** É a regra 5, e o cenário do
  teste tem exatamente o caso: alguém da Empresa B lotado num departamento da
  Empresa A. Derivar pelo departamento poria cerca de um quarto da folha na
  empresa errada, de forma consistente e invisível.
- **A promoção não inventa unidade.** `app.unit` é dimensão nossa e o espelho não
  tem o conceito; a ponte é `app.unit_secullum_map`, curada com o cliente. Quem
  não tem mapa é promovido com `unit_id` nulo e entra na **fila de pendência**,
  nomeada por departamento e ordenada por quanta gente depende dela — que é o
  segundo lado do aceite do S1 ("zero ativo sem unidade, **ou fila visível**").
  E o `on conflict` preserva a lotação feita à mão: mapa removido não desfaz
  trabalho humano.

O que continua dependendo do cliente é a curadoria em si — decidir qual
departamento é qual pátio. A diferença é que agora ela tem uma fila para
trabalhar em cima, em vez de uma tabela vazia.

**Atualização de 25/08/2026 — a fila ganhou tela.**
`/dashboard/administracao/mapeamento` mostra os departamentos do espelho por peso
(quem tem mais gente sem unidade vem primeiro), sugere a unidade por semelhança de
nome com o número do palpite ao lado, aplica em lote acima de um limiar escolhido
por quem cura, e grava `validated_by`/`validated_at`. Nenhuma migration: a tabela
já tinha as duas colunas desde a migration 04.

Três decisões que a tela toma e vale registrar:

- **A sugestão não é um mapeamento.** Ela é semelhança de nome, não é gravada, e
  some assim que a linha é validada — oferecer alternativa a uma decisão humana é
  convidar a desfazê-la sem querer. É o oposto do que a promoção faz de propósito:
  lá adivinhar é proibido, porque palpite gravado não se distingue de fato lido.
- **A semelhança é contada por palavra, não por letra.** Letra a letra,
  "Departamento 4471" e "Aeroporto 01" passam de 45% — vogais em comum bastam — e
  o palpite errado chega à tela com meio termômetro do lado, virando o clique
  automático de quem está curando quarenta linhas.
- **"Provisório" não entra em "validado".** Mapa que existe e ninguém confirmou é
  uma faixa própria na barra. Somar os dois faria a curadoria parecer terminada
  com metade do trabalho por fazer, que é o jeito mais eficiente de não terminá-la.

O que a curadoria **não** faz é mover quem já tem unidade: é a mesma regra do
`coalesce(excluded.unit_id, app.employee.unit_id)` da promoção. Alocação existente
é trabalho de alguém.

### O S3 tinha uma pergunta que decidia o cronograma. Ela foi respondida

O plano avisava: *"se `HorarioDia` descreve semana fixa, a escala não cabe e a
confiança despenca"*. Medido em 24/08 contra produção:

`secullum."HorarioDia"` é **semana fixa de sete dias** — chave
`(horario_id, "DiaSemana")`, `DiaSemana` de 0 a 6, sem índice de ciclo e sem data
de início. Um 12x36 é ciclo de 48 h e não cabe. O contorno do próprio Secullum
aparece no dado: escalas em pares `Par`/`Ímpar` com `HorarioDia` **inteiramente
vazio**, e nenhum horário alternativo preenchido.

**Mas o alcance é pequeno, e isso muda a conclusão:**

- **66 de 79 ativos (83,5%)** estão em semana fixa, e ela é confiável — 4 de 546
  dias trabalhados (0,7%) caíram em dia declarado como folga.
- **7 pessoas em 2 unidades** (U-040 Cotia e U-042 Alphaville) estão em 12x36 de
  verdade e precisam de uma fonte de rotação que o espelho não traz.
- **6 pessoas na administração** têm horário em branco **por desenho** — os
  horários irmãos se chamam "Ponto por exceção" e "Marcação Supervisor". Elas não
  precisam de escala manual; precisam ficar **fora** do motor.

Então **não** entra o sub-sprint grande de cadastro manual de escala que o plano
previa. Entra um pequeno, de 7 pessoas — e ele **não é opcional**: G4 é taxa de
erro, não cobertura. Sobre 14 dias de dado, um motor ingênuo emitiria ~140
eventos dos quais **≥50 seriam certamente errados (≥36%)**, contra um portão de
≤5%. Dezesseis por cento do efetivo são trinta e seis por cento dos eventos.

### Reconciliação da nuvem — trabalho real que este plano não previa

O projeto de produção (`Kastro Park Ponto`) é **este repositório parado na
migration 11**, com os mesmos arquivos guardados na grafia em português. Alinhá-lo
virou um plano próprio, em `docs/PLANO-RECONCILIACAO-NUVEM.md`:

| Fase | Estado |
|---|---|
| 0 · destravar o acesso | ✅ 22/08 — Management API com o token de conta, sem senha de banco |
| 1 · fotografar sem tocar | ✅ 22/08 |
| 2 · provar a fusão, duas vezes | ✅ 24/08 — Postgres descartável **e** projeto Supabase real |
| 3 · janela de aplicação | **pendente de decisão do dono** — teto de 48 h imposto pelo `sync-batidas` |

A aplicação em si deixou de ser o risco: a Management API é transacional, então a
migration de rename aplica inteira ou não aplica. O que sobra é escrita
concorrente das Edge Functions durante o DDL.

**Os riscos de ingestão declarados na §4b daquele plano** — ausência de transação,
janela de 48 h sem autocura, saída HTTP 200 com ingestão zero e ausência de
alarme — seguem sem sprint aqui, e por decisão: são a trilha de ingestão, que o
dono está documentando à parte. Registrado para não parecer esquecimento (achado
A9 da auditoria de 24/08).

---

### Andamento em 25/08/2026 — o quadro do dia, e a conta que não fechava

Três dos cinco indicadores de headcount do escopo (§4.3, itens 1, 4 e 5) entraram
no **monitor diário**: ativos, em férias e afastados. Ficaram no monitor e não no
dashboard porque "em férias" é fato de um dia — num recorte de 30 dias a pergunta
não tem resposta única.

**A conta não fechava, e ninguém via.** O quadro do monitor saía de
`app.expected_workday`, então quem o motor não materializou não era escalado, não
era folga e não era nada: sumia da tela. Agora ele sai de `app.employee`, e a
diferença virou um número — `unrostered`, ativo sem jornada prevista para o dia.
Contra o seed local, hoje, **os 40 ativos estão todos nesse estado**; antes a
tela mostrava "0 escalados, 0 fora da escala", que se lê como "todo mundo de
folga". As seis pessoas da administração da FastPark estão nesse estado de
propósito, e falha de cobertura do motor tem exatamente a mesma aparência: contar
é o que separa as duas.

**Os indicadores 2 e 3 entraram em 25/08 — com o rótulo que o dado sustenta, e
não com o nome que o escopo usa.** A migration 24 trouxe as quatro tabelas de
ingestão para as migrations, e `operax/motor/marcacao.py` passou a ser o único
lugar onde a ponte para o espelho está escrita: a mesma que `regras.py` atravessa,
para que motor e tela nunca discordem sobre quem bateu.

O que a tela diz é **"com marcação / sem marcação até a leitura de HH:MM"**, e a
hora faz parte da entrega tanto quanto o número. Quem bateu um minuto depois
daquela leitura está do outro lado da conta; sem a hora ao lado, o cartão
afirmaria que essa pessoa não bateu ponto. "Presentes" apagaria a hora e viraria
uma afirmação sobre onde a pessoa estava — que é a **decisão de produto A12**,
aberta com o Rodrigo, e o tipo de frase que um gestor repassa ao colaborador.

Duas coisas continuam verdadeiras e ficam escritas:

- a policy dessas tabelas é `util.has_tenant` sozinha, e não o
  `util.can_see_employee` que guarda as de domínio. Por isso a marcação **não** é
  lida como o usuário: quem autoriza é a consulta de domínio que vem antes, e a
  ponte só é atravessada depois — com um id que a policy já devolveu;
- **nenhuma migration deste repositório cria o espelho.** A 03 endurece as
  tabelas `secullum` que encontrar, e não encontrar nenhuma é desfecho válido: é
  o estado do banco de desenvolvimento. Quando o espelho não está lá, a tela
  mostra a falta da leitura em vez de dois zeros — as duas imagens são idênticas
  e significam o oposto uma da outra.

---

### Andamento em 26/08/2026 — a noite que andava para trás, e a rotação que não cabia

Duas entregas, e a medição que as ordenou inverteu o que o plano previa.

**A medição de 24/08 perguntou cobertura e foi lida como corretude.** Ela contou
quantas pessoas têm escala declarada — 66 de 79 — e não perguntou se o que a
escala declara descreve o turno. Seis horários de produção declaram `Entrada1`
**depois** da própria última `Saida` (19:00 às 05:00), e quatro pessoas ativas
estão neles, em semana fixa, pontuando confiança 100. Estavam dentro dos 66.

Lido como `time`, 05:00 menos 19:00 é menos catorze horas. Uma noite normal saía
com `early_entry` de dezenove horas, `late_exit` de catorze e um intervalo de
menos vinte e duas — três acusações por noite, contra exatamente quem o portão
de 80 deixa passar. Medido sobre 11–26/08: **61 dos 682 dias trabalhados (8,9%)
cruzam a meia-noite**, e 39 deles são dessas quatro pessoas.

**O 12x36 nunca foi a fonte do falso positivo.** Confiança 0 já o barra no
portão. O custo dele é outro, e é ausência: quem pontua 0 não é medido, e o G4
tinha oito pessoas fora do denominador sem que isso aparecesse em lugar nenhum.

O que entrou:

- **A virada de meia-noite** (`regras.py`, `jornada.py`) — toda batida vira
  instante antes de qualquer comparação. A data real sai de
  `secullum."BatidaFonteDados"."Data"`; o degrau para trás na ordem posicional é
  a rede, e a ordem entre as duas foi **medida**: sobre produção a rede
  concordou nas 79 viradas reais e inventou mais 4. O grão de
  `app.deviation_event` não se moveu.
- **A rotação** (migration 25, `app.schedule_rotation_map`) — âncora mais
  comprimento de ciclo, por horário do espelho, no formato do
  `unit_secullum_map`. Rotação sem `validated_at` o motor não lê.
- **A porta** — `/dashboard/administracao/rotacoes`. Mostra os dias em que cada
  horário bateu ponto e deixa a pessoa escolher um como âncora. O sistema **não**
  deduz a âncora das batidas: escala derivada de batida encaixa sempre, e escala
  que encaixa sempre nunca produz `no_punches` nem `punch_on_day_off`.

**E a administração saiu do motor**, decisão do Rodrigo em 26/08. As 6 pessoas
de `U-000 … (Supervisão)` têm horário em branco por desenho — os horários irmãos
se chamam "Ponto por exceção" e "Marcação Supervisor" — e mediram-se contra uma
jornada que ninguém lhes deve. `app.employee.exception_tracking` (migration 26)
é a decisão escrita: quem a carrega não materializa jornada e é contado à parte
no monitor.

O ponto não é economizar seis linhas: é que `unrostered` juntava **decisão** e
**falha de cobertura** no mesmo número, e as duas têm a mesma aparência na tela.
Enquanto dividiam um balde, uma falha de cobertura se escondia lá dentro
parecendo intenção de alguém. Agora o quadro do dia tem as duas faixas, e a
ressalva que dizia "pode ser desenho, pode ser cobertura do motor" virou uma
afirmação.

A marca nasce `false` para todos, pelo mesmo motivo de `triggers_alert`: quem
aparece fora da medição sem alguém ter tirado é quem ninguém decidiu não medir.
E `scripts/92_teste_cadastro.py` passou a afirmar que ela sobrevive à promoção —
a sincronização roda a cada 30 minutos por cima de `app.employee`, e o dia em
que alguém trocar a lista de colunas do `on conflict` por `excluded.*`, seis
supervisores voltam para dentro do motor sem erro nenhum e sem ninguém ver.

### Ainda em 26/08/2026 — o gestor estava no espelho o tempo todo

O escopo pede "comparação entre equipes e gestores" (COBERTURA §4.3 item 14) e
ele estava ❌ com a justificativa de que `employee.manager_employee_id` existe e
nada o agrega. A justificativa estava incompleta: **nada o preenche, e nada
pode.** Ele é FK para `app.employee`, está declarado em `ownership.py` como
`Owner.SYNC, pending=True` e — ao contrário de todos os outros campos de sync —
**sem `mirror=`**. Congelado como "o Secullum manda", sem coluna do Secullum
atrás. O filtro `p_manager_id` dos quatro RPCs, entregue em 25/08, filtra por
ele: hoje não casa com nada.

**O Secullum sabe o gestor, e o repositório já sabia disso em dois lugares.** Ele
chega como `Funcionario.EstruturaId` → `secullum."Estrutura"`, que o
`sync-cadastro` deste repositório chama de manager (`listManagers`,
`upsertManagers`) e que o comentário do baseline descreve como "tabela do
gestor". Medido em produção: 4 estruturas ativas, **69 dos ~70 ativos** ligados a
elas, `EstruturaPaiId` nulo nas quatro (hierarquia de um nível), e `Descricao`
com duas palavras, sem dígito, cujo primeiro nome casa com alguém do quadro — é
nome de pessoa.

O que **não** dá para resolver é qual colaborador é aquele gestor: nome completo
não casa em nenhuma das quatro, e o próprio `sync-cadastro`, que já tenta esse
casamento para achar o e-mail do gestor, resolveu **zero de 4** em produção.
Escrever o vínculo por semelhança de nome seria o palpite que a promoção proíbe.

Então o gestor entrou como dimensão própria — `app.manager` (migration 27),
promovida do espelho, com `fn_ranking_by_manager` e o cartão no dashboard.
`manager_employee_id` fica intocado, respondendo à outra pergunta.

⚠️ O ranking ordena por volume, e volume segue efetivo. Cada linha carrega o
número de pessoas ao lado: sem ele a tela faria uma afirmação de desempenho que
o dado não sustenta, sobre alguém com nome.

### Ainda em 26/08/2026 — `rejected` ganhou quem o produzisse

A migration 23 fechou `app.justification.status` em `accepted` e `rejected` e
registrou, no cabeçalho dela, o que ficava faltando: *"Não há tela que aceite ou
rejeite. `rejected` existe no domínio e não tem quem o produza; enquanto isso não
existir, 'aceita' e 'escrita' são a mesma coisa na prática."*

Entrou a porta, e **sem migration nenhuma** — a coluna, a policy de escrita e o
grant existiam desde a 05 e a 23. `POST /ocorrencias/{id}/justificativa`, com o
veredito no drawer da ocorrência.

**Quem pode não é `is_admin`.** `justification_write` é `for insert` com check
`util.can_see_employee(employee_id)`, e esse recorte é diferente do da curadoria
de propósito: o supervisor responde pelo desvio da unidade dele. Então a
autorização é ler o evento **como o usuário** — se a RLS o devolve, o veredito
pode ser escrito. Nada de regra nova em Python.

Três decisões que o código carrega:

- **Insert, nunca update.** A policy só concede insert, e isso é a semântica: um
  veredito é fato datado com autor. Mudar de ideia escreve outra linha.
- **A pessoa e a data saem do evento, nunca do corpo do pedido.** O cliente manda
  texto e veredito; sobre quem o veredito recai, quem responde é o banco.
- **O veredito é escolhido antes de ser gravado.** Dois botões lado a lado numa
  ação irreversível é um clique errado a um pixel de distância.

⚠️ Falta a *fila*: `fn_pending_justification` existe desde a 23 e nenhuma tela
ainda a lê. O cartão do dashboard continua mostrando "pendentes de ciclo", que é
outro número e está rotulado como tal.

---

## Gates — pontos onde a sprint seguinte não começa

Não são recomendações. Cada um existe porque violá-lo custa mais caro do que
esperar.

| Gate | Condição | Bloqueia | Por quê | Estado em 24/08 |
|---|---|---|---|---|
| **G1** | Diagnóstico rodado e convenção PascalCase confirmada | S0 | As migrations 00 e 03 selecionam por essa convenção | ✅ |
| **G2** | Suíte de isolamento verde | S3 | Motor grava dado real; RLS errada vira vazamento | ✅ e agora provado também por HTTP |
| **G3** | Jornada esperada com ≥80% de confiança | S4 | Sem escala correta, o motor é gerador de falso positivo | os 83,5% de 24/08 mediam **cobertura**, não corretude — ver 26/08 abaixo. As 8 pessoas em horário sem expediente têm fonte de rotação desde a migration 25, e o número volta a ser medido depois da curadoria |
| **G4** | Falso positivo ≤5% em duas execuções de sombra | S6 | Primeiro relatório errado mata a credibilidade e não se recupera | a projeção de ≥36% de 24/08 atribuía o erro ao 12x36, e o 12x36 nunca foi a fonte dele: confiança 0 já o barra. A fonte era a virada de meia-noite, corrigida em 26/08. Segue inalcançável até o S4 rodar contra produção |
| **G5** | Regras homologadas com cliente + jurídico/RH | envio real | Alerta nominal indevido é risco trabalhista | fora da engenharia |
| **G6** | Cláusula de IP assinada | comercializar | Sem ela é projeto sob encomenda, não produto | fora da engenharia |

---

## S0 — Diagnóstico e blindagem · 2–3 dias ✅

**Objetivo:** fechar a exposição de dado pessoal e montar a fundação, sem quebrar
nada que já roda.

| Trilha | Entrega |
|---|---|
| Banco | `scripts/00_diagnostico.sql` rodado e commitado; migrations `00`, `01`, `02` |
| Infra | Exposed schemas reduzido a `public` e `graphql_public` |
| Produto | Redação da cláusula de IP e licenciamento |

Não quebra o worker: `service_role` tem grants próprios e ignora RLS. O frontend
ainda não existe.

**Aceite**

- Nenhuma tabela do espelho legível pela chave pública (a própria migration falha
  se sobrar).
- Advisor do Supabase sem alerta de tabela exposta.
- Tenant `kastro-park` criado com a matriz de sensibilidade populada.

**⚠️ G1** — se a convenção de nomes não for PascalCase, ajustar o predicado das
migrations `00` e `03` antes de aplicar.

---

## S1 — Isolamento e ajuste do worker · 3–5 dias ✅

**Objetivo:** mover o espelho para schema privado e apontar o worker para lá.

| Trilha | Entrega |
|---|---|
| Banco | Migrations `03` e `04` |
| Sincronização | Edge Functions (`sync-cadastro`, `sync-batidas`) apontam para o schema `secullum` — decisão de 22/08/2026, fora do backend Python; `core/tenant.py` injeta `tenant_id` em todo acesso do FastAPI |
| Dados | Cadastrar unidades reais; preencher o mapeamento Departamento → unidade |

**A migration `03` quebra a sincronização.** Ela move o espelho de `public` para `secullum`, e as Edge Functions precisam ser atualizadas junto — só que elas vivem noutro repositório, então "no mesmo PR" deixou de ser possível. É coordenação manual até o código delas ser versionado aqui.

O mapeamento de unidades é trabalho de curadoria com o cliente, não de código. É
onde os ~26% de divergência entre empresa e departamento são resolvidos de uma vez.

**Aceite**

- Ciclo completo de sincronização sem erro.
- Zero colaborador ativo sem unidade, ou fila de pendência de mapeamento visível.
- `public` sem nenhuma tabela.

---

## S2 — Modelo completo e superfície de API · 3–5 dias ✅

**Objetivo:** o resto do modelo e a API pronta para o frontend consumir.

| Trilha | Entrega |
|---|---|
| Banco | Migrations `05` a `11` |
| Banco | Suíte `testar_migrations.sh` no CI |
| Doc | Dicionário de dados regenerado |

**Aceite**

- ~~14 migrations~~ **17** aplicam limpas em banco descartável.
- ~~23 asserções funcionais e 11 estruturais~~ **69 asserções em quatro suítes**
  (jornada 24, alerta e cadência 24, isolamento 21, estruturais 13) passando.
- Views e RPCs respondendo com um usuário de teste autenticado.

**⚠️ G2** — a suíte verde é pré-requisito para qualquer gravação de dado real.

---

## S3 — Jornada esperada · 5 dias · em andamento

**Objetivo:** materializar o que era esperado de cada colaborador em cada dia.
Sem isso, o motor não tem contra o que comparar.

| Trilha | Entrega |
|---|---|
| Backend | `operax/motor/jornada.py` preenche `app.expected_workday` a partir de Horario/HorarioDia e afastamentos |
| Backend | Cálculo do grau de confiança por linha |
| Produto | Relatório de cobertura: % de colaboradores com confiança ≥80 |

**Este é o sprint que decide o cronograma real.** Estacionamento opera em 12x36 e
revezamento. Se `HorarioDia` descreve semana fixa, a escala não cabe e a confiança
despenca.

Se mais de 20% ficar abaixo de 80, entra um sub-sprint de cadastro manual de
escala — trabalho de implantação que precisa estar dimensionado na proposta, não
absorvido em silêncio.

**Aceite**

- `app.expected_workday` preenchida para os últimos 90 dias.
- Percentual de confiança medido e reportado.
- Precedência verificada: afastamento > folga > jornada.

**Andamento em 24/08/2026.** O motor existe: `backend/operax/motor/jornada.py`
materializa a tabela num `insert … select` idempotente, com a precedência
provada. A confiança é escada de três — 100 quando o dia da semana está
declarado ou há afastamento, 50 quando há turno sem hora de entrada, 0 quando o
horário nada diz — e não uma curva, porque a fonte ou está certa ou está ausente.
`make jornada` roda e imprime a cobertura, agrupada **por descrição de horário**,
que é o que separa os dois problemas achados na medição.

`scripts/96_teste_jornada.py` entrou no `make db-test` com 24 asserções e
**extrai o SQL do próprio módulo** em vez de repeti-lo. Pegou um bug na primeira
execução: `translate` rodava antes de `upper`, o "é" minúsculo de "Férias"
escapava da lista de acentos e **toda férias era arquivada como atestado**.

Para escrever isto foi preciso consertar antes o baseline: o `secullum` do banco
de teste era um stub simulado, com colunas que produção não tem e sem sete das
vinte tabelas. `scripts/gerar_baseline_nuvem.py` passou a montá-lo do catálogo
real — o gancho `scripts/_baseline.sql`, que a suíte procurava desde sempre,
nunca tinha sido preenchido.

**O que falta:** rodar contra produção. `app.employee` está com zero linha lá, e
a promoção `secullum → app` não existe em nenhum lugar do repositório.

**⚠️ G3**

---

## S4 — Motor em modo sombra · 5–10 dias · motor entregue, ⚠️ G4 aberto

**Objetivo:** detectar desvio sem publicar nada, e medir o erro.

| Trilha | Entrega |
|---|---|
| Backend | `operax/motor/deteccao.py` conforme a spec |
| Backend | Gravação idempotente com `on conflict` |
| Backend | `operax/motor/revogacao.py` para correção retroativa |
| Produto | Comparativo sombra × apuração do Secullum, com divergências classificadas |

A duração varia porque depende de quantas rodadas de correção forem necessárias.
Uma semana de dados por rodada.

**Aceite**

- Reprocessar o mesmo período duas vezes não altera contagem.
- Toda divergência classificada em escala errada, tolerância errada ou bug.
- Falso positivo ≤5% em duas execuções seguidas.

**⚠️ G4** — nenhum alerta ou relatório sai antes disso.

### Andamento em 24/08/2026 — o motor existe; o gate não fechou

**O que foi entregue.** `backend/operax/motor/regras.py` guarda o cálculo de "o
que é desvio neste dia" como SQL puro, sem driver e sem cópia; `deteccao.py`
grava `app.deviation_event` a partir dele; `revogacao.py` faz a correção
retroativa. `python -m operax.motor` roda os três em ordem — jornada, detecção,
reconciliação — porque detectar contra uma tabela de jornada vazia não dá zero
desvio, dá zero informação.

**Um cálculo, três statements.** O detector escreve a partir de uma definição e a
revogação pergunta duas vezes contra ela. Uma segunda cópia de um `union all` de
trezentas linhas divergiria na primeira mudança de tolerância, e a cópia que
diverge nunca é a que alguém está lendo. Um teste do pytest afirma que os três
começam com `EVENTS_SQL` — se um deixar de derivar dele, a suíte fica vermelha
antes de o motor se contradizer.

**Reprocessar não duplica — e isso precisou de migration.** A migration 05 tinha
índice único só para `mode = 'production'`; a sombra ficou sem nenhum, e é
justamente ela que reprocessa a mesma semana a cada correção de tolerância. Sem
índice para o `on conflict`, a segunda execução inseria uma segunda cópia de cada
evento, e o **falso positivo que decide este gate seria medido contra uma tabela
que dobrava toda vez que alguém acertava uma tolerância**. A migration 18
estende o grão declarado na 05 à sombra e prova o comportamento com um teste vivo
dentro do próprio bloco.

**O que já foi enviado não se reescreve.** O `on conflict do update` carrega um
`where app.deviation_event.report_cycle_id is null`: um indício que saiu num
relatório está na mão de um gestor, e reescrever o número em silêncio é como o
produto perde a discussão que ele existe para ganhar. Esses passam pela
supersessão — revoga e insere apontando para o anterior. E o `do update` copia
`company_id` e `unit_id` de si mesmo: quem mudou de unidade depois não reescreve
onde o fato aconteceu.

**A guarda que segura o 12x36.** `no_punches` exige `workload_minutes` declarado.
Sem ela, todo dia de descanso de quem está numa rotação que o espelho não
descreve viraria um turno perdido — e a enxurrada de falso positivo apareceria
justamente na medição que este gate depende. Não se pode afirmar que alguém
faltou a um turno que ninguém conseguiu descrever. O relatório do motor imprime
os dias cegos ao lado do total pelo mesmo motivo: uma taxa calculada sem esse
denominador parece melhor do que é.

**O que o motor deliberadamente ignora**, nomeado para ser a primeira suspeita
quando um falso positivo aparecer: as bandeiras de dia do próprio espelho
(`"Folga"`, `"Neutro"`, `"Compensado"`) e os campos de abono. A expectativa vem
de `app.expected_workday` e só dela — duas fontes para "este dia era de trabalho"
é uma a mais, e escolher entre elas é decisão de produto. Um teste afirma que
nenhuma delas aparece no `where`.

**Prova.** `scripts/94_teste_deteccao.py` entrou no `make db-test` com 15 pessoas,
uma por caso, e **importa o SQL do motor** em vez de repeti-lo. A asserção que
mais vale não é a contagem: é que o **sinal** de cada indício concorde com a
`direction` declarada em `app.deviation_type` — contar eventos à mão envelhece a
cada tipo novo, e essa pega um sinal invertido em qualquer um dos doze. Dois
achados do cenário: quem sai para o intervalo e não volta tem número **par** de
batidas (a coluna sem hora não é batida), então a regra de paridade da SPEC §3.2
não o pega — quem pega é `break_no_return`; e uma batida `desconsiderada` que
contasse transformaria um dia correto em jornada excedida e par ímpar de uma vez.

**O que falta para o G4 fechar:** dados reais. O gate é "falso positivo ≤5% em
duas execuções seguidas" contra a apuração do próprio Secullum, e isso depende de
`app.employee` estar populado em produção — que é a pendência do S3 e o assunto
de `docs/PLANO-RECONCILIACAO-NUVEM.md`. O motor está pronto para rodar em sombra
no dia em que houver contra o que comparar.

---

## S5 — Dashboard · 7–10 dias ✅

**Objetivo:** a tela. Pode começar em paralelo ao S4 usando dados de sombra.

| Trilha | Entrega |
|---|---|
| Frontend | Projeto Next.js 16 na Vercel, autenticação Supabase |
| Backend | Endpoints FastAPI para dado individual e sensível (`server/routers/`) |
| Frontend | Filtros empresa → unidade → período, estado na query string |
| Frontend | KPIs, tendência, rankings, recorrência, drill-down |
| Frontend | Consulta individual do colaborador |
| Frontend | Monitor diário, com indicador de idade do dado (`fn_data_freshness`) |
| Frontend | Tela de TV, só agregado, sem nome |

**Aceite**

- Dashboard abre em menos de 3 s no período padrão.
- Link com query string abre já filtrado.
- Supervisor de unidade não enxerga outra unidade nem dado sensível — verificado
  na tela, não só no banco.
- Nenhum nome de colaborador na tela de TV.

**Fechada em 24/08/2026 — os quatro com teste.** Três se provam na tela e viviam
no Playwright desde 22/08. O quarto era um número que ninguém media: o orçamento
de 3 s não podia ser aferido contra `next dev`, que compila a rota na primeira
requisição. `E2E_PROD=1` (ou `make e2e-prod`) troca o servidor por build de
produção; medido cinco vezes, **979 a 1516 ms**. A suíte inteira passa nos dois
modos, 16 de 16.

O número é piso, não teto: aqui o Next e o Supabase dividem máquina e o seed é
sintético. O teto continua sendo medido no S8.

---

## S6 — Alertas e relatório consolidado · 5–7 dias · esteira entregue, ⚠️ G4 na frente

**Objetivo:** o produto começa a falar com o gestor.

| Trilha | Entrega |
|---|---|
| Backend | `operax/alertas/outbox.py` enfileira em `app.alert_queue` |
| Backend | `operax/alertas/sender.py` com `skip locked`, backoff e idempotência |
| Backend | `operax/alertas/ciclo.py` monta o ciclo com reserva transacional |
| Backend | Link profundo para o dashboard filtrado |
| Frontend | Tela de configuração de regras e destinos |
| Produto | Homologação das regras com cliente, jurídico e RH |

Toda regra nasce desligada. Rodar primeiro em modo de teste, com destino no
próprio Owner.

**Aceite**

- Reprocessar período não reenvia mensagem.
- Falha de rede não duplica nem perde.
- Regra individual com destino de grupo é rejeitada pelo banco.
- Relatório declara ocorrências de dias anteriores quando houver.
- Custo por mensagem sendo registrado.

**⚠️ G5**

---

### Andamento em 24/08/2026 — a esteira existe e não entrega nada

**O que foi entregue.** `ciclo.py` monta `app.report_cycle` por unidade e reserva
os eventos numa transação; `outbox.py` enfileira em `app.alert_queue` com chave de
idempotência; `sender.py` consome com `for update skip locked`, backoff e
descarte; `provedores/base.py` é o contrato `(template, variáveis, destino)`.

**"Um desvio em exatamente um ciclo" é uma cláusula, não uma convenção.** A
reserva é `update ... where report_cycle_id is null` — quem já está num ciclo não
entra em outro, e reservar duas vezes não move ninguém. E ela **não tem piso de
data**: um desvio detectado tarde é de antes do início do ciclo e tem de entrar,
porque bloqueá-lo derrubaria justamente as ocorrências que o gestor ainda não
ouviu. Daí a frase obrigatória — *"Inclui 3 ocorrências de dias anteriores
detectadas após o último envio"* — que existe porque o painel filtra por data do
fato e o relatório agrupa por ciclo: **os dois números estão certos e são
diferentes**, e sem a declaração o gestor conclui que o sistema está errado.

**O gate G4 é perguntado, não lembrado.** A regra 8 diz que nenhum alerta sai
antes de a sombra fechar. Isso virou uma pergunta ao banco: *este cliente já teve
alguma execução do motor concluída em `mode = 'production'`?* Enquanto o motor só
rodou em sombra, o remetente reserva o lote, registra a tentativa com o motivo em
`app.alert_sent` e **não entrega nada**. Promover o motor é o que abre a porta — e
promover o motor é exatamente o que "a sombra fechou" quer dizer. Um teste roda o
remetente contra as duas respostas.

**O destino em claro na fila, hasheado no log.** `alert_queue.destination` guarda
o número porque o remetente precisa discar; `alert_sent.destination_hash` guarda
só o hash, porque um log de entrega de longo prazo não precisa do telefone de
ninguém para ser útil. E `cost_cents` entra desde o primeiro envio.

**Prova.** `scripts/93_teste_ciclo.py` entrou no `make db-test` e faz duas coisas:
compila **as 15 instruções fixas** dos três módulos contra o schema real — `prepare`
pega coluna errada e join inválido antes de a primeira mensagem sair — e roda o
cenário funcional da reserva, com sete desvios, cada um por um caso: o do período,
o detectado tarde, o já reservado, o de sombra, o revogado e o de uma unidade sem
regra. Mais 21 asserções no pytest.

**O que falta:** as três integrações de WhatsApp e o SMTP. Elas recebem credencial
**por tenant**, do Supabase Vault via `app.integration_secret`, e nenhum tenant
tem uma configurada — montar um cliente HTTP contra uma API que não se consegue
exercitar seria código que só falha na primeira mensagem real. Enquanto isso o
`NullProvider` registra o que teria saído, que é o mesmo comportamento que o gate
G4 impõe de qualquer forma.

---

## S7 — Assistente de IA · 3–5 dias · entregue

| Trilha | Entrega |
|---|---|
| Backend | `operax/agente/` com `create_agent`: pergunta → métrica → execução como o usuário → texto |
| Backend | `POST /assistente/perguntar` com streaming SSE |
| Frontend | Interface de conversa consumindo o SSE via `fetch` + `ReadableStream` |
| Backend | Registro em `app.ai_query`: métrica, parâmetros, latência e tokens |

**Aceite**

- Pergunta fora do catálogo recebe recusa, não número inventado.
- Usuário sem o domínio sensível é recusado antes da consulta.
- Resposta informa período e filtros usados.
- Custo de tokens visível.

---

### Andamento em 24/08/2026 — a metade que decide a segurança

**O que foi entregue.** `catalogo.py` e `executor.py` — a fronteira inteira da
regra 9. O que **não** foi: `agente.py`, o `create_agent` do LangChain, e o
endpoint SSE. A razão está no fim desta seção.

**Por que catálogo em vez de prompt esperto.** Um modelo convidado a escrever SQL
contra um schema que ele viu vai, uma hora, escrever uma consulta sintaticamente
perfeita e semanticamente errada — juntando departamento a empresa, por exemplo,
que é o erro de 26% em torno do qual o modelo de dados inteiro foi desenhado. Um
modelo convidado a escolher entre nove métricas nomeadas só consegue errar de uma
forma: escolhendo a errada entre nove, que uma pessoa lê na tela e corrige. Essa é
a troca, e é por isso que **recusa é resposta válida**.

**Quatro recusas, e todas nomeiam o problema.** Fora do catálogo (com a lista do
que existe), domínio fora de alcance, parâmetro desconhecido (pelo nome) e
período ausente. "Não consigo responder isso" não ensina nada a ninguém; dizer
*qual* parâmetro não foi reconhecido acerta a próxima pergunta.

**O domínio filtra antes de o modelo ver.** Métrica que a pessoa não alcança não
entra no catálogo oferecido. Oferecer e recusar depois confirmaria que existe
dado de folha para quem não pode saber que ele existe — o mesmo raciocínio que
tira a aba da tela em vez de desabilitá-la.

**`BINDINGS` é código, e o `make db-test` é o contrato.** `app.metric` diz o que
cada métrica aceita (dado); `BINDINGS` diz como cada parâmetro alcança o alvo —
coluna e operador para view, nome de argumento para função — e é código porque é
o único ponto em que um nome de coluna encosta em estrutura de SQL. Nenhum valor
do modelo ou do usuário é interpolado: tudo viaja ligado.

`scripts/91_teste_catalogo.py` confere as duas listas uma contra a outra e
**achou três divergências na primeira execução**: `data_freshness` declarava a
dimensão `entity` sem binding; `fn_ranking_by_unit` não tem `p_unit_id` — ela
ordena unidades, e filtrar um ranking de unidades por uma unidade é pedir o
ranking de um item só; e sobrava binding para uma view que nenhuma métrica ativa
usa mais. As três eram invisíveis até alguém fazer a pergunta em produção.

**Por que o agente não foi escrito naquele dia.** Ele precisava do LangChain 1.x
e de um provider real, e nenhum dos dois estava no `pyproject.toml`. Escrever a
fiação de `create_agent` sem conseguir exercitá-la produz exatamente o tipo de
código que parece certo e falha na primeira pergunta.

---

### Andamento em 25/08/2026 — a fiação, e o que a primeira execução real mostrou

**Entregue.** `agente.py` (o `create_agent`, a allowlist de modelo, o turno como
eventos tipados), `POST /assistente/perguntar` com SSE, a tela de conversa, o
registro em `app.ai_query`, o rate limiting por usuário e o provider falso do
E2E. As dependências entraram: `langchain` 1.3, mais os três providers.

**A decisão que valeu a espera foi exercitar antes de fechar.** Cinco perguntas
reais contra um provider real acharam sete coisas que nenhum teste com fixture
acharia. As quatro primeiras com as leituras de banco simuladas:

1. **O modelo inventa valor, não só nome.** Para "quantos desvios tivemos este
   mês?" ele mandou `unit="month"`. As quatro recusas do catálogo passam por
   isso — `unit` é dimensão que a métrica aceita — e a string chegaria a uma
   coluna `uuid`. Virou a **quinta recusa**, `valor_invalido`, e o mapa de tipos
   que o `make db-test` já tinha saiu do script e virou `catalogo.TYPES`, com o
   contrato conferido nos dois lados.

2. **Quando o modelo acerta, o `event: recusa` não dispara.** Perguntado sobre
   folha sem alcançar o domínio, ele recusou sozinho, em prosa, sem chamar
   ferramenta nenhuma. A resposta é boa e a UI não sabe que foi recusa: o
   `app.ai_query` conta a pergunta como respondida, e a lista de "métricas que
   faltam" — que é o principal uso desse registro — nasce errada. O modelo
   ganhou uma segunda ferramenta, `recusar`, e um sexto código, `sem_metrica`.
   O texto que ele produz ali é o melhor insumo que existe para decidir qual
   métrica criar: *"nenhuma métrica retorna média por colaborador"*.

3. **Um filtro descartado virava uma frase falsa.** O modelo mandou `unit` para
   `ranking_by_unit`; o `BINDINGS` descarta (a função **ordena** unidades e não
   tem `p_unit_id`), a consulta rodou sem o filtro, e o modelo respondeu "com
   filtro da unidade Shopping Norte". O número estava certo e a frase em cima
   dele, não. O silêncio no SQL segue de pé — é limitação declarada do alvo —
   mas agora a ferramenta devolve `filtros_aplicados` e `filtros_ignorados`, e
   a tela mostra os dois.

4. **A métrica de contagem não contava.** `deviations_total` apontava para
   `vw_deviation_event`, uma linha por evento, e o assistente lê no máximo 200
   linhas (elas são pagas por token). Contra o seed de desenvolvimento, com 508
   eventos, "quantos desvios tivemos este mês?" responderia **200** — não erro,
   não vazio: um número errado com uma frase confiante na frente. A migration 20
   aponta `deviations_total` e `deviations_minutes` para `fn_kpi_period`, que já
   existia desde a 10 e é o que o KPI do dashboard lê. Hoje a mesma pergunta
   responde 217, que é a contagem. As dimensões `employee` e `type` saíram das
   duas: a função não as aceita, e catálogo que promete o que o alvo não entrega
   produz filtro descartado em silêncio.

**E a primeira execução contra o banco de verdade achou mais duas.** Rodadas as
mesmas perguntas contra o seed de desenvolvimento, com provider real, as cinco
recusaram:

5. **`null` não é valor inválido, é ausência de filtro.** Perguntado por um total
   do mês, o modelo manda `{"unit": null}` — que é como ele escreve "sem filtro
   de unidade". A recusa `valor_invalido` tratava isso como lixo e derrubava a
   pergunta certa, cinco vezes em cinco. `null` e string vazia agora são
   descartados antes de qualquer validação.

6. **O modelo estreita o filtro por conta.** Sem poder filtrar por tipo, ele
   trocava o recorte pedido por outro: "quantos atrasos em agosto?" virava o
   total de uma unidade que ninguém citou — número certo para uma pergunta que
   ninguém fez. Duas coisas seguraram isso: uma regra explícita no prompt e na
   descrição da ferramenta ("só os parâmetros que a pergunta pediu"), e o evento
   `metrica` passando a resolver **nome** de unidade em vez de mostrar o uuid.
   A segunda é a que não depende de o modelo obedecer: `unidade: Shopping Norte`
   numa pergunta que não citou unidade é visível; `unidade: dede0000-…-a1` não é.

**E o E2E achou a sétima.** `expected_time` é `time`, o serializador não
conhecia `time`, e a primeira pergunta contra o banco de verdade morria em
`TypeError` — que o `except` largo do turno mostrava como "falha ao consultar o
modelo". Fixture com `{"total": 42}` nunca alcançaria isso. É a razão de o E2E
do assistente existir com provider falso (`E2E_FAKE_LLM=1`): o que ele prova é
transporte e integração, não a qualidade da frase.

**O que o registro de custo passou a carregar.** `app.ai_query` ganhou a coluna
`model` (migration 19). Token não é preço: os mesmos 10.000 tokens custam um
número num modelo pequeno e outro num grande, o backend é multi-provider de
propósito, e uma tabela de contadores sem o nome do modelo responde "quantos
tokens?" e não responde "quanto custou?", que é para o que a coluna foi criada.

**A lacuna que a migration 20 abriu, de propósito.** Com `fn_kpi_period` no
lugar da view de eventos, o assistente deixou de aceitar filtro por **tipo** e
por **colaborador** nas duas métricas de desvio — a função não os recebe. Não é
perda de capacidade que funcionava: um "quantos atrasos?" contra a view também
batia no teto de 200 e devolvia 200. Hoje a pergunta recebe recusa nomeada. O
que fecha isso é uma métrica de contagem **por tipo**, e ela é uma das três que
a `COBERTURA-ESCOPO.md` já lista como faltando.

Há um efeito colateral que vale registrar como ganho: o que o assistente manda
para o provider virou **agregado**. Antes, uma pergunta de desvio embarcava até
200 linhas nominais — com nome de colaborador — num serviço de terceiro. Duas
métricas ainda fazem isso (`documents_expiring` e `ranking_by_employee`, as duas
com nome de pessoa na saída), e isso **não** foi decidido aqui: fica anotado
como pergunta em aberto, porque a resposta certa pode ser projetar a saída antes
de mandar, e isso muda o que a UI recebe.

**O que continua fora.** Thread de conversa — cada pergunta é um turno só, sem
histórico. Não é limitação de fiação: é escopo que ninguém pediu, e um histórico
enviado a cada turno multiplica o custo por token sem que ninguém tenha pedido a
continuidade.

---

## S8 — Homologação, treinamento e produção · 3–5 dias

| Trilha | Entrega |
|---|---|
| Produto | Roteiro de homologação por funcionalidade |
| Produto | Treinamento dos usuários indicados |
| Produto | Runbook de suporte e escalonamento |
| Infra | Backup testado com restauração real, não só configurado |
| Infra | Monitoramento dos sinais da spec |

**Aceite:** critérios do item 18 da proposta comercial atendidos e homologados
pelo responsável do cliente.

---

## Fase 3 — Folha via Excel, documentos e acordos · a definir

**Não depende mais de acesso ao Domínio.** O escopo decidiu: a v1 é upload de
relatório em Excel. O que destrava a fase é a contabilidade mandar uma planilha
de exemplo — não a Thomson Reuters liberar API.

Entregáveis novos que não existiam em nenhum sprint:

| Trilha | Entrega |
|---|---|
| Produto | Template padronizado publicado (§6 do escopo obriga a contratada a fornecer) |
| Backend | `operax/imports/`: parser, validação de campos obrigatórios, duplicidade |
| Backend | Devolutiva de erro por linha em `app.file_import.report` |
| Frontend | Tela de upload com preview antes de confirmar |
| Produto | **Mapa de código de evento de folha → categoria**, curado com a contabilidade |

O último é bloqueante: sem ele, 8 dos 16 indicadores de 5.3 não saem. É curadoria,
igual ao mapa de unidades, e precisa estar dimensionado como atividade de
implantação — não absorvido em silêncio.

O modelo de dados já existe (migrations `07` e `08`) mas **não foi validado contra
dado real**. Parte vai mudar quando o primeiro layout chegar.

---

## Linha do tempo

```
S0 ██                                                    2–3d   banco + comercial
S1  ████                                                 3–5d   banco + backend
S2     ████                                              3–5d   banco
S3        █████                                          5d     backend   ← decide o cronograma
S4             ██████████                                5–10d  backend
S5             ██████████████                            7–10d  frontend  (paralelo ao S4)
S6                       ███████                         5–7d   backend + frontend
S7                              █████                    3–5d   frontend
S8                                   █████               3–5d   produto
                                                         ─────
                                            total ~33–50 dias úteis
```

A proposta comercial fala em 30 a 45 dias corridos. **Dias corridos e dias úteis
não são a mesma coisa** — 33 a 50 dias úteis são 7 a 10 semanas. O intervalo da
proposta só fecha se S5 correr de fato em paralelo com S4 e se o S3 não exigir
cadastro manual de escala.

Se o S3 revelar que a escala precisa ser cadastrada à mão, isso é escopo adicional
e precisa ser conversado com o cliente **no momento em que for descoberto**, não
no fechamento.

**Revelou, em 24/08/2026 — e o alcance é pequeno.** Sete pessoas em duas unidades,
não a base inteira: o resto está em semana fixa e ela é confiável. É escopo
adicional de qualquer forma, e está sendo dito agora, que é o ponto desta regra.
Outras seis pessoas não precisam de escala nenhuma — precisam sair do motor.

---

## Definition of done

Vale para toda entrega, em qualquer trilha:

1. `make test && make lint` verde. Se tocou banco, policy, view ou grant: `make db-test` também.
2. Dicionário de dados regenerado se o schema mudou.
3. Nenhum dado sensível em view de `public` — verificado pela suíte.
4. Nenhuma consulta com `service_role` sem filtro de `tenant_id` — e `service_role` só existe no backend FastAPI.
5. Vocabulário: *desvio* e *indício*, nunca "hora extra".
6. Pendência que dependa da API do Secullum marcada com ⏳ e listada na spec.
