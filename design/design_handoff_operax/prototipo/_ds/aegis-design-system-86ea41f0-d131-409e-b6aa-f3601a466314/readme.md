# Aegis Design System

Design system for **OperaX** — a B2B, multi-tenant **workforce-time, people and
payroll-cost management SaaS** (Supabase-backed) built on top of a third-party
time-clock system. It reads clock data, detects deviations from the expected
workday, alerts the manager the same day, and consolidates payroll cost.
Anchor client: FastPark. Vendor: EURECA. The interface is white-label:
the FastPark brand is the first tenant theme, carried entirely by the colour
tokens, the type tokens and the logo — brand is tenant configuration, not a
product constant.

The flagship surface is **Gestão de ponto**, a management dashboard with
persistent filters, hierarchised KPIs, a diverging deviation trend, three
rankings and a drill-down occurrences table.

> **Heads-up on sources.** The attached resources were effectively empty — the
> mounted `aegis/` folder had no files and the linked GitHub repos contained no
> importable assets. **The visual system was therefore built from the written
> spec** (page structure, component list, official light + dark palette). The
> product context below was later rewritten against the real OperaX PRD, data
> dictionary and Supabase schema. If/when brand fonts or logo files exist, point
> this system at them to raise fidelity.

---

## Product context

- **What it is.** A management, automation and intelligence layer over a
  third-party time-clock system. OperaX **reads** the clock; it never records or
  edits a punch. Multi-tenant: every row is isolated by `tenant_id` under
  Supabase Row Level Security, and role scope narrows it further.
- **Who uses it.** People who spend the whole day inside it — departamento
  pessoal closing the month, unit supervisor acting on an occurrence, direction
  looking at cost. Information density is a feature. **Nine roles**, each with a
  different surface, not a different set of disabled controls.
- **Four sensitive domains** gate what exists on screen: PII, remuneração,
  saúde, disciplinar. A restricted view is a complete screen with fewer
  sections — never a padlock, never a greyed block.
- **Core entities** (Supabase): `employee`, `expected_workday`,
  `deviation_event` (the primary fact table), `alert_rule`, `payroll_period`,
  plus `company`, `unit`, `department`, `time_punch`, `justification`,
  `document`, `sync_run`, `audit_log`.
- **Vocabulary that is binding.** *Desvio* and *indício* — **never "hora
  extra"**; the official record lives in the source system and every detail path
  ends in a "conferir no Secullum" step. Deviation minutes are **signed**:
  positive = excedente, negative = faltante; colour encodes **direction**, not
  magnitude. **Escala não confirmada** is a first-class state — an inferred
  workday marked with a discreet, repeatable seal that never fires an alert.
