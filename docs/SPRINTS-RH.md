# OperaX — sprints da etapa RH

Quatro sprints (R1–R4), numerados à parte da linha do tempo principal de
`SPRINTS.md` para não colidir. Cada sprint termina com um gate verificável —
sem gate verde, o seguinte não começa. O projeto já está em andamento no Claude
Code: estes sprints entram na fila, não a substituem.

---

## R1 — Fundação: banco, matriz e validadores ✅

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

### Andamento em 24/08/2026 — fechado

**Feito.** `supabase/migrations/20260824140000_16_hr_management.sql` aplica limpa
e é idempotente (provado rodando duas vezes seguidas). Ela traz `hr_code` com
índice único **parcial** por tenant — parcial de propósito: um índice único comum
deixaria exatamente um colaborador sem ID RH e recusaria o segundo, que é o
oposto do que "vazio até vincular" precisa. Traz também os sete tipos de
`app.file_import`, somados aos existentes **lidos do catálogo** em vez de
reescritos de memória, que é como se apaga em silêncio um valor já gravado. O
bloco de prova já carrega a asserção do gate: `anon` não escreve em nenhuma das
nove tabelas de RH.

**Feito também.** `operax/rh/ownership.py` traz os 55 campos da matriz — 19 do
sync, 36 do RH — cada campo do sync citando **a coluna do espelho de onde vem**,
que é o que a tela repete como "Secullum · leitura de HH:MM". A conferência
contra o schema real pegou quatro dos dezessete nomes errados na primeira
escrita: `Cadastro` em vez de `NumeroFolha`, `Departamento`/`Empresa` em vez das
FKs uuid, e um `TipoContrato` que não existe. `scripts/95_teste_matriz_rh.py`
entrou no `make db-test` para que isso não dependa de atenção: confere cada
coluna, cada origem no espelho e os dez enums copiados para o Python contra o
`check` do banco.

Duas conclusões vieram do espelho, não de palpite: `secullum."Funcionario"`
carrega `Cpf`, `Rg`, `NumeroPis`, `Nascimento`, `Mae`, `Pai`, `Telefone`,
`Email` e `Endereco` — então **quase todo o bloco de PII é somente-leitura**, o
que convém saber antes de alguém desenhar formulário para ele. `ctps` e
`employment_type` são as exceções: nada no espelho os alimenta, e o dono é o RH.

`operax/rh/validators.py` tem os seis casos como funções puras — nada ali abre
conexão ou conhece tenant — e quatro compositores por domínio, que é como a
regra 1 fica garantida por construção: não existe segundo lugar onde a regra
pudesse ser escrita diferente. `backend/tests/test_rh_validators.py`: **30
asserções**, cada recusa com o par que tem de passar ao lado — um validador que
recusa tudo passa em qualquer teste de recusa e trava o DP.

Duas decisões registradas no código, não escondidas: o limite de retroatividade
de vigência **não tem valor padrão** (quanto retroagir é política de folha, e um
padrão aqui viraria a política por omissão), e a soma de parcelas tolera **dois
centavos**, porque a planilha carrega valor arredondado à mão.

**Gate do R1: cumprido.** `make db-test` verde com a migration 16 · 30 asserções
de validador cobrindo os seis casos · a asserção de que o painel não escreve em
tabela de RH mora no bloco de prova da própria migration.

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

## R2 — Template e pipeline de importação ✅

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

### Andamento em 24/08/2026 — fechado

**As duas decisões que o R1 deixou em aberto, resolvidas como declarado.** Os sete
campos sem coluna ficam **fora do escopo v1** — continuam nomeados em
`ownership.SEM_COLUNA`, e nenhum template os cita. E o parcial é `processed` com
`rows_error > 0`, sem sexto valor no `check` de `app.file_import.status`: a API
devolve `partial` como campo derivado, o banco guarda os fatos e a tela lê o
rótulo. `app.sync_run` tem `partial` no check dela; `app.file_import` não tem, e
inventar o valor mudaria a semântica que a folha já usa.

**Três templates, não sete.** `hr_link`, `hr_employee` e `hr_compensation` têm o
caminho de ida e volta inteiro. Os outros quatro estão declarados em
`templates.SEM_TEMPLATE` com o motivo, e `GET /rh/template/{tipo}` responde
**501 com o motivo** em vez de 404 — "ainda não" e "nunca" são respostas
diferentes para quem está esperando o arquivo:

