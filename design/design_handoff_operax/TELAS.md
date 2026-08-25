# Telas — especificação

Medidas em px. Onde há token, use o token. Cópia entre aspas é final.

## Chrome (todas as telas)

**Sidebar** — 264px, fundo `--surface-sidebar` (cinza `#5A5A5A`, Pantone 425 C),
padding 22/18. Marca no topo: símbolo FastPark em SVG inline
(`viewBox="0 0 269.8 257.1"`, moldura `#FF8C00` + sorriso branco), 32px de altura,
ao lado o wordmark "Fast" `#FFFFFF` + "Park" `#FF8C00`, 21px/700, tracking −0.2px.
O mesmo par símbolo+wordmark aparece no login do celular (34px) e no cabeçalho do
celular (26px). Mínimo digital de 35px de largura para o conjunto; abaixo disso,
símbolo sozinho.
Grupos de nav com eyebrow 11px/700 uppercase em `rgba(231,237,245,0.4)`:

- **Operação** — Gestão de ponto (`layout-dashboard`) · Monitor diário (`activity`,
  badge com a contagem do dia) · Consulta individual (`user-round`) · Assistente
  (`sparkles`)
- **Custo de pessoal** — Folha e custo (`wallet`) · Importação (`file-up`).
  **Não existe para supervisor de unidade.**
- **Configuração** — Regras de alerta (`bell-ring`) · Administração (`shield`) ·
  Painel de TV (`monitor`). Supervisor vê só o Painel de TV.

Item: altura 42, padding 11/14, gap 12, raio `--radius-md`; ativo = fundo `--brand`,
texto `#fff`, peso 700; inativo = `rgba(231,237,245,0.72)`, peso 500.
Rodapé: avatar + e-mail truncado + chip do papel em `--categorical-2` sobre
`rgba(64,127,252,0.16)`.

**Cabeçalho** — altura mínima `--header-height` (84), fundo `--surface-card`, borda
inferior `--border-subtle`, padding 16/28. À esquerda: tile 44×44 `--brand-soft` com o
ícone da tela, título 24px/800 e subtítulo 14px `--text-muted`. À direita, nesta ordem:

1. **Indicador de idade do dado** — pílula com ponto 8px, título tabular e nota.
   Normal: fundo `--surface-muted`, ponto `--good-foreground`, "Dados de 08:40 · há
   25 min" / "Sincroniza a cada 30 min". Atrasado: fundo `--alert-background`, borda e
   texto `--alert-foreground`, "Dados de 07:12 · há 1h52" / "Sincronização atrasada —
   2 execuções falharam".
2. **Seletor de cenário** — Select pílula 250px: dia com ocorrências · dia sem
   ocorrência · dado atrasado. É andaime de demonstração, não vai para o produto.
3. **Seletor de papel** — SegmentedControl sm: DP / Financeiro · Supervisor de unidade.
4. **IconButton** `bell` com badge 3.

Conteúdo: `overflow-y:auto`, padding 24/28/40, largura máxima 1440 (1180 na consulta
individual, 1240 no assistente e na importação, 1340 na folha e nos alertas).

## 1. Gestão de ponto

Objetivo: em cinco segundos responder se o dia está normal e, se não, onde.

**Barra de filtro** — card com tile `sliders-horizontal` e rótulo "Recorte": Select de
empresa, unidade, departamento, gestor; SegmentedControl de período (hoje · 7 dias ·
30 dias · mês atual); botões "Limpar" (ghost) e "Aplicar" (primary). Abaixo, linha
"Filtros ativos" com chips removíveis (28px, pílula, borda `--border-default`, "x" à
direita) e a URL do recorte em mono `--text-faint` — o estado vive na URL.

**KPI (hierarquia deliberada, não doze números iguais)**
- Grade 3 colunas: `KpiCard` "Ocorrências no recorte" (43, accent alert) ·
  card de minutos · `KpiCard` "Pendentes de justificativa" (12, accent bad).
- O card do meio: eyebrow "Minutos em desvio", número 32px/800 tabular (1.284), barra
  empilhada 8px com 58% `--accent-violet` (teal) e 42% `--accent-orange` (laranja queimado), legenda
  "Excedente +742" / "Faltante −542".
- Faixa secundária: seis contagens de baixo peso (Ativos 182 · Presentes hoje 168 ·
  Ausentes 6 · Férias 5 · Afastados 3 · Saldo consolidado +12h40) em card único
  dividido por bordas, rótulo eyebrow e valor 20px/700.

