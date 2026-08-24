<!-- verificar-docs: inexistentes-de-proposito app.employee.hr_code -->

# OperaX — SPEC técnica da etapa RH

Complementa `SPEC-TECNICA.md` com o **como** desta etapa. O quê e o porquê estão
em `PRD-RH.md`; as decisões de origem em `DECISAO-RH-UPLOAD-TELAS.md`. Nenhuma
seção aqui altera o que já está construído — esta etapa só acrescenta.

---

## 1. Banco — migration 16 (`hr_management`)

Uma migration, idempotente, no padrão das 15 existentes (termina com bloco
`do $$` que falha alto). Conteúdo:

**1a. Chave alternativa do RH.** Coluna `hr_code text` em `app.employee`,
anulável, com unicidade parcial por tenant:

```sql
alter table app.employee add column if not exists hr_code text;
create unique index if not exists employee_hr_code_unique
  on app.employee (tenant_id, hr_code) where hr_code is not null;
comment on column app.employee.hr_code is
  'ID RH do cliente. Chave ALTERNATIVA — nunca composta com a matrícula: cada '
  'uma identifica sozinha, e divergência entre elas é erro de linha no import.';
```

**1b. Tipos de importação.** O check de `type` em `app.file_import` passa a
aceitar, além do existente: `hr_link`, `hr_employee`, `hr_document`,
`hr_leave`, `hr_movement`, `hr_compensation`, `hr_agreement`. Um tipo por
template — "uma tabela por vez" vira restrição, não convenção.

**1c. Sem tabela nova.** Os destinos já existem (migrations 04–08):
`app.employee`, `app.employee_pii`, `app.employee_position`,
`app.employee_compensation`, `app.document`, `app.occupational_exam`,
`app.leave_period`, `app.workforce_movement`, `app.financial_agreement`,
`app.agreement_installment`. A matriz dono-do-campo é **constante do backend**
(seção 4), não tabela — muda por deploy, com revisão, nunca por painel.

RLS: inalterada. Escrita continua exclusiva do caminho 2 (FastAPI com
`service_role` + revalidação); o painel não ganha grant de escrita nenhum.

## 2. O template

Arquivo `.xlsx` **gerado pelo sistema**, nunca genérico:

- **Aba de dados** — cabeçalho travado (proteção de planilha), uma linha por
  registro, **pré-preenchida com o dado atual**. Colunas de chave (matrícula,
  ID RH) impressas e bloqueadas. Colunas do sync presentes porém bloqueadas,
  com nota "origem: Secullum". Enums como dropdown (validação de dados do
  Excel) alimentados do catálogo do tenant.
- **Aba oculta `_meta`** — `layout_version`, tipo (`hr_document`…), tenant,
  gerado em, hash do cabeçalho. Upload sem `_meta` ou com hash divergente é
  recusado na hora com "baixe o modelo atual" — nunca importado "no melhor
  esforço".
- **Domínio sensível gera template sensível**: o de `hr_compensation` só é
  baixável por quem tem escrita no domínio de remuneração. O download em si é
  registrado em `app.audit_log`.

O `layout_version` gravado em `app.file_import.layout_version` permite evoluir
o modelo sem quebrar arquivo antigo em trânsito: o backend mantém o parser da
versão anterior por uma janela declarada.

## 3. Pipeline de importação

Reuso do que a folha já usa — `app.file_import` com `rows_total/rows_ok/
rows_error` e `report` jsonb por linha — com o fluxo de 4 passos da tela de
Importação (tipo → arquivo → **preview** → confirmar).

Validações por linha, nesta ordem (a primeira falha marca a linha):

1. `_meta` válida e `layout_version` aceita (falha de arquivo, não de linha).
2. Chaves: matrícula e/ou `hr_code` existem no tenant; **se ambas presentes e
   apontarem para pessoas diferentes → "chaves divergem"** com os dois nomes.
3. Campo bloqueado alterado (coluna do sync editada) → linha falha com "campo
   pertence ao Secullum; a alteração não teria efeito".
4. Tipos e enums (datas, valores, dropdowns).
5. Regras do domínio: vigência com `desde` retroativo além do limite; parcela
   com soma diferente do total do acordo; documento com validade no passado
   (aviso, não erro); afastamento sobreposto ao existente.
6. Duplicidade contra o banco e dentro do próprio arquivo.

Confirmação grava **só as linhas válidas**; o import fica `partial` até as
demais entrarem (mesma semântica da folha). Toda gravação: upsert pela chave,
`audit_log` com `file_import.id` como origem, nunca delete físico.

> **Resolvido em 24/08/2026 (R2).** `app.file_import.status` não tem o valor
> `partial` — o check aceita `received`, `validating`, `validation_error`,
> `processed` e `discarded`. A semântica da folha é `processed` com
> `rows_error > 0`, e é essa que vale: o banco guarda os fatos, e "parcial" é
> rótulo derivado, devolvido pela API no campo `partial`. Cada envio é um
> `file_import` próprio — o registro de **um arquivo**, que não muda quando outro
> arquivo entra depois. "Fechar o import" é o conjunto de pessoas ficar completo,
> não um contador antigo ser reescrito.

## 4. Matriz dono-do-campo (proposta — confirmar antes do template congelar)

| Campo | Dono | Na tela e no template |
|---|---|---|
| matrícula, nome, data de admissão, data de demissão, unidade (lotação Secullum) | **Sync** | somente-leitura, "Secullum · leitura de HH:MM" |
| status do vínculo (ativo/desligado) | **Sync** | somente-leitura; a planilha DESLIGADOS serve de conferência na carga, não de fonte |
| `hr_code`, CBO, supervisor, atuando, uniforme | **RH** | editável |
| cargo, nível (posição) | **RH** | vigência (nunca edição direta) |
| salário, benefícios (VR, planos, cesta, VT), periculosidade, cargo de confiança | **RH** | vigência; domínio remuneração |
| documentos e vencimentos, ASO (aptidão + validade) | **RH** | editável; domínio conforme o tipo |
| afastamentos (rótulo neutro), movimentações | **RH** | editável |
| acordos e parcelas | **RH** | editável; domínio remuneração |

