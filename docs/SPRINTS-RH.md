# OperaX — sprints da etapa RH

Quatro sprints (R1–R4), numerados à parte da linha do tempo principal de
`SPRINTS.md` para não colidir. Cada sprint termina com um gate verificável —
sem gate verde, o seguinte não começa. O projeto já está em andamento no Claude
Code: estes sprints entram na fila, não a substituem.

---

## R1 — Fundação: banco, matriz e validadores

**Entrega:** migration 16 aplicada; matriz dono-do-campo em código; validadores
de domínio prontos e testados **antes de existir tela ou endpoint**.

- Migration 16: `hr_code` em `app.employee` (unicidade parcial por tenant) +
  tipos novos de `app.file_import` + bloco de prova.
- `operax/rh/ownership.py`: a matriz dono-do-campo como constante, com os três
  campos pendentes de confirmação **fora** (tratados como sync até decisão).
- `operax/rh/validators.py`: um validador por domínio, função pura, usada
  depois por import e formulário. Casos: chave divergente, campo do sync
  alterado, vigência retroativa, parcela inconsistente, sobreposição de
  afastamento, enum inválido.
- Fixture sintética de planilha (nunca dado real) para os testes.

**Gate:** `make db-test` verde com a migration 16 · pytest dos validadores
cobrindo os seis casos de erro por linha · asserção de que o painel não tem
grant de escrita em tabela de RH.

## R2 — Template e pipeline de importação

**Entrega:** baixar template pré-preenchido, subir, ver preview por linha,
confirmar parcial — de ponta a ponta por API.

- Gerador de template (`GET /rh/template/{type}`): pré-preenchimento, colunas
  bloqueadas por dono, dropdowns de enum, aba `_meta` com `layout_version` e
  hash de cabeçalho. Download de template sensível auditado.
- `POST /rh/imports` (preview sem gravação) e `POST /rh/imports/{id}/confirm`
  (grava só linhas válidas; import `partial` até completar).
- Template de **vínculo** (`hr_link`): matrícula + nome impressos, ID RH a
  preencher.
- Recusa de arquivo sem `_meta`/hash divergente com mensagem "baixe o modelo
  atual".

**Gate:** E2E de API: template → edição → upload → preview com erro simulado em
3 linhas → confirmação parcial → reimport das corrigidas fecha o import ·
`audit_log` registra origem de cada linha gravada.

## R3 — Telas: aba Colaboradores

**Pré-requisito:** handoff da rodada 7 do Claude Design. Se atrasar, a versão
funcional nasce com os componentes existentes (Table, Tabs, Drawer, EmptyState)
seguindo `COMPONENTES.md`, e o refinamento visual entra quando o handoff chegar
— o sprint não bloqueia.

- Lista com filtros, busca e coluna de próximos vencimentos (ASO, CNH,
  experiência 30/60d).
- Detalhe em abas por domínio; aba aparece só com o domínio; edição só com
  escrita. Proveniência por campo ("Secullum · leitura de HH:MM").
- Remuneração e posição como linha do tempo + "nova vigência"; correção =
  revogar + criar.
- Importação de RH plugada na tela de Importação existente (seletor de tipo).
- Visibilidade da aba Colaboradores por papel, sem expor Integrações/Usuários.

**Gate:** Playwright: DP edita cadastro e cria vigência · supervisor não vê a
aba de remuneração (**ausente do DOM**, não desabilitada) · quem tem leitura
sem escrita não vê botão de editar · fluxo de import completo pela tela.

## R4 — Carga inicial e homologação

**Entrega:** conversor de implantação + ensaio geral da carga com fixture; a
carga real acontece na implantação, fora do repositório.

- `scripts/rh_carga_inicial.py`: lê a planilha do cliente, emite os templates
  de domínio na ordem (vínculo → cadastro/posição → documentos/ASO →
  afastamentos/movimentações → remuneração/acordos) e o **relatório de
  descarte** (CID, dados bancários, abas de dashboard — com motivo).
- Conversões específicas: FÉRIAS matriz→formato longo; DESLIGADOS→status
  desligado; VENCIMENTO ASO→`app.occupational_exam` (aptidão+validade).
- Ensaio com a fixture sintética: 100% das linhas com destino ou descarte
  justificado — o critério de sucesso do PRD vira teste.
- Roteiro de implantação de 1 página para a EURECA executar no cliente.

**Gate:** ensaio da carga fecha em 100% (destino ou descarte) · relatório de
descarte gerado e legível · suíte completa verde (`make db-test`, pytest,
Playwright) · demonstração: planilha de fixture → sistema → aba Colaboradores
respondendo "o que vence em 30 dias?".

---

## Fora destes sprints, registrado

- Confirmação dos três campos pendentes da matriz (supervisor, unidade de
  atuação, data de demissão antecipada) — decisão com o cliente; até lá são
  sync.
- CÓD POSTOS como fonte de escala esperada — avaliação própria depois de R4.
- Rodada 7 do Claude Design — dispara em paralelo a R1/R2 para chegar antes
  de R3.