| Tipo | Por que não fecha o ciclo |
|---|---|
| `hr_document` | `app.document.storage_path` é NOT NULL — documento chega com o arquivo, não com uma linha de planilha |
| `hr_agreement` | `app.financial_agreement.document_id` é NOT NULL por decisão explícita: desconto sem autorização documentada não se registra |
| `hr_leave` | `app.leave_period` não concede escrita ao painel e não tem policy de escrita |
| `hr_movement` | `app.workforce_movement`, idem |

Os dois últimos são **decisão de policy**, e policy para e pergunta.

**O terceiro resultado de linha.** `ok`, `error` e **`unchanged`**. O template vem
preenchido, então um arquivo intocado é um arquivo em que toda linha já diz o que
o banco diz. Sem essa distinção, baixar e subir a planilha de remuneração abriria
uma faixa de vigência nova por pessoa, e reimportar três linhas corrigidas
reescreveria as outras setenta e sete. É o que faz o reimport ser seguro — e é
exatamente o que o gate mede.

**O teto de retroatividade saiu da folha, não de um número.** O R1 deixou
`limite_dias` sem valor padrão de propósito. O import agora o calcula a partir de
`app.payroll_period`: o primeiro dia aberto é o dia seguinte ao fim da última
competência `fechada` (mês 13 termina em 31/12). Sem competência fechada não há
teto — não porque tudo passa, mas porque não há nada a proteger; vigência ausente,
futura ou ilegível continua caindo.

**O arquivo fica guardado, inclusive o recusado.** `app.file_import.storage_path`
é NOT NULL porque o arquivo é a prova: o relatório diz que três linhas caíram, e a
única forma de conferir isso depois é abrir o arquivo que o produziu. O confirm
**relê do storage e revalida** em vez de confiar no veredito do preview — entre
ver o preview e clicar em confirmar, alguém pode ter tomado o ID RH e a folha pode
ter fechado uma competência.

**`_meta` é o que faz o arquivo ter identidade.** Aba oculta com versão de layout,
tipo, tenant e hash do cabeçalho. Arquivo de outro cliente, de outro tipo, de
layout antigo ou com coluna inserida no meio é recusado **inteiro, antes da
primeira linha** — um arquivo errado não tem linha certa. A proteção da planilha é
um empurrão, não a fronteira: a fronteira é `check_owned_fields` no servidor, que
recusa a linha independentemente do que o Excel permitiu.

**Escrita e leitura têm identidades diferentes, e é deliberado.** A leitura vai por
`user_scope` — a RLS decide o que volta, e é isso que faz o escopo valer na
escrita sem a escrita reimplementá-lo: linha que nomeia alguém fora do alcance de
quem enviou o arquivo não resolve a chave. A gravação vai por `tenant_scope`
porque `app.audit_log` não concede insert a ninguém além do `service_role` — o log
é fora do alcance do painel de propósito — e a linha e o log que a descreve
precisam entrar na mesma transação.

**Gate do R2: cumprido.** `backend/tests/test_rh_api.py` faz o caminho inteiro num
teste só: modelo → edição → upload → preview com **3 linhas erradas de três jeitos
diferentes** (ID RH repetido, nome do ponto reescrito, matrícula colada errada) →
confirmação parcial (`applied=2`, `partial=true`, `processed` com `rows_error=3`)
→ reimport das corrigidas, em que as duas que já tinham entrado voltam como
`unchanged` e **não são reescritas**. Cada linha gravada tem `audit_log` com
`depois->'_origem'->>'file_import_id'`.

**132 testes** no pytest (eram 93) e `make db-test` verde. O `95_teste_matriz_rh.py`
ganhou três conferências novas: as colunas que o repositório cita fora da matriz,
o `select` de pré-preenchimento de cada template compilado com `prepare` contra o
schema real, e **as oito instruções fixas do repositório compiladas do mesmo
jeito** — lidas do arquivo, não copiadas, para não divergirem na primeira
alteração.

### O que o R2 não cobre, e é bom saber antes do R3

Os dois `update`/`insert` montados coluna a coluna (`app.employee` e o upsert de
`app.employee_pii`) não passam pelo `prepare`: o que varia neles é nome de coluna,
e isso é o que a matriz e a lista de literais conferem. O caminho completo contra
um Postgres de verdade — endpoint, RLS e escrita — é assunto do R3, que traz o
formulário e com ele a segunda metade do mesmo funil.

O bucket do Storage (`IMPORT_BUCKET`, default `imports`) **precisa existir e ser
privado** no projeto Supabase. Não é migration: `storage.*` é gerenciado pelo
Supabase. Se faltar, o upload responde 503 dizendo qual bucket falta.

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
