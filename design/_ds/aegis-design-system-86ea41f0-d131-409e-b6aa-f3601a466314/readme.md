# Aegis Design System

Design system for **OperaX** — a B2B, multi-tenant **workforce-time, people and
payroll-cost management SaaS** (Supabase-backed) built on top of a third-party
time-clock system. It reads clock data, detects deviations from the expected
workday, alerts the manager the same day, and consolidates payroll cost.
Anchor client: Kastro Park. Vendor: EURECA.

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
  but organised. Deep-navy structural chrome (`#111D2D`) against light-grey app
  canvas; cool, blue-led data palette.
- **Colour.** A blue-forward 8-step categorical ramp (`categorical1…8`,
  `#9FBFFE → #013DF2`, plus violet/amber/orange accents) for data viz; semantic
  pairs for bad/good/alert; a 3-stop heatmap (`#DCFFDC → #FFF6E6 → #FFCCCC`,
  Baixa → Média → Alta). Full light **and** dark palettes — see `tokens/colors.css`.
  Brand action = `categorical-4` (`#015DFC` light / `#407FFC` dark);
  active/pressed = `categorical-5`. **Stay inside the palette** — no off-token
  colours. Direction pair for signed minutes: `accent-violet` = excedente,
  `accent-orange` = faltante.
- **Type.** *Manrope* for UI/display (weights 400–800), *JetBrains Mono* for
  codes, timestamps and tabular figures. Tight tracking on headings; uppercase
  `0.08em` eyebrows. (Fonts are a substitution — see Caveats.)
- **Spacing.** 4px base grid; generous gutters (24px page padding, 16px card
  gaps). Layout: fixed sidebar (264px / 76px collapsed), 84px header, fluid
  content.
- **Corners.** High radii: cards `18px`, containers `24px`, fields `10px`,
  buttons & filter chips are full **pills** (`999px`), avatars/icon-buttons round.
- **Elevation.** Soft, low-opacity navy shadows (`shadow-sm` resting on cards,
  `shadow-md` on hover, `shadow-lg` for popovers/menus). No harsh borders — lines
  are low-opacity (`border-subtle` ≈ 8% navy).
- **Backgrounds.** Flat surfaces, no textures/patterns. The only gradients are
  the subtle trend-area fill and the heatmap scale — never decorative bg
  gradients. No bluish-purple hero gradients.
- **Motion.** Calm and quick — `120–280ms`, standard/`ease-out` curves, no
  bounce. Bars/lines grow on load; menus fade. Honors `prefers-reduced-motion`.
- **Interaction states.** Hover = subtle surface tint (`surface-muted`) or a
  lighter fill on dark chrome; cards lift `-1px` + `shadow-md`. Active = brand
  fill (`brand-strong`) + a `0.5px` nudge. Focus = brand ring
  (`shadow-focus`). Disabled = `background-muted` + `foreground-quaternary`.
- **Transparency/blur.** Used sparingly — translucent white fills on the navy
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
- **Logo.** The Aegis monogram — a thin-line apex ("A") inside an open ring.
  Stored as `assets/aegis-symbol-white.png` (white, for navy chrome),
  `assets/aegis-symbol-navy.png` (`#111D2D`) and `assets/aegis-symbol-blue.png`
  (`#015DFC`). OperaX chrome pairs the `timer` glyph tile with the "OperaX"
  wordmark (Manrope 800) until a product logo is supplied.

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

- **Fonts are substitutes.** No brand fonts were provided — Manrope + JetBrains
  Mono were chosen. Provide official font files to swap them in `tokens/fonts.css`.
- **Logo.** The Aegis monogram files ship here; a dedicated OperaX mark does not
  exist yet.
- **Icons via CDN.** Lucide is loaded from unpkg; vendor it locally for offline
  use if needed.
- **Validate against the schema.** Component names, copy and state vocabulary
  follow the OperaX PRD, `DICIONARIO-DE-DADOS.md` and the migrations in
  `supabase/migrations/`. Check field labels against the generated data
  dictionary rather than inventing them.