**Tendência diária** — `Chart type="diverging"`, 14 dias, zero no meio, excedente
acima em teal, faltante abaixo em laranja queimado, legenda própria, altura 220.

**Recorrência** — lista de quem teve desvio em 3+ dias na janela: tile tabular com o
número de dias em `--alert-background`, nome, "unidade · N eventos", `chevron-right`.
Clique vai para a consulta individual.

**Três rankings** — `Chart type="rankbar"` em grade de 3: por unidade, por colaborador,
por gestor. Valor formatado "412 min".

**Ocorrências** — `Table`. Cabeçalho da seção com tile `list`, título, Badge "43 no
recorte", SegmentedControl de direção (todos · faltante · excedente · sem par) e
"Baixar XLS". Colunas: Observado (hora mono + data) · Colaborador (nome + unidade ·
matrícula, ordenável) · Tipo de desvio (texto + selo "escala não confirmada" quando
for o caso) · Previsto (mono) · Registrado (mono) · Minutos (sinal, cor por direção,
sub com a direção, ordenável) · Situação (Badge pendente/justificado/não contabilizado).
Linha inteira clicável → Drawer. Rodapé: `Pagination` (43 registros, 25/50/100) e a
frase "Registro oficial de jornada permanece no Secullum. A plataforma aponta indícios."

**Cenário sem ocorrência** — `EmptyState` tone good, ícone `check-check`: "Nenhum
desvio no recorte" + "182 colaboradores previstos, 182 dentro do previsto. A detecção
rodou às 08:40 e cobriu todas as 6 unidades — este é um resultado, não ausência de
dado." Ações: "Ver últimos 7 dias", "Abrir monitor diário".

## 2. Monitor diário

Tela de plantão. O elemento mais importante é a idade do dado.

**Faixa de leitura** — card com tile `radio`, "Retrato de 08:40 — há 25 minutos" 20px/700
e a explicação de que tudo na tela é o que a origem tinha naquele instante; à direita
"Próxima leitura 09:10" com barra de progresso 6px. No cenário atrasado a faixa vira
`--alert-background` com `cloud-alert`, "Retrato de 07:12 — há 1h52" e o aviso de que
uma unidade pode parecer sem ocorrência apenas por falta de dado.

**Resumo** — quatro cards: Fora do previsto 14 (bad) · Dentro do previsto 162 · Sem
marcação 6 (alert) · Escala não confirmada 9 (muted, "não geram alerta").

