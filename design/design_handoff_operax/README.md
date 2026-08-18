# Handoff — OperaX (protótipo de interface)

## Visão geral

Nove telas do OperaX desenhadas em HTML, com dado de exemplo, estados e navegação
funcionando. O destino é **este repositório** — Next.js 16 / React 19, Supabase com
as views e RPCs de `supabase/migrations/`, regras de arquitetura em `CLAUDE.md`.
Não é um projeto novo: cada tela abaixo aponta a view ou a função que a alimenta.

Telas: Gestão de ponto · Monitor diário · Consulta individual (duas variantes de
papel) · Assistente · Folha e custo · Importação de folha · Regras de alerta ·
Administração · Painel de TV.

## Sobre os arquivos deste pacote

`prototipo/OperaX.dc.html` é **referência de design**, não código de produção. É um
único arquivo HTML que renderiza React em runtime, com todo o estilo inline. A tarefa
é **recriar essas telas no ambiente que já existe** (Next.js + React, Tailwind ou o que
o repositório adotar), não portar este arquivo.

O que **deve** ser aproveitado tal como está:

- `prototipo/_ds/.../tokens/*.css` — os tokens de cor, tipografia, espaço, raio,
  sombra e motion. São CSS custom properties; entram no projeto como estão.
- `prototipo/_ds/.../_ds_extras.js` — implementação de referência de `Table`, `Chart`,
  `Drawer`, `Tabs`, `EmptyState`, `Toast`, `Skeleton` e `Pagination`. Escrito em
  `React.createElement` puro, sem build. Serve como especificação executável da API
  de cada componente (props, estados, medidas) — ver `COMPONENTES.md`.
- `prototipo/_ds/.../readme.md` — o guia do design system, já reescrito para o
  contexto OperaX (entidades, papéis, vocabulário, domínios sensíveis).

## Fidelidade

**Alta fidelidade.** Cores, tipografia, espaçamento, densidade, estados e cópia são
finais. A recriação deve ser fiel ao pixel usando os componentes do repositório.
As exceções conhecidas estão em "Pendências" no fim deste documento.

## Regras de produto que o desenho carrega

Não são preferências visuais. Cada uma resolve um risco e precisa sobreviver à
implementação:

