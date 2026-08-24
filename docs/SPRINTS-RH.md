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

### Andamento em 24/08/2026 — em curso

**Feito.** `supabase/migrations/20260824140000_16_hr_management.sql` aplica limpa
e é idempotente (provado rodando duas vezes seguidas). Ela traz `hr_code` com
índice único **parcial** por tenant — parcial de propósito: um índice único comum
deixaria exatamente um colaborador sem ID RH e recusaria o segundo, que é o
oposto do que "vazio até vincular" precisa. Traz também os sete tipos de
`app.file_import`, somados aos existentes **lidos do catálogo** em vez de
reescritos de memória, que é como se apaga em silêncio um valor já gravado. O
bloco de prova já carrega a asserção do gate: `anon` não escreve em nenhuma das
nove tabelas de RH.

**Falta.** `operax/rh/ownership.py`, `operax/rh/validators.py` e a fixture
sintética.

### Duas coisas que a execução expôs, e que decidem antes do R2

**1. Sete campos da matriz não têm coluna.** A SPEC §4 é explícita em ser
"proposta — confirmar antes do template congelar", e a conferência contra o
schema real mostra que estes não existem em lugar nenhum:

| Campo da matriz | Situação |
|---|---|
| CBO | sem coluna |
| uniforme | sem coluna |
| nível (posição) | sem coluna — `app.employee_position` tem só `cargo` |
| benefícios: VR, planos, cesta, VT | sem coluna — `app.employee_compensation` tem só `salary` |
| periculosidade | sem coluna |
| cargo de confiança | sem coluna |
| unidade de atuação ("atuando") | sem coluna — e é um dos três pendentes |

Os demais existem: matrícula, nome, admissão, demissão, unidade, status,
supervisor (`manager_employee_id`), cargo, salário, documentos, ASO,
afastamentos, movimentações, acordos e parcelas.

A SPEC §1c diz "sem tabela nova" e a migration 16 não cria coluna alguma além de
`hr_code` — corretamente, porque é o que ela especifica. Mas **o template de
remuneração do R2 não tem como carregar benefício que não tem coluna**. Então a
matriz nasce cobrindo só o que existe, o resto fica nomeado como lacuna em
`ownership.py`, e a decisão — criar as colunas numa migration 17 ou tirar os
campos do escopo v1 — precisa sair **antes do R2**, não durante.

**2. `app.file_import.status` não aceita `partial`.** A SPEC §3 diz que o import
"fica `partial` até as demais entrarem (mesma semântica da folha)", e o check
atual aceita `received`, `validating`, `validation_error`, `processed` e
`discarded`. Ou a semântica da folha é `processed` com `rows_error > 0` e o texto
usa "partial" como descrição, ou falta um valor. É pergunta do R2, registrada
aqui para não virar descoberta no meio dele.

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
