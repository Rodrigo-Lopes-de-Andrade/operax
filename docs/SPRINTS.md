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
| S7 · Assistente de IA | não começou |
| S8 · Homologação e produção | não começou |

**Números que mudaram desde que este plano foi escrito.** São **17 migrations**
(entraram a `11b`, que renomeia o schema da nuvem de pt para en, a `15` do
rebrand FastPark e a `16` de RH). A suíte de banco tem **quatro** conjuntos:
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

## Gates — pontos onde a sprint seguinte não começa

Não são recomendações. Cada um existe porque violá-lo custa mais caro do que
esperar.

| Gate | Condição | Bloqueia | Por quê | Estado em 24/08 |
|---|---|---|---|---|
| **G1** | Diagnóstico rodado e convenção PascalCase confirmada | S0 | As migrations 00 e 03 selecionam por essa convenção | ✅ |
| **G2** | Suíte de isolamento verde | S3 | Motor grava dado real; RLS errada vira vazamento | ✅ e agora provado também por HTTP |
| **G3** | Jornada esperada com ≥80% de confiança | S4 | Sem escala correta, o motor é gerador de falso positivo | número medido em **83,5%** contra o espelho de produção; falta o motor produzi-lo, o que depende da promoção `secullum → app` |
| **G4** | Falso positivo ≤5% em duas execuções de sombra | S6 | Primeiro relatório errado mata a credibilidade e não se recupera | inalcançável até o S4 existir; a medição de 24/08 projeta **≥36%** enquanto as 7 escalas 12x36 não tiverem fonte |
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

## S7 — Assistente de IA · 3–5 dias

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