1. **Idade do dado é permanente.** O indicador no cabeçalho ("Dados de 08:40 · há
   25 min") aparece em toda tela que mostra o dia corrente, sempre visível, nunca
   em tooltip. Fonte: `app.sync_run` / métrica `data_freshness`.
2. **Nunca "hora extra".** O vocabulário é *desvio* e *indício*. Todo detalhamento
   termina em "Conferir no Secullum". O OperaX não escreve na origem.
3. **Alerta cita horário observado.** "Entrada registrada às 08:12, prevista 08:00" —
   nunca "está atrasado".
4. **Minutos têm sinal e a cor codifica direção.** Excedente = `--accent-violet`,
   faltante = `--accent-orange`. Vermelho fica para falha, não para desvio.
5. **Papel muda o que existe na tela.** Supervisor de unidade não vê remuneração,
   documento nem exame: os blocos **não são renderizados**. Sem cadeado, sem cinza.
   No protótipo isso é o seletor de papel no cabeçalho.
6. **Escala não confirmada é estado de primeira classe.** Selo tracejado com ícone
   `calendar-off`, repetível em tabela e em card; a linha não gera alerta.
7. **Um provedor de WhatsApp por tenant, e template não é texto.** Com o provedor
   oficial (`meta_cloud`), mensagem sem template aprovado é descartada pela Meta sem
   erro: regra ligada nessa condição é falha silenciosa e a tela precisa denunciá-la
   em três lugares (faixa da lista, linha da regra, editor). Provedores não oficiais
   (`z_api`, `uazapi`) conectam por QR Code e aceitam texto livre, ao custo do risco
   de banimento do número — informado no momento da escolha.
8. **Vazio, erro e dado velho são caminho principal.** O seletor de cenário no
   cabeçalho alterna entre *dia com ocorrências · dia sem ocorrência · dado
   atrasado* e afeta todas as telas.

## Mapa tela → dado

| Tela | Views / RPCs |
|---|---|
| Gestão de ponto | `fn_kpi_period`, `vw_deviation_daily_trend`, `fn_ranking_by_unit`, `fn_ranking_by_employee`, `fn_recurrence`, `vw_deviation_event` |
| Monitor diário | `vw_deviation_event`, `vw_deviation_summary_by_unit`, `app.expected_workday`, `app.sync_run` |
| Consulta individual | `vw_employee`, `vw_deviation_by_employee_day`, `app.justification`, `app.leave_period`; sensível: `app.employee_compensation`, `app.employee_pii`, `vw_document_expiry`, `app.occupational_exam` |
| Assistente | catálogo `app.metric` (9 ativas, 4 previstas), registro em `app.ai_query` |
| Folha e custo | `vw_payroll_summary`, `app.payroll_period`, `app.payroll_entry`, `app.payroll_charge`, `app.workforce_movement` |
| Importação de folha | `app.file_import` (o erro por linha fica em `file_import.report`, jsonb), `app.payroll_entry`, `app.payroll_charge` |
| Regras de alerta | `app.alert_rule`, `app.alert_rule_target`, `app.alert_queue`, `app.message_template`, `public.fn_whatsapp_readiness()` |
| Administração | `app.unit`, `app.unit_secullum_map`, `app.tenant_member` + `app.user_scope` + `app.domain_permission`, `app.integration`, `app.sync_run`, `app.audit_log` |
| Painel de TV | somente agregados: `vw_deviation_summary_by_unit`, `vw_deviation_daily_trend` |

O detalhe de cada tela — layout, colunas, estados, cópia — está em `TELAS.md`.

## Estado da interface

Estado local do protótipo, que na implementação vira URL + query cache:

- `papel` — 'DP / Financeiro' | 'Supervisor de unidade'. Define nav e blocos sensíveis.
- `cenario` — 'Dia com ocorrências' | 'Dia sem ocorrência' | 'Dado atrasado'. No
  produto real isso não é estado: vem do dado. **Nenhum horário de leitura é fixo na
  interface** — todos derivam de uma única fonte (`leitura()` no protótipo,
  `app.sync_run` no produto).
- `provedor` — 'meta_cloud' | 'z_api' | 'uazapi', um por tenant; e o estado de
  aprovação por template, que decide se a regra pode ser ligada.
- Filtros do dashboard: `empresa`, `unidade`, `departamento`, `gestor`, `periodo`,
  `direcao`. **Vivem na URL** — o link chega por WhatsApp já filtrado, e a barra
  precisa comunicar "você está vendo um recorte" com os chips removíveis.
- `drawer` — ocorrência aberta no painel lateral (fecha com Esc e no scrim).
- Administração: `aba`, `filtro` (não validados / validados / todos), `selecao`,
  `validados`, `pagina`, `porPagina`, `toast`.
- Painel de TV: `bloco` — rotação automática a cada 12 s entre dois blocos.

## Tokens

Use `prototipo/_ds/.../tokens/`. Os valores que mais aparecem:

**Cor (tema claro, que é o padrão)**
- Chrome navy `#111D2D` (sidebar) · canvas `--surface-app` · card `--surface-card`
- Ação `--brand` `#015DFC`; pressionado `--brand-strong`; fundo suave `--brand-soft`
- Direção do desvio: `--accent-violet` (excedente) · `--accent-orange` `#CE4B02` (faltante)
- Semânticos: `--good-foreground` `#028402` · `--alert-foreground` `#996601` ·
  `--bad-foreground` `#C10202`, cada um com seu `*-background`
- Texto: `--text-strong` · `--text-body` · `--text-muted` · `--text-faint` `#767676`

Os cinco últimos foram escurecidos em relação à primeira versão do design system
para passar em WCAG AA (4,5:1) sobre o próprio fundo. O matiz não mudou. **O tema
escuro não foi alterado** — já estava conforme.

**Tipografia** — Manrope 400/500/600/700/800 na interface; JetBrains Mono em código,
horário e número tabular (classes `aegis-mono` e `aegis-tnum`). Escala em
`tokens/typography.css`: `--text-2xs` 11px → `--text-4xl` 40px. Eyebrow = 11px, 700,
uppercase, tracking 0.08em.

**Espaço** — grade de 4px; página 24/28px; gap entre cards 16px; padding de card 20/24px.

**Raio** — card `--radius-xl` 18px; container `--radius-2xl` 24px; campo 10px; botão e
chip são pílula; avatar e icon-button redondos.

**Sombra** — `--shadow-sm` em repouso, `--shadow-md` no hover, `--shadow-lg` em
drawer, popover e toast.

**Motion** — 120–280ms, `ease-out`/standard, sem bounce. Barra e linha crescem na
entrada; menu faz fade. Respeitar `prefers-reduced-motion`.

## Assets

- Ícones: **Lucide** (`https://unpkg.com/lucide@latest`), traço 2px, `currentColor`.
  Vendorizar no repositório em vez de CDN.
- Logo: o pacote traz o monograma Aegis em `_ds/.../assets/` (não referenciado pelas
  telas). O chrome do OperaX usa o glifo `timer` sobre `--brand` mais o wordmark
  "OperaX" em Manrope 800, até existir marca própria.
- **Nenhuma imagem de pessoa, nenhum documento.** Avatares são iniciais.
- Nomes de pessoa no protótipo são fictícios; **não há CPF, RG ou PIS em nenhum mock**,
  e não deve haver — nem em fixture de teste.

## Arquivos

- `prototipo/OperaX.dc.html` — as nove telas. Abre direto no navegador.
- `prototipo/support.js` — runtime do protótipo. Não vai para o produto.
- `prototipo/_ds/aegis-design-system-.../` — tokens, `styles.css`, `_ds_bundle.js`
  (primitivas: Button, IconButton, Card, Badge, Avatar, SegmentedControl, Icon,
  Input, Select, DateField, Checkbox, Switch, Tooltip, KpiCard, ExposureCard),
  `_ds_extras.js` (os oito componentes novos) e `readme.md` (guia do sistema).
- `TELAS.md` — especificação tela por tela.
- `COMPONENTES.md` — API dos oito componentes novos.

## Superfície pré-sessão

A tela de login do celular é a única superfície anterior à autenticação e **não
mostra dado de colaborador** — sem nome, unidade, horário, tipo de ocorrência ou
contagem. Apenas a confirmação neutra de que há um link pendente. Vale como regra
para qualquer tela pré-sessão que venha a existir. Os códigos de template seguem
a convenção em inglês de `app.deviation_type` (`late_entry`, `break_exceeded`,
`no_punches`), porque vão para `app.message_template.code`; o que o usuário lê —
corpo da mensagem, rótulos de estado, legenda das variáveis — continua em português.

## Conferência de nomes

Todos os identificadores de banco citados neste pacote foram conferidos contra
`docs/DICIONARIO-DE-DADOS.md` (gerado por introspecção). Cuidado com quatro nomes
cuja forma "plausível" não existe:

- marcação de ponto é **`app.batida_marcacao`** (não `time_punch`);
- papel e escopo de usuário são três tabelas — **`app.tenant_member`**,
  **`app.user_scope`** e **`app.domain_permission`** (não existe `user_role`);
- importação de arquivo é **`app.file_import`**, e o erro por linha não tem tabela
  própria: fica em **`file_import.report`** (jsonb);
- destinatário de alerta é **`app.alert_rule_target`**; remuneração é
  **`app.employee_compensation`**; mapeamento de origem é
  **`app.unit_secullum_map`** (linha sem `validated_at` = não validado, que é
  exatamente o estado desenhado na tela de mapeamento).

## Pendências conhecidas

1. **Consulta individual** foi desenhada para um colaborador (Ubirajara Lins); falta o
   estado de busca/seleção de colaborador.
2. **Regras de alerta** tem o editor de uma regra; criar regra nova abre o mesmo editor
   vazio, não desenhado.
3. **Assistente** mostra uma conversa gravada. O streaming real é SSE, conforme
   `CLAUDE.md`; o cursor piscante do protótipo é a única parte animada.
4. **Painel de TV** é pré-visualização em escala dentro do app. Na parede é rota
   própria em tela cheia, sem sidebar nem cabeçalho, com a rotação de blocos.
5. **Paginação** do dashboard e do mapeamento é visual: a troca de página não refaz a
   consulta no protótipo.
6. **Tema escuro** existe nos tokens e não foi desenhado tela por tela.