Três campos ficam **marcados para confirmação com o cliente** antes de entrar
em template: *supervisor* (existe no Secullum? se sim, vira sync), *unidade de
atuação* quando difere da lotação, e *data de demissão* quando o RH souber
antes do Secullum. Até lá, esses três não são editáveis — aparecem como sync.

> **Resolvido em 24/08/2026 (R1/R2).** A conferência contra o schema real mostrou
> que sete campos desta tabela não têm coluna em lugar nenhum: CBO, uniforme,
> nível, os quatro benefícios (VR, planos, cesta, VT), periculosidade, cargo de
> confiança e unidade de atuação. Eles ficam **fora do escopo v1**, nomeados em
> `ownership.SEM_COLUNA` para não sumirem, e nenhum template os cita. Criar as
> colunas é uma migration 17 e uma decisão de produto — não uma consequência de
> template.
>
> A matriz que vale está em `backend/operax/rh/ownership.py`, conferida contra o
> schema por `scripts/95_teste_matriz_rh.py` a cada `make db-test`.

## 5. Backend (FastAPI — caminho 2)

Rotas novas sob `/rh`, todas com revalidação de papel e domínio:

- `GET /rh/template/{type}` → gera e devolve o `.xlsx` pré-preenchido.
- `POST /rh/imports` → recebe arquivo, valida, cria `file_import` em preview e
  devolve o relatório por linha. **Não grava dado.**
- `POST /rh/imports/{id}/confirm` → aplica as linhas válidas.
- `GET /rh/employees` → lista da aba Colaboradores (filtros + vencimentos nos
  próximos N dias). Leitura **via FastAPI**, não via PostgREST: a lista mistura
  domínios e o recorte por permissão é responsabilidade do backend.
- CRUD por domínio: `PATCH /rh/employees/{id}` (só campos de dono RH),
  `POST /rh/employees/{id}/position` e `/compensation` (nova vigência),
  `POST/PATCH` para documentos, afastamentos, movimentações, acordos e
  parcelas. **Nenhuma rota DELETE** — encerrar, revogar ou inativar.

O validador de linha do import e o validador do formulário são **a mesma
função** por domínio (`operax/rh/validators.py`) — regra 1 do PRD garantida
por construção, não por disciplina.

## 6. Conversor de implantação

Script de linha de comando (`scripts/rh_carga_inicial.py`), roda **na
implantação, em ambiente controlado**, nunca como serviço:

1. Lê a planilha do cliente (caminho local).
2. Emite os templates de domínio preenchidos, na ordem: vínculo → cadastro/
   posição → documentos/ASO → afastamentos/movimentações → remuneração/acordos.
3. Emite o **relatório de descarte**: cada coluna e aba não importada, com o
   motivo (CID → regra 10; conta bancária → fora de escopo; abas de dashboard →
   substituídas pelo sistema). Formato legível para anexar à ata de implantação.
4. **Não escreve no banco.** A entrada é sempre pelos templates + preview +
   confirmação humana.

FÉRIAS (matriz por ano) é convertida para formato longo; DESLIGADOS entram como
colaboradores com status desligado, sem CID.

## 7. Telas (aba Colaboradores da Administração)

Especificação de comportamento — o desenho é a rodada 7 do Claude Design:

- **Lista**: filtros (unidade, status, domínio de pendência), coluna "próximos
  vencimentos" (ASO, CNH, experiência 30/60d), busca. Linha abre o detalhe.
- **Detalhe em abas por domínio** — cada aba aparece **somente** para quem tem
  o domínio (leitura); botões de edição somente com escrita. Sem cadeado, sem
  cinza.
- **Proveniência por campo**: bloco do sync agrupado e rotulado com origem e
  horário da última leitura; blocos do RH editáveis inline ou por drawer.
- **Remuneração e posição como linha do tempo** + ação "nova vigência"
  (desde, valor/cargo, motivo). Corrigir = revogar + criar.
- A aba Colaboradores é visível por papel (DP/RH) **sem** ver Integrações ou
  Usuários — visibilidade de aba segue papel, como decidido.
- Importação de RH usa a tela de Importação existente com seletor de tipo.

## 8. Segurança e LGPD

- PII, remuneração e saúde continuam nos domínios respectivos; o template
  espelha o domínio — quem não tem o domínio não baixa o template dele.
- Arquivos importados ficam em storage privado do tenant (`storage_path` de
  `app.file_import`), com retenção definida; nunca em bucket público.
- Diagnóstico/CID: sem coluna em template, sem campo em tela, sem coluna em
  tabela — as três camadas negam.
- Toda escrita (formulário, import, carga) referencia autor e origem em
  `app.audit_log`.

## 9. Testes que fazem parte da entrega

- `make db-test` estendido: migration 16 aplica limpa; unicidade de `hr_code`
  por tenant; asserções de que o painel **não** tem grant de escrita nas
  tabelas de RH.
- pytest: validadores por domínio (linha válida, chave divergente, campo do
  sync alterado, vigência retroativa, parcela inconsistente, template sem
  `_meta`); conversor gera os templates e o relatório de descarte a partir de
  uma planilha de fixture **sintética** (nunca a real).
- E2E: baixar template → editar → subir → preview com erro por linha →
  confirmar parcial → conferir na aba Colaboradores.