- **Data is up to 30 minutes old.** Sync runs every half hour. Every screen
  showing the current day states the age of the data permanently and legibly,
  and alerts quote the **observed time** ("entrada registrada às 08:12, prevista
  08:00"), never "agora".
- **Empty, stale and error states are the main path.** The product exists to
  answer "did something go wrong today?" — a day with no occurrence is success
  and gets a designed state.
- **The surfaces.** Gestão de ponto · Monitor diário · Consulta individual ·
  Assistente · Folha e custo · Importação de folha · Regras de alerta ·
  Administração · Painel de TV.
- **Out of scope, by decision.** Employee self-service portal, mobile app,
  recruiting, e-signature, payroll processing, and any screen that records or
  edits a punch.

---

## Content fundamentals

- **Language: Brazilian Portuguese.** All product copy is pt-BR
  ("Gestão de ponto", "Monitor diário", "Minutos de desvio acumulados",
  "Baixar XLS", "Conferir no Secullum", "Limpar", "Aplicar").
- **Voice.** Neutral, corporate, operational. Third-person / impersonal —
  describes the system and the data, not "you". No marketing fluff.
- **Casing.** Sentence case for titles and labels ("Total de desvios",
  "Custo médio por colaborador"). UPPERCASE only for tiny eyebrow labels and
  status emphasis in captions ("PENDENTE de justificativa").
- **Numbers & units.** Figures are terse and tabular: `43`, `+52`, `−17`,
  `412 min`, `R$ 496.420`, `182 colaboradores`. Times as `HH:MM`, dates as
  `DD/MM/AAAA HH:MM`, competência as `MM/AAAA`. Signed minutes always carry the
  sign. Codes, times and figures are monospace: `MT-0481`, `08:12`,
  `deviations_minutes`.
- **State vocabulary.** Row states: *dentro do previsto · atrasado · em
  intervalo · intervalo estourado · não retornou · sem marcação · escala não
  confirmada*. Occurrence status: *pendente · justificado · não contabilizado*.
  Direction: *faltante · excedente*. Import: *completa · parcial · recusada*.
  Mapping: *validado · não validado*.
- **No emoji.** Iconography carries meaning, not emoji. Tone is confident and
  understated — "premium corporate", not playful.

---

## Visual foundations

- **Mood.** Premium, sophisticated, corporate. Clean, high breathing room, dense
  but organised. Warm-grey structural chrome (`#5A5A5A`, Pantone 425 C) against a
  light-grey app canvas (`#F1F1F1`, 427 C at 50%); orange-led data palette with a
  teal counterpart.
- **Colour.** The FastPark brand palette: orange `#FF8C00` (Pantone 151 C),
  grey `#5A5A5A` (425 C), light grey `#DCDCDC` (427 C), light blue `#98D2DB`
  (2975 C). The 8-step categorical ramp is derived from those four. Semantic
  pairs for bad/good/alert and the 3-stop heatmap (`#DCFFDC → #FFF6E6 → #FFCCCC`)
  are unchanged. Full light **and** dark palettes — see `tokens/colors.css`.
  **Stay inside the palette** — no off-token colours.

  **The rule that governs the orange.** `#FF8C00` is 2.33:1 on white and never
  works as text. It appears as a **fill with dark text on top**
  (`--text-on-accent #262626`, 5.42:1). Where the interface needs orange in text
  or a link, it uses `--brand-strong #A85F00` — the same hue darkened to 4.88:1.
  On the dark TV surface (`#2E2E2E`) the pure orange reaches 5.82:1 and is used
  directly for large figures.

  **Direction pair for signed minutes:** `accent-violet` = excedente (the token
  name is kept; the value is teal `#1F7A8A`), `accent-orange` = faltante (burnt
  `#C2410C`). Both differ from the brand orange, so a deviation bar never reads
  as a button, and teal × orange stays legible under the common colour
  deficiencies. Colour codes **direction**, and the sign and the word are always
  present alongside it.
- **Type.** *Hanken Grotesk* for UI/display (weights 300–800) — the brand family
  from the manual, with **Verdana** as the institutional fallback. Tabular
  figures come from the family's own `"tnum"` feature. *JetBrains Mono* for codes
  and URLs is a declared substitution: the manual defines no mono face. Tight
  tracking on headings; uppercase `0.08em` eyebrows.
- **Spacing.** 4px base grid; generous gutters (24px page padding, 16px card
  gaps). Layout: fixed sidebar (264px / 76px collapsed), 84px header, fluid
  content.
- **Corners.** High radii: cards `18px`, containers `24px`, fields `10px`,
  buttons & filter chips are full **pills** (`999px`), avatars/icon-buttons round.
- **Elevation.** Soft, low-opacity neutral-grey shadows (`shadow-sm` resting on cards,
  `shadow-md` on hover, `shadow-lg` for popovers/menus). No harsh borders — lines
  are low-opacity (`border-subtle` ≈ 8% neutral grey).
- **Backgrounds.** Flat surfaces, no textures/patterns. The only gradients are
  the subtle trend-area fill and the heatmap scale — never decorative bg
  gradients. No bluish-purple hero gradients.
- **Motion.** Calm and quick — `120–280ms`, standard/`ease-out` curves, no
  bounce. Bars/lines grow on load; menus fade. Honors `prefers-reduced-motion`.
- **Interaction states.** Hover = subtle surface tint (`surface-muted`) or a
  lighter fill on dark chrome; cards lift `-1px` + `shadow-md`. Active = brand
  fill (`brand-strong`) + a `0.5px` nudge. Focus = brand ring
  (`shadow-focus`). Disabled = `background-muted` + `foreground-quaternary`.
- **Transparency/blur.** Used sparingly — translucent white fills on the grey
  sidebar; scrim token for overlays. No glassmorphism elsewhere.
- **Contrast.** Light-theme semantic foregrounds were darkened to clear WCAG AA
  4.5:1 on their own backgrounds (`alert-foreground #996601`,
  `foreground-quaternary #767676`, `accent-orange #CE4B02`,
  `bad-foreground #C10202`, `good-foreground #028402`). Hues unchanged. The dark
  theme was already compliant and was left alone.

---

## Iconography

- **System: [Lucide](https://lucide.dev)** — linear, 2px stroke, `currentColor`.
  Loaded from CDN (`https://unpkg.com/lucide@latest`). The `Icon` component
  wraps it.
- **No brand icon set existed** in the sources, so Lucide is a deliberate
  substitution chosen for its clean linear style. Swap names per surface; keep
  stroke weight 2 for UI chrome.
- **Common glyphs.** `layout-dashboard`, `activity`, `user-round`, `sparkles`,
  `wallet`, `file-up`, `bell-ring`, `shield`, `monitor` (nav); `bell`, `search`
  (header); `sliders-horizontal`, `building-2`, `calendar`, `eraser` (filters);
  `timer`, `clock`, `triangle-alert`, `calendar-off` (states); `external-link`,
  `message-square-plus`, `download`, `chevron-right` (actions).
- **Logo.** The FastPark mark: a rounded frame open at the base, in orange
  `#FF8C00`, with the **smile** — the arc — below it. Drawn as inline SVG,
  `viewBox="0 0 269.8 257.1"`, geometry traced from the brand manual. Symbol sits
  to the **left** of the wordmark; wordmark is "Fast" + "Park" in Hanken Grotesk
  700, where "Park" is always orange and "Fast" takes white on dark chrome or
  `#5A5A5A` on light. Clear space ½X; minimum digital size 35px wide for symbol +
  wordmark together — below that, use the symbol alone. Never rotate, shadow,
  recolour or mirror it. The smile arc doubles as a base element on the TV panel
  cards, following the physical signage in the manual.

---

## Index / manifest

**Root**
- `styles.css` — global entry (import this). `@import`s only.
- `tokens/` — `colors.css` (light+dark), `typography.css`, `spacing.css`,
  `radius.css`, `shadows.css`, `motion.css`, `fonts.css`, `base.css`.
- `assets/` — `aegis-symbol-white.png`, `aegis-symbol-navy.png`, `aegis-symbol-blue.png`.
- `guidelines/` — foundation specimen cards (Colors, Type, Foundations, Brand).
- `components/` — reusable primitives (see below).
- `_ds_bundle.js` — built runtime for the primitives below.
- `_ds_extras.js` — built runtime for the OperaX additions below. Load **after**
  `_ds_bundle.js`; registers into the same global namespace.

**Components** (`window.AegisDesignSystem_*` namespace)
- `core/` — `Button`, `IconButton`, `Card` + `CardHeader`, `Badge`, `Avatar`,
  `SegmentedControl`, `Icon`.
- `forms/` — `Input`, `Select`, `DateField`, `Checkbox`, `Switch`.
- `feedback/` — `Tooltip`.
- `data/` — `KpiCard`, `ExposureCard`.

**OperaX additions** (`_ds_extras.js`, same namespace)
- `Table` — the backbone surface. Sticky header, density (`compact` ·
  `default` · `relaxed`), sortable columns, clickable rows, tabular numeric
  cells, embedded empty state, optional footer slot. Cell values are either
  plain strings or descriptors: `{kind:'badge'|'stack'|'signed'|'chip'|'bar'|'time'}`.
- `Chart` — three forms only: `diverging` (zero in the middle, excedente above /
  faltante below), `trend` (time series with optional area fill), `rankbar`
  (horizontal ranking).
- `Drawer` — right-side detail panel (occurrence detail, mapping item). Escape
  closes; header/body/footer slots.
- `Tabs` — section switch with optional counts.
- `EmptyState` — designed empty / success / stale state, `compact` variant for
  in-table use.
- `Toast` — result of a bulk action, with optional undo.
- `Skeleton` — loading placeholder (lines, blocks).
- `Pagination` — page controls plus page-size and total-record readout.

---

## Caveats

- **Fonts.** Hanken Grotesk is the brand family and loads from Google Fonts;
  Verdana is the manual's fallback. JetBrains Mono for code and URLs is a
  declared substitution — the manual defines no mono face.
- **Logo.** The FastPark symbol is drawn as inline SVG from geometry traced out
  of the brand manual PDF; no vector asset was supplied. Replace it with the
  official file when one exists — the paths live in the prototype chrome
  (sidebar, mobile login, TV panel header).
- **Icons via CDN.** Lucide is loaded from unpkg; vendor it locally for offline
  use if needed.
- **Validate against the schema.** Component names, copy and state vocabulary
  follow the OperaX PRD, `DICIONARIO-DE-DADOS.md` and the migrations in
  `supabase/migrations/`. Check field labels against the generated data
  dictionary rather than inventing them.
