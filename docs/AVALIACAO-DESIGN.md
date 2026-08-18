# OperaX — avaliação do design entregue

Confronto entre o pacote recebido (`OperaX.zip`) e o que os prompts de
`PROMPT-CLAUDE-DESIGN.md` pediram. Verificado por leitura do código **e** por
renderização real do protótipo: as dependências de CDN foram vendorizadas
localmente, o arquivo foi aberto em navegador e cada tela foi capturada e
medida. Onde há número neste documento, ele veio da medição, não de leitura.

**Veredito: aprova com ressalvas.** Sete das nove telas estão entregues e com
qualidade acima do esperado. As sete regras de produto sobreviveram ao desenho —
inclusive as duas que costumam morrer primeiro. Faltam duas telas, e há quatro
lacunas que atrapalham o handoff para o Claude Code.

---

## 1. Decisão registrada: a paleta fica

O design system entregue chama-se **Aegis** e traz azul `#015DFC` sobre navy
`#111D2D`, com Manrope + JetBrains Mono. Não é a marca EURECA (`#0E0918`,
`#EA4B71`, Orbitron + Inter), e o `readme.md` do pacote registra o porquê: os
assets não foram anexados, então ele montou a partir da especificação escrita.

**Você decidiu manter.** Então isto não é defeito e não entra na lista de
correções. Duas observações que continuam valendo mesmo com a decisão tomada
estão nos itens **D** e **G** adiante — uma é sobre a documentação que viaja
junto com a paleta, a outra é sobre claro vs. escuro.

Vale dizer o que a paleta acerta: violeta para excedente e laranja para faltante
é uma escolha divergente correta. Codifica direção sem transformar todo desvio em
alarme vermelho, e sobrevive às formas mais comuns de daltonismo — o que
vermelho/verde não faria.

---

## 2. As sete regras de produto

Todas passaram. Esta é a parte que mais importa e é a que veio melhor.

| # | Regra | Situação | Evidência medida |
|---|---|---|---|
| 1 | Idade do dado permanente | **Cumprida** | Presente no cabeçalho das 7 telas. No Monitor é o elemento dominante: "Retrato de 08:40 — há 25 minutos", com próxima leitura (09:10) e barra de progresso |
| 2 | Nunca "hora extra" | **Cumprida** | 0 ocorrências no arquivo. Vocabulário é desvio/indício. "Conferir no Secullum" em 2 pontos, mais o rodapé "Registro oficial de jornada permanece no Secullum" |
| 3 | Horário observado, nunca "agora" | **Cumprida** | 0 ocorrências de "agora". A prévia da mensagem lê "entrada registrada às 08:12, prevista 08:00 … Leitura de 08:40", com nota explicando o atraso de até 40 min |
| 4 | Minutos com sinal | **Cumprida** | Violeta = excedente, laranja = faltante, aplicado consistentemente. A tendência diária é um gráfico divergente acima/abaixo do zero — a melhor tradução visual possível da regra |
| 5 | Papel remove, não desabilita | **Cumprida** | Verificado alternando o perfil no protótipo: em Supervisor somem Remuneração, Documentos e ASO, e a navegação perde Folha, Importação e Administração. Zero cadeados, zero "sem permissão" |
| 6 | Escala não confirmada | **Cumprida** | Selo com ícone, repetido em tabela e no monitor, e contabilizado à parte no resumo: "Escala não confirmada · 9 · não geram alerta" |
| 7 | Vazio, erro e dado velho | **Cumprida no código** | Os quatro estados existem. Ressalva no item **E**: dois deles não são alcançáveis clicando |

Dois acertos que vão além do pedido:

- **Regras de alerta.** Grupos aparecem como `INDISPONÍVEL` com o motivo escrito
  na própria linha, mais um aviso âmbar que explica o risco e oferece a saída
  ("Mudar para agregado"). O botão diz **"Salvar desligada"** e a nota abaixo
  reforça "Salvar não liga a regra". A restrição é comunicada antes do erro,
  como pedido — e o desenho não trata o usuário como culpado.
- **Importação.** A duplicidade é detectada **antes** de confirmar, com opção de
  comparar. O erro é por linha, com número, coluna, valor lido e motivo. O
  caminho parcial está resolvido: "Importar as 340 válidas", e logo abaixo a
  consequência — "a competência fica marcada como incompleta até que entrem".

---

## 3. Lacunas

### A. Administração e Painel de TV não existem — prioridade 1

Estão na navegação, mas renderizam **página em branco**. Medido: 378 e 376
caracteres de texto, que é só o cabeçalho. Sete das nove telas foram entregues.

O problema não é a contagem, é *quais*. São exatamente as duas que carregavam
restrição:

- **Administração** contém a curadoria do mapeamento origem → unidade. É onde os
  ~26% de colaboradores com vínculo ambíguo são resolvidos, e o prompt pedia que
  fosse desenhada para resolver 200 itens numa sessão. Sem essa tela, a
  implantação não tem por onde começar.