**Grupos por unidade** — um card por unidade com exceção. Cabeçalho: nome, Badge "N
fora do previsto", "31/34 presentes". Corpo: `Table density="compact"` com Colaborador
(ponto de estado 8px + nome + cargo · escala + selo de escala não confirmada) ·
Situação da jornada (Badge: dentro do previsto · atrasado · em intervalo · intervalo
estourado · não retornou · sem marcação) · Entrada (mono) · Intervalo (mono, "12:30 →
13:47") · Diferença (sinal + rótulo do tipo). Linha clicável → Drawer.

**Dentro do previsto** — botão tracejado que expande a lista dos 162 sem exceção. Os
normais ficam colapsados por padrão: o olho cai no que não está normal.

**Cenário sem ocorrência** — `EmptyState` `shield-check`: "Nada fora do previsto às
08:40".

## 3. Consulta individual — duas variantes

**Cabeçalho do colaborador** — avatar lg, nome 28px/800, "cargo · unidade ·
departamento · matrícula", SegmentedControl de período; faixa inferior com jornada
contratada, gestor, admissão, situação.

**Indicadores** — quatro cards: eventos no período, minutos, dias com desvio,
pendentes de justificativa.

**Histórico de marcações** — `Table density="compact"`: Data (dia + dia da semana) ·
Marcações (mono, "06:58 · 12:30 · 13:47 · —") · Desvio (sinal com cor de direção,
"folga" em `--text-faint`).

**Desvio por tipo** — `Chart type="rankbar"`, valor "4 · 326 min".

**Saldo de horas** — número 32px/800 em teal, nota "Indício consolidado pela
plataforma. A apuração válida é a do sistema de ponto.", botão "Conferir no Secullum".

**Justificativas** — lista com data mono, texto, autor e Badge de status.

**Bloco sensível (só DP / RH)** — grade de dois: histórico de remuneração (desde ·
motivo · valor) e documentos e exames (item · vencimento · Badge). Para supervisor de
unidade **esses dois cards não são renderizados** — nada de cadeado, nada de cinza, e o
resto da tela não muda de layout.

## 4. Assistente

**Conversa** — pergunta do usuário em bolha `--brand`, raio 18/18/4/18, máx. 70%.
Resposta em card com o texto à esquerda e, quando houver número, um painel de 250px
`--surface-muted` à direita com o valor 32px/800 e barras — texto e número no mesmo
card, não dois produtos empilhados. Cursor piscante 8×17 durante o streaming.

**Proveniência** — barra inferior de cada resposta, fundo `--surface-muted`: métrica,
período e filtros em mono, com o **código real** da métrica
(`deviations_minutes · direção faltante`), mais "Ver no dashboard".

**Duas recusas de natureza diferente, ambas resposta válida e não erro:**
- *Domínio sensível* — "qual o atestado médico mais frequente?" → não tenho esse dado,
  motivo de afastamento é informação de saúde e a plataforma não captura; proveniência
  "nenhuma — domínio sensível, fora do catálogo".
- *Métrica prevista* — "qual o custo médio por colaborador no Aeroporto?" → ainda não
  respondo isso; depende do mapa de eventos de folha, que não foi definido;
  proveniência "cost_per_employee · prevista, indisponível".
Cada recusa oferece três sugestões que o catálogo responde.

**Catálogo (barra lateral 300px)** — "9 métricas ativas · 4 previstas". Ativas, com
código em `--brand` e rótulo: `deviations_total`, `deviations_minutes`,
`ranking_by_unit`, `ranking_by_employee`, `daily_trend`, `recurrence`,
`documents_expiring`, `payroll_summary`, `data_freshness`. Sob "Em breve", quatro
cards tracejados desabilitados **com motivo** — `attendance_daily` (em
desenvolvimento), `hour_balance` (depende de definição da fonte),
`cost_per_employee` e `payroll_charges` (dependem do mapa de eventos de folha).
Chip desabilitado sem motivo parece defeito.

## 5. Folha e custo

Sóbria, não vistosa. Folha total 40px/800, variação vs. competência anterior,
KPIs de encargos, custo médio e rotatividade, evolução mensal de 12 meses,
movimentação (admissões/desligamentos), desvio contra a média histórica em texto, e
`Table` de custo por unidade (colaboradores, proventos, encargos, custo médio,
variação com sinal), com "Baixar XLS".

**Competência não importada** — `EmptyState compact` `calendar-clock`: "Competência
08/2026 ainda não importada" + "O relatório da contabilidade chega entre o 5º e o 8º
dia útil. Os números abaixo são de 07/2026 e não incluem o mês corrente." Ações:
"Importar competência", "Ver 07/2026". Os números continuam visíveis abaixo, rotulados.

## 6. Importação de folha

**Quatro passos** — competência · arquivo · preview e validação · confirmar. Passo
concluído com fundo `--good-background`, atual em `--brand`, futuro em
`--surface-muted` com texto `--text-faint`; cada passo mostra o valor já escolhido.

**Duplicidade antes de confirmar** — faixa `--alert-background`: "Competência 07/2026
já foi importada em 08/08/2026", explicando que confirmar substitui os valores e que o
histórico anterior fica registrado e pode ser restaurado. Ação "Comparar".

**Resumo** — linhas lidas 352 · válidas 340 · com erro 12 · total de proventos, cada um
com nota.

**Erro parcial, que é a tela** — `Table density="compact"`: Linha (mono, em
`--bad-foreground`) · Coluna (mono) · Valor lido (mono, mostrando o valor sujo,
inclusive o espaço à direita) · Motivo em português. Rodapé com as três saídas:
"Importar as 340 válidas" (primary), "Corrigir a planilha e reenviar", "Baixar modelo
padronizado", mais o aviso de que a competência fica marcada como incompleta.

**Importações anteriores** — `Table`: competência · arquivo · enviado por · quando ·
estado (completa / parcial).

## 7. Regras de alerta

**Lista (esquerda)** — nome, Badge de conteúdo (individual/agregado), detalhe
(limiar · janela · canal), destinatários, `Switch` e o estado em eyebrow. Nota fixa:
"Toda regra nasce desligada. Ligar é um ato deliberado do administrador do tenant,
registrado na trilha de auditoria." No mock, três de sete ligadas.

**Editor (direita)** — tipo de ocorrência, canal, limiar, janela; escolha de conteúdo
em dois cards de rádio com exemplo de mensagem real; lista de destinatários com
Checkbox.

**A regra de ouro, comunicada antes do erro:** com conteúdo **individual**, os
destinatários de grupo aparecem desabilitados, com fundo `--surface-muted` e a nota
"Grupo — não recebe conteúdo individual"; acima da lista, "somente pessoas — grupos não
recebem conteúdo individual". Um aviso explica que expor nome de colaborador em grupo
é risco trabalhista e oferece "Mudar para agregado" — explicação, não punição. O banco
recusa; a interface explica antes.

**Prévia da mensagem** — o texto exato que sai no canal, individual ou agregado.

### Canal de WhatsApp — três provedores

O tenant tem **no máximo um provedor ativo**, escolhido na aba Integrações:

- **Meta Cloud API** (oficial) — número verificado, exige **template aprovado** com
  variáveis numeradas, sem risco de banimento, 2 a 5 dias para subir.
- **Z-API** e **Uazapi** (não oficiais) — ponte sobre o WhatsApp Web, conectam por
  **QR Code**, aceitam texto livre, sobem em 15 minutos; em troca **o número do
  cliente pode ser banido pela Meta, sem recurso**. O desenho informa isso no
  momento da escolha, sem dramatizar e sem esconder.

Com provedor oficial, a mensagem **é um template, não um texto**. A tela de regras
mostra, por regra: o código do template em mono, o estado com Badge — *rascunho ·
em análise · aprovado · reprovado · pausado* — e, no editor, o corpo do template com
as variáveis numeradas destacadas (`{{1}}`…`{{6}}`) mais a legenda de cada uma. Para
template reprovado, o **motivo** da Meta aparece na íntegra.

**O pior estado do produto, agora desenhado.** Regra ligada + provedor oficial +
template não aprovado = a Meta descarta a mensagem e **não devolve erro**: o alerta
não chega e nada aparece no painel. Três camadas cobrem isso:

1. faixa no topo da lista de regras — "1 regra ligada sem template válido — os
   alertas estão sendo descartados";
2. na linha da regra, aviso com o template, o estado e a contagem de alertas
   perdidos desde a data;
3. no editor, bloco em tom `bad` com duas saídas: "Enviar template para aprovação" e
   "Desligar a regra até aprovar".

Regra cujo template está **reprovado ou em rascunho não pode ser ligada**: em vez do
Switch, a linha mostra o chip "bloqueada · sem template válido". Isto substitui o
erro do banco por explicação antes da ação — mesma lógica da restrição de grupo.

Com provedor não oficial, o gate de template desaparece (texto livre) e a prévia diz
que o que está na tela é exatamente o que sai. A aba Integrações mantém a tabela de
templates do tenant apenas quando o provedor é oficial.

## 8. Administração

`Tabs`: Mapeamento origem → unidade (47) · Unidades (6) · Usuários e papéis (14) ·
Integrações · Auditoria.

**Mapeamento — desenhado para resolver 200 itens numa sessão**
- Faixa: "47 de 182 colaboradores com vínculo não validado", explicando que a origem
  entrega empresa e departamento ambíguos para 26% do quadro, que a curadoria é feita
  uma vez, e que o vínculo não validado não entra no consolidado de custo. Barra de
  progresso 74% e ação em lote "Aplicar sugestões ≥ 90%".
- Filtro: não validados · validados · todos, com contagem.
- Atalhos de teclado visíveis: ↑↓ percorre · Espaço marca · Enter aplica a sugestão ·
  Shift+Enter aplica e avança.
- Barra de seleção (aparece com 1+ marcado, fundo `--brand-soft`): "N selecionados",
  "Aplicar sugestão e validar", "Atribuir unidade manualmente", "Limpar seleção".
- `Table density="compact" stickyHeader`: Checkbox · Origem (código + fonte) ·
  Colaborador (nome + matrícula) · Sugestão (unidade + departamento, ou o chip "Sem
  sugestão") · Confiança (barra + %; ≥90 verde, ≥70 alerta, abaixo bad) · Estado
  (Badge "Não validado" alert / "Validado" good) · ação ("Aplicar" primary quando a
  confiança é alta, "Atribuir" secondary quando não há sugestão; validado mostra quem
  validou e quando).
- `Pagination` 47 registros. `Toast` tone good após ação em lote, com "Desfazer".
- O item não validado nunca parece resolvido: badge alert permanece até alguém
  confirmar explicitamente.

**Unidades** — `Table`: unidade · código de origem (mono, é o que casa com o relógio) ·
cidade · gestor · colaboradores · estado.

**Usuários e papéis** — `Table`: usuário (nome + e-mail) · papel (Badge) · escopo ·
domínios sensíveis alcançados · último acesso. Nota: são nove papéis e a diferença
entre eles é o que existe na tela, não o que está desabilitado.

**Integrações** — três cards (Secullum · ponto, WhatsApp · alertas com o provedor ativo,
planilha de folha); o bloco **Provedor de WhatsApp** com as três opções em cards de
rádio, a nota de risco derivada da escolha e a tabela de templates do tenant (só no
provedor oficial)
com número em destaque e nota; tabela de execuções de sincronização (execução ·
escopo · registros lidos · novos desvios · duração · estado completa/parcial/falha),
com a execução em andamento representada por `Skeleton` e "Executar agora".

**Auditoria** — `Table` somente leitura: quando · quem · ação · entidade (mono) ·
detalhe. Registra consulta a dado sensível, mudança de regra, validação de vínculo,
reexecução de sync e importação.

## 9. Painel de TV

Lido a 4 metros. **Somente agregado — nenhum nome de colaborador em hipótese alguma**,
porque é tela de acesso coletivo. A frase aparece na própria tela.

- Fundo `#0B1220`, raio 24, padding 40/44. Alto contraste para sala com luz natural:
  texto `#F5F7FA` e `#B8C6DC`, apoio `#7FA0C8`.
- **Nada abaixo de 24px.** Eyebrow 24, título 52, nome de unidade 30, número principal
  64, hora da última leitura 80 em mono/800. No cenário atrasado a hora fica
  `#FDAD0D` com "atrasado há 1h52 · duas execuções falharam".
- **Bloco 1** — grade 3×2 de unidades: ponto de estado 14px, nome, "31 / 34 previstos",
  contagem de ocorrências colorida (verde 0, alerta 1–3, bad 4+).
- **Bloco 2** — ocorrências do dia por tipo (`Chart type="rankbar"` com rótulo 28px,
  valor 30px, barra 16px, trilha `rgba(255,255,255,0.1)`), últimos 7 dias em
  `Chart type="trend"` com grade `rgba(255,255,255,0.12)`, e alertas prioritários
  agregados por unidade (número 44px + título 28px + nota 24px, borda esquerda 6px na
  cor do tom).
- **Rotação automática** a cada 12 s, com "Bloco 1 de 2" e dois pontos clicáveis no
  rodapé — é assim que cabe tudo sem reduzir fonte.
- Cenário sem ocorrência: um único alerta "Nenhuma ocorrência aberta · Todas as
  unidades dentro do previsto na leitura das 08:40".

## 10. Alerta no celular — o destino do link (390 × 844)

Não é o produto responsivo: é **uma superfície nova**, com um propósito único.
O alerta sai por WhatsApp com o recorte na query string
(`app.fastpark.com.br/ponto?un=shopping-norte&per=hoje&ev=4821`) e abre no telefone do
gestor. As nove telas de desktop continuam desktop.

Quem está do outro lado é o **papel mais restrito** — supervisor de unidade. Nesta
superfície remuneração, documento de identidade e exame ocupacional **não existem**.
A variante restrita é a principal aqui.

Tipografia e alvos: corpo 14–17px, número do desvio 18–26px, nenhuma área de toque
abaixo de 44px, botão de ação 52px. Cor **nunca sozinha**: o sinal (`+`/`−`) e a
palavra (*faltante* / *excedente* / *sem par*) acompanham o matiz, porque em tela
pequena, no sol, cor é sugestão.

### 1. Chegada — ocorrências no recorte do link

- Barra do app em navy (status bar clara), com uma **única** saída para o resto do
  produto: "no computador".
- Faixa **Recorte do link** em `--brand-soft`: "Shopping Norte · hoje". Ele chegou
  por link, não navegou até aqui — precisa saber que vê um pedaço.
- **Idade do dado, logo abaixo e não escondida**: "Dados de 08:40 · há 25 min" +
  "A leitura roda a cada 30 min. O que você vê é o retrato de 08:40." No cenário
  atrasado a faixa vira `--alert-background` e explica as execuções que falharam.
  Em tela pequena a tentação é virar ícone; aqui ela ocupa uma faixa inteira.
- Lista ordenada pelo que exige ação primeiro. Cada item: ponto de estado, nome
  (17px/700), minutos com sinal (18px/800) na cor da direção, tipo de ocorrência,
  a palavra da direção, e **registrado × previsto lado a lado** em dois blocos mono
  de peso igual. Escala não confirmada aparece como selo tracejado com "não gera
  alerta".
- Cabeçalho da lista com contagem: "Ocorrências 4 · 3 pendentes".

### 2. Detalhe da ocorrência

Versão de celular do Drawer do desktop. Voltar 44px, nome e matrícula; card do
indício com a frase do horário observado, o número grande com sinal e a palavra;
nota de que foi detectado na leitura e que **o alerta pode chegar até 40 minutos
depois do fato**; sequência de marcações do dia (mono, com a saída "ainda não
registrada"); e a lembrança de que a apuração oficial é do sistema de ponto.

**Zona do polegar**, fixa no rodapé: "Registrar justificativa" (primary, 52px) e
"Conferir no Secullum" (secondary, 48px). Nunca no topo.

### 3. Justificar

Motivos frequentes como chips de atalho (Trânsito · Atestado · Autorizado pelo
gestor · Falha do relógio), campo de texto livre com contador, e a frase que
define o papel: "Vai para análise do departamento pessoal. Você não decide sozinho
se a justificativa vale." Botão "Enviar para análise" a 52px, acima do teclado.

### Estados desenhados

| Estado | O que muda |
|---|---|
| **Enviado** | Confirmação em tom `good`, a ocorrência passa a **Em análise** e o texto enviado fica visível. Volta para "as 3 pendentes". |
| **Revogada** | "Este indício não existe mais": a marcação foi corrigida na origem às 09:14 e o motor **revogou** em vez de apagar. Tom neutro/positivo — o dado melhorou, não quebrou. Mostra o antes (riscado) e o depois. |
| **Login com retorno** | Tocou o link deslogado: tela navy com uma confirmação **neutra** — "Você abriu um link de ocorrência. Entre para vê-la." — e a promessa explícita "você volta direto para esta ocorrência, não para a página inicial". **Nada de colaborador antes da sessão**: sem nome, unidade, horário, tipo de ocorrência ou contagem. O banco recusa qualquer leitura de ocorrência para sessão não autenticada (erro de permissão, não lista vazia), então não existe dado para preencher esse espaço — e desenhá-lo exigiria uma exceção na regra de acesso que não vai existir. Encaminhar a mensagem de WhatsApp não pode levar junto o nome da pessoa e o desvio dela. A nota de rodapé sobre acesso de supervisor permanece: ela fala do papel, não de ninguém. |
| **Sinal ruim** | Faixa "Sem conexão" com a justificativa salva no aparelho, card "Enviando" com `Skeleton`, "Tentar de novo", e a garantia de que a lista mostra a última leitura recebida **com a hora dela** — não um retrato em branco. |
| **Dado atrasado** | O seletor de cenário do cabeçalho vale aqui: a faixa de idade do dado muda em todas as sete molduras. |

### Pontos de quebra

O protótipo apresenta as sete molduras num quadro; os números abaixo são do
desenho, para a implementação:

1. **390px** — largura de referência. Entre 360 e 430 tudo se mantém: os dois
   blocos "registrado × previsto" dividem a linha por igual. Abaixo de **360px** eles
   ficam apertados e devem empilhar.
2. **~700px** — acima disso a lista ganharia largura sem ganhar informação; é onde
   entra o layout de tablet, **não desenhado nesta rodada**.
3. **~1150px** — abaixo desta largura o cabeçalho das telas de desktop passa a
   ocupar duas linhas (já tratado); acima dela o desktop é o ambiente pretendido.
4. Todas as tabelas de desktop rolam horizontalmente dentro do card
   (`overflow-x:auto` no wrapper), então nenhuma vaza a borda em viewport estreito.

## Fora de escopo, por decisão

Portal do colaborador · aplicativo nativo (o alerta abre no navegador do celular) ·
recrutamento · assinatura eletrônica ·
processamento de folha · qualquer tela que registre ou edite ponto.
