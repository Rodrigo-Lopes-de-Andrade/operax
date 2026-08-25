# Componentes novos do design system

Oito componentes que o protótipo introduziu para acabar com markup improvisado.
A implementação de referência está em
`prototipo/_ds/aegis-design-system-.../_ds_extras.js` — React puro, sem build, no
mesmo namespace global do bundle. Recriar com a stack do repositório mantendo a API.

## Table

A espinha dorsal do produto: cinco tabelas do protótipo (ocorrências, monitor diário,
histórico de marcações, erros de importação, custo por unidade, mapeamento, unidades,
usuários, sync, auditoria) são a mesma componente.

```
columns: [{ key, label, align, width, strong, muted, mono, numeric, sortable, noWrap }]
rows:    [{ ...valores, id, onClick, muted }]
density: 'compact' | 'default' | 'relaxed'   // padding vertical 8 / 12 / 16
stickyHeader, maxHeight, zebra, footer
sortKey, sortDir, onSort                     // sem onSort, ordena internamente
onRowClick, empty: { icon, title, description, tone }
```

Cabeçalho: 10px de padding, 11px/700 uppercase tracking 0.06em, fundo
`--surface-muted`, borda inferior `--border-subtle`; coluna ordenável mostra
`chevrons-up-down` e, quando ativa, `arrow-up`/`arrow-down` e texto `--text-strong`.
Linha: borda superior `--border-subtle`; hover em linha clicável recebe
`--surface-muted` com transição `--duration-fast`. Primeira e última célula têm
padding lateral 22px, as demais 16px.

**Célula.** O valor é string/número, ou um descritor — é assim que a tabela cobre os
casos do produto sem virar div:

| kind | Renderiza |
|---|---|
| `badge` | `{tone, label, dot}` no Badge do sistema |
| `stack` | `{title, sub, dot, chip, chipIcon}` — duas linhas, ponto de estado, selo |
| `signed` | `{value, color, sub}` — número tabular 700 com sinal; sem `color`, deduz pelo sinal (− laranja queimado, + teal) |
| `textchip` | `{label, chip, chipIcon}` — texto de corpo + selo tracejado |
| `chip` | `{label, icon}` — selo tracejado isolado |
| `bar` | `{label, pct, color, width}` — valor + barra 6px |
| `time` | `{label, sub}` — hora mono 600 + data |
| `check` | `{checked, disabled, onChange}` — Checkbox, sem propagar o clique da linha |
| `button` | `{label, icon, variant, onClick}` — Button sm, sem propagar o clique |

Vazio, nulo ou string vazia renderiza "—" em `--text-faint`. Coluna `numeric`/`mono`
aplica `aegis-tnum`/`aegis-mono` para os números alinharem na vertical.
Sem linhas e com `empty`, a própria tabela mostra o `EmptyState compact`.

## Chart

Três formas, porque o produto usa três.

```
type: 'diverging' | 'trend' | 'rankbar'
data: diverging [{label, pos, neg}] · trend [{label, value}] · rankbar [{label, value, display, pct, color}]
height, color, posColor, negColor, posLabel, negLabel, empty, onSelect
gridColor, labelColor, labelSize, valueSize, barHeight, valueColor, track, gap
```

- **diverging** — zero no meio, excedente acima (`--accent-violet`, valor teal), faltante abaixo
  (`--accent-orange`), legenda própria, hover realça a coluna e apaga as outras para
  55%, `title` nativo com os minutos. É a tendência diária.
- **trend** — série temporal em SVG `viewBox 0 0 100 100` com
  `preserveAspectRatio="none"`, traço 2px `vectorEffect="non-scaling-stroke"`, área em
  gradiente de 24% a 0, ponto por leitura, três linhas de grade.
- **rankbar** — barra horizontal com rótulo à esquerda e valor tabular à direita;
  `display` permite "4 · 326 min".

Os parâmetros de tamanho e cor de grade existem para o Painel de TV, que usa a mesma
componente com tipografia de 24–30px sobre fundo escuro.

## Drawer

Painel lateral de detalhe. `open, title, eyebrow, subtitle, onClose, width=520, footer,
children`. Scrim `--scrim`, `z-index` 60, sombra `--shadow-lg`; fecha no Esc e no clique
fora; cabeçalho fixo com `IconButton x`, corpo com rolagem, rodapé opcional fixo.

## Tabs

`tabs: [{value, label, icon, count}], value, onChange`. Item 11px de padding vertical,
14 horizontal; selecionado ganha peso 700, `--text-strong` e `inset 0 -2px` em
`--brand`; `count` vira pílula `--brand-soft` quando ativo.

## EmptyState

`icon, title, description, tone, compact, children`. Círculo de 64 (44 no `compact`)
com fundo e cor do tom, título 20px/700, descrição 14px `--text-muted` com
`text-wrap: pretty` e máximo de 520px, ações em linha. Tom `good` para sucesso —
dia sem ocorrência **é** sucesso, não tabela vazia.

## Toast

`tone, title, description, action, actionLabel, onClose, icon`. Máx. 460px, sombra
`--shadow-lg`, tile de 30px com ícone do tom (`check-circle-2`, `octagon-alert`,
`triangle-alert`, `info`), ação de texto em `--brand` (usada como "Desfazer" na ação
em lote do mapeamento).

## Skeleton

`width, height, radius, lines, gap`. Gradiente que varre em 1.4s
(`@keyframes aegis-skeleton`, injetado uma vez). Última linha a 64% quando
`lines > 1`. Respeitar `prefers-reduced-motion` na implementação.

## Pagination

`page, pageCount, total, pageSize, sizes, onPage, onPageSize, label`. Total tabular à
esquerda, seletor de tamanho em pílulas mono, "Página X de Y" e dois botões 30×30 de
navegação com estado desabilitado em `--control-disabled-*`.

## Já existiam e agora estão em uso

`Card`/`CardHeader`, `Tooltip`, `DateField` e `ExposureCard` continuam disponíveis no
bundle. O protótipo usa `Button`, `IconButton`, `Badge`, `Avatar`,
`SegmentedControl`, `Icon`, `Input`, `Select`, `Checkbox`, `Switch` e `KpiCard`.

## Variantes de celular

A superfície do alerta no celular (390 × 844) reaproveita o sistema sem componente
novo, com três ajustes de uso:

- **Table não vai para o celular.** A lista de ocorrências é um empilhamento de
  cartões-botão (mínimo 44px de toque, 14–17px de corpo), não uma tabela reduzida.
  Colunas viram pares rotulados: "Registrado 08:12" ao lado de "Previsto 08:00".
- **Drawer → tela cheia.** O painel de detalhe do desktop é uma rota no celular,
  com voltar de 44px e a ação fixa no rodapé (zona do polegar): primary 52px,
  secondary 48px.
- **EmptyState em `compact`** cobre "indício revogado" e "nada pendente";
  **Skeleton** cobre "enviando justificativa"; **Badge** carrega os estados
  (*Em análise*, *Enviando*) com `dot`.
- **Signed sempre com palavra.** No celular a cor não basta: além de
  `--accent-violet` (teal, excedente) / `--accent-orange` (laranja queimado,
  faltante), o sinal e a palavra da direção são
  obrigatórios. Vale como regra para o `kind: 'signed'` da Table no desktop também.

A moldura de aparelho usada na apresentação (`ios-frame.jsx`, `IOSDevice`) é
andaime de protótipo: reserva 58px para a status bar e 34px para o home indicator.
Na implementação isso é `env(safe-area-inset-*)`.