- **Painel de TV** é a tela de acesso coletivo, onde vale a regra mais dura do
  produto: **nenhum nome de colaborador, em hipótese alguma**. Uma regra que não
  foi desenhada é uma regra que o Claude Code vai descobrir sozinho — ou não.

### B. O catálogo de métricas do assistente não bate com o banco — prioridade 1

A tela do assistente exibe dez códigos em português e afirma "14 métricas
registradas". O banco tem **nove**, em inglês. **Nenhum dos dez existe.**

| Na tela | No banco |
|---|---|
| `desvio_minutos_abs` | `deviations_minutes` |
| `desvio_eventos` | `deviations_total` |
| `ranking_unidade` | `ranking_by_unit` |
| `ranking_colaborador` | `ranking_by_employee` |
| `recorrencia_dias` | `recurrence` |
| `presenca_dia` | — não existe |
| `saldo_periodo` | — não existe |
| `folha_total` | — não existe |
| `custo_medio_colaborador` | — não existe |
| `encargos_periodo` | — não existe |
| — | `daily_trend`, `documents_expiring`, `payroll_summary`, `data_freshness` |

Isso importa mais do que parece. O catálogo fechado é o mecanismo que impede o
assistente de inventar número: fora dele, a resposta é "não tenho esse dado". Se
a tela promete cinco métricas que não existem, ela está prometendo respostas que
o produto vai recusar — e a recusa, que foi bem desenhada, vai parecer defeito.

**Decidido:** a tela mostra as **9 ativas** e mais **4 previstas em estado
desabilitado**, com o motivo escrito. `folha_total` sai da lista — já é servida
por `payroll_summary`. As quatro previstas ganham código em inglês desde já, para
que a migration que as registrar não precise renomear nada:

| Código previsto | Rótulo | Travado em |
|---|---|---|
| `attendance_daily` | Presença por dia | — em desenvolvimento |
| `hour_balance` | Saldo de horas no período | decisão: espelhar do Secullum ou calcular |
| `cost_per_employee` | Custo médio por colaborador | mapa código de evento → categoria |
| `payroll_charges` | Encargos por período | mapa código de evento → categoria |

Duas delas estão travadas em decisões que ainda são suas (as mesmas listadas em
`COBERTURA-ESCOPO.md`). O chip desabilitado carrega o motivo justamente por isso:
um "em breve" mudo parece defeito, um "em breve" com motivo é roadmap.

### C. O design system cobre um quarto da superfície — prioridade 2

O DS tem 16 primitivos. O protótipo usou 11 deles, 78 vezes. E usou **237 divs
com estilo inline e 5 `<table>` cruas** para todo o resto.

Nunca usados: `Card`, `CardHeader`, `Tooltip`, `DateField`, `ExposureCard`.

Não existem, e fizeram falta: **Table** (a espinha dorsal do produto), **Chart**
(barra divergente, tendência, ranking — todos improvisados à mão), **Drawer**,
**Tabs**, **EmptyState**, **Toast**, **Skeleton**, **Pagination**.

Consequência prática: no handoff, o Claude Code não tem tabela canônica nem
gráfico canônico para partir. Ele vai escrever os dois, tela a tela, e eles vão
divergir. A tabela do dashboard, a do monitor e a de custo por unidade já são
três implementações diferentes no protótipo.

### D. O readme do DS descreve outro produto — prioridade 2

Mesmo mantendo as cores, este arquivo viaja junto no handoff. E ele diz que o
sistema é de **monitoramento operacional de equipamento**: modelo de dados com
`equipamentos`, `severity`, `exposure_hours`; papéis Admin, Gestor, Operador,
Visualizador; tela principal "Visão Executiva"; vocabulário Alarme/Anomalia,
Crítica/Alta/Normal, Aberto/Em análise/Resolvido.

Nada disso é OperaX. Nosso modelo tem `deviation_event`, `expected_workday`,
`employee`; nove papéis; quatro domínios sensíveis. Um agente que ler esse readme
para se orientar vai construir contra a especificação errada.

A paleta fica; o texto que a acompanha precisa ser reescrito para o OperaX.

### E. Dois estados existem, mas não dá para vê-los — prioridade 3

"Dia sem ocorrência" e "Dado atrasado" estão implementados — inclusive bem, com
texto próprio ("Duas sincronizações consecutivas falharam. Marcações após 07:12
ainda não chegaram: uma unidade pode parecer sem ocorrência apenas por falta de
dado"). Mas são **prop**, não estado da interface: não há controle no protótipo
para alcançá-los.

No canvas do Claude Design você alterna a prop e vê. No arquivo exportado —
que é o que vai para o cliente e para o Claude Code — o estado que a regra 7
chama de caminho principal é invisível. Basta um seletor de cenário no cabeçalho,
ao lado do seletor de papel que já existe e funciona.

### F. Contraste reprova em cinco pares no tema claro — prioridade 2

Medido em WCAG sobre os tokens do DS. O tema escuro está saudável; o claro, que
é o que está renderizando hoje, tem problemas:

| Token | Sobre | Atual | Sugerido | Depois |
|---|---|---|---|---|
| `--alert-foreground` `#D48E02` | `#FFF6E6` | **2,55:1** reprova | `#996601` | 4,60:1 |
| `--foreground-quaternary` `#9E9E9E` | `#FFFFFF` | **2,68:1** reprova | `#767676` | 4,54:1 |
| `--accent-orange` `#F55902` | `#FFFFFF` | 3,33:1 só texto grande | `#CE4B02` | 4,53:1 |
| `--bad-foreground` `#D40202` | `#FFCCCC` | 3,88:1 só texto grande | `#C10202` | 4,50:1 |
| `--good-foreground` `#029602` | `#DCFFDC` | 3,61:1 só texto grande | `#028402` | 4,50:1 |

O primeiro é o mais sério: `--alert-foreground` é o token do estado "Atrasado" e
do aviso de dado velho. É o texto que precisa ser lido justamente quando algo
está errado, e hoje ele reprova até para texto grande.

As sugestões preservam o matiz — só escurecem o suficiente para passar. A
identidade não muda.

### G. O tema claro fica como padrão — decidido

O prompt original pedia escuro. O protótipo não define `data-theme`, então
renderiza claro — e **essa é a decisão**: claro fica como padrão, combinando com
o "premium corporativo" que o DS descreve. O tema escuro continua existindo como
alternativa, sem seletor na interface.

Consequência prática: as correções de contraste do item **F** passam a ser
obrigatórias, não opcionais. O tema escuro está saudável; era o claro que tinha
os cinco pares reprovando, e agora é o claro que todo mundo vai ver.

---

## 4. O que está seguro

Verificado explicitamente, porque foi restrição declarada:

- **Nenhum CPF, RG ou PIS** gerado, em nenhuma tela. Zero ocorrências.
- Nomes de pessoa obviamente fictícios (Marisol Tavares, Ubirajara Lins,
  Genoveva Amarante, Bartolomeu Fróes). Unidades plausíveis e genéricas.
- Nenhum telefone real; o único e-mail é `renata.guimaraes@kastropark`.
- Ordens de grandeza respeitadas: 182 colaboradores, 6 unidades, 43 ocorrências
  no dia, desvios entre 3 e 52 minutos.
- Sem emoji, em nenhuma superfície.
- Aderência a token é alta: 830 usos de `var(--…)` contra 2 hex crus.

---

## 5. Correção de banco feita nesta rodada

A auditoria da tela do assistente expôs um defeito nosso, não do design: a
passada de renomeação pt→en tinha traduzido **strings de exibição**, não só
identificadores. Quatro rótulos que aparecem na interface estavam quebrados.

- `Ranking de desvios por unit` → `por unidade`
- `Ranking de desvios por employee` → `por colaborador`
- `Valor total, por company e unit` → `por empresa e unidade`
- Dica do erro de alerta: `Exposição nominal de employee em grupo` → `de colaborador`
- Filtro `dias` → `days_ahead`, alinhado aos demais

Duas verificações novas entraram na suíte para que não volte:

- **Verificação 12** — toda `app.metric.target_view` aponta para view ou RPC que
  existe. Se apontar para o nada, a pergunta vira erro em vez de "não tenho esse
  dado", que é justamente o que o catálogo fechado existe para evitar.
- **Verificação 13** — nenhum `title`/`description` de métrica carrega
  identificador em inglês no meio de frase em português.

Ambas testadas por negativo: reintroduzi cada defeito e confirmei que a suíte
acusa. Suíte completa verde, agora com 13 verificações estruturais.

---

## 6. Prompts de correção

Estão em arquivo próprio, prontos para colar bloco a bloco:
**`docs/PROMPT-CLAUDE-DESIGN-CORRECOES.md`**.

São cinco blocos, precedidos de um bloco que declara o que **não** é para
corrigir — a paleta Aegis e o tema claro, ambos decididos. Sem esse bloco de
abertura, a primeira coisa que o Claude Design faz é "consertar" a marca.

| # | Correção | Prioridade |
|---|---|---|
| 1 | Administração e Painel de TV | trava a entrega |
| 2 | Catálogo de métricas real, 9 ativas + 4 previstas | trava a entrega |
| 3 | Table, Chart, Drawer e o resto do design system | alta — define a qualidade do handoff |
| 4 | Readme do DS e seletor de cenário | média |
| 5 | Cinco tokens de contraste no tema claro | média — obrigatória, já que o claro é o padrão |

## 7. Depois das correções

Peça o **handoff para o Claude Code** e traga o pacote. Deste lado já existem o
schema com as views e RPCs que alimentam cada tela, o dicionário de dados gerado
por introspecção e o `CLAUDE.md` com as regras de arquitetura — o handoff entra
neste repositório, não num projeto novo.
