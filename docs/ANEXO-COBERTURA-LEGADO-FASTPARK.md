<!-- verificar-docs: inexistentes-de-proposito app.unit_compliance_report app.transport_fare app.benefit_plan app.work_post app.work_schedule_day -->
<!-- `app.work_schedule_day` entra na lista porque a §6 a CITA para dizer que
     ela não existe. As outras quatro são entidades que esta etapa vai criar. -->

# OperaX — cobertura do sistema legado FastPark (DP)

Levantamento a partir de 16 telas do sistema que o cliente **já usa hoje** para
Departamento Pessoal. Substitui a premissa que abriu a etapa de RH: o que vai
ser aposentado não é uma planilha de 17 abas — é um **aplicativo em operação**,
com KPIs derivados, rotinas mensais de geração, exportação para banco e um
módulo de conformidade por unidade que a documentação de RH não previa.

Fonte: capturas de tela enviadas em 28/08/2026. **Nenhum dado pessoal das
capturas foi transcrito para este documento** — nomes, CPF, RG, telefone,
endereço, filiação e conta bancária aparecem nas telas e ficam nas telas.

> Precedência: para a fase de RH, a documentação de RH é a fonte da verdade
> (`ANEXO-CONTEXTO-SESSAO.md` §3). Este anexo **estende** `PRD-RH.md` e
> `SPEC-RH.md`; onde contradiz, a contradição está marcada como decisão aberta,
> não como fato.

---

## 1. O que as telas mudam no entendimento da etapa

Quatro coisas, em ordem de impacto:

1. **O legado não é um cadastro — é um sistema com rotinas.** Gestão de
   Benefícios (cestas), Gestão de Vale Transporte e Gestão de Folha não guardam
   dado: **geram** o pedido do mês, com regra de direito, período de apuração e
   arquivo de saída. Substituir a tela de cadastro não aposenta o legado; a
   planilha morre quando a **rotina** for para o OperaX.
2. **Laudos por unidade não existem no desenho de RH.** PCMSO, PGR, LTCAT+LTIP
   com vencimento, situação e histórico de renovação, por unidade. Não é dado de
   colaborador: é conformidade de local. Entidade nova.
3. **Duas pendências deixam de ser pendência.** `QUADRO_POSTOS` já é fonte de
   escala em produção (a tela de VT declara isso), e o formato de exportação já
   está decidido pelo uso (Excel + PDF + arquivo de banco).
4. **Duas regras do projeto são tocadas de frente.** Conta bancária — fora do
   escopo v1 por decisão — é insumo obrigatório do arquivo de banco do VT. E o
   painel inicial nomeia colaborador com parcela em aberto na tela de abertura.

Três módulos aparecem no menu e **não foram abertos**: `Comercial`,
`Financeiro`, `Unidades`. Este inventário não os cobre. `Unidades` é o mais
urgente — é onde deve morar o Quadro de Postos, do qual o VT depende.

---

## 2. Inventário — Painel inicial (Início)

### 2a. KPIs de topo — fórmula declarada na própria tela

| Variável | Fórmula declarada | Destino | Status |
|---|---|---|---|
| Total analisado | registros no filtro corrente | contagem sobre `app.employee` | ➕ novo KPI |
| Efetivo ativo | vínculos ativos | P2 §1 da etapa de operação | ✅ previsto |
| Desligamentos | vínculos desligados (histórico) | `app.employee` status | ✅ previsto |
| Retenção | `ativos / total` | derivado | ⚠ ver nota |
| Folha salarial base | `salário + ajuda de custo + cargo de confiança + periculosidade`, só ativos | `app.employee_compensation` vigente | ➕ fórmula nova |
| Média (folha base) | folha base ÷ ativos | derivado | ➕ |
| Vale refeição (VR) | soma mensal, ativos — **fora** da folha base | `employee_compensation` | ➕ |
| Ajuda de custo | soma mensal — **dentro** da folha base | `employee_compensation` | ➕ |
| Cargo confiança + periculosidade | soma mensal — **dentro** da folha base | `employee_compensation` | ➕ |

**Nota sobre Retenção.** `ativos / total no filtro` não é retenção — é a
proporção de ativos na base carregada. Muda de significado conforme o filtro, e
some se a base virar histórico completo. Ou ganha janela declarada
("desligamentos nos últimos 12 meses ÷ efetivo médio") ou muda de rótulo. É
canetada de produto, não de engenharia.

**Nota sobre a folha base.** Esta é a definição de custo de pessoal que o cliente
usa hoje e reconhece. O consolidado de custo do OperaX precisa **bater com ela
na vírgula** no dia da virada, ou a substituição não é aceita. Vira asserção,
não expectativa.

### 2b. Unidades com sinistro ativo

| Variável | Conteúdo | Destino | Status |
|---|---|---|---|
| Unidades com parcela em aberto | contagem | `app.financial_agreement` + `agreement_installment` | ✅ previsto |
| Lista unidade → colaboradores | **nome do colaborador, na home** | — | ⚠ **conflito** |

O painel de abertura nomeia quem tem parcela não paga. No modelo do OperaX isso
é conteúdo individual de **domínio sensível (remuneração)** exposto num
agregado — a mesma classe de problema da regra 7. Duas saídas: o card mostra só
a contagem por unidade e o nome exige o domínio, ou o card inteiro fica atrás do
domínio. **Decisão do owner** (§6, item 1).

### 2c. Painel de alertas — 8 contadores + 8 listas

| Contador | Janela | Fonte | Status |
|---|---|---|---|
| Aniversariantes | mês corrente | `employee_pii.data_nascimento` | ➕ |
| Em experiência | 1ª (1–30d) · 2ª (31–60d) | admissão + hoje | ➕ |
| CNH vencidas | data < hoje | `app.document` | ✅ previsto |
| CNH a vencer | 90 dias | `app.document` | ✅ previsto |
| Vencimento ASO | vencidos + a vencer | `app.occupational_exam` | ◐ janela não declarada na tela; é config em `app.document_type` |
| Férias próximas | próximo mês | `app.leave_period` | ✅ previsto |
| Em férias hoje | data corrente | `app.leave_period` | ✅ previsto |
| Data limite férias | 90 dias | limite = admissão +12m | ➕ |

As listas repetem o contador com colaborador, empresa e o valor que dispara
(dia do mês, "59º dia / 60d", "25/03/2026 · vencida", "14d restantes").

**Duas ações saem daqui para fora do sistema:** o botão **Enviar Parabéns** e o
botão **Solicitar CNH**. São mensagens ao colaborador — entram como
`app.message_template` (`birthday_greeting`, `cnh_renewal_request`) sob a regra
11: `(template, variáveis, destino)`, nunca string pronta. Se o tenant estiver
em `meta_cloud`, precisam de aprovação da Meta antes de existirem no botão;
`fn_whatsapp_readiness()` já reporta isso.

### 2d. Raio-X de benefícios (folha ativa)

Usuários V.T. · Plano odonto · Plano de saúde (com custo aproximado) ·
Dependentes (total) · Vínculos em saúde · VR/Cesta e demais · VR · Ajuda de
custo · Cargo confiança + periculosidade. Todos são contagem ou soma sobre a
vigência de remuneração ativa. ➕ novos como conjunto; a base existe.

### 2e. Tabelas do rodapé

- **ASO a vencer / vencidos** — colaborador, empresa, vencimento, status com
  dias (`Vencido (1697d)`). ✅ previsto.
- **Resumo financeiro por empresa** — empresa, ativos, total folha (ativos).
  ✅ e **confirma a regra 5**: o legado agrega por `colaborador → empresa`
  (campo REGISTRO da ficha), não por departamento. Aparecem 5+ CNPJs; um deles
  rotulado `CONTRATO` — provável balde, não empresa. Entra na curadoria.

---

## 3. Inventário — Cadastro (ficha)

### 3a. Ações e filtros

Importar Excel · Novo · Editar · Desligar · **Excluir Cadastro** · Relatório
personalizado · Relatório Geral. Filtros: empresa, funcionário, busca rápida
(nome/cargo/unidade), status. Contador "N registro(s) no filtro". Abas da ficha:
**Ficha · Renovação ASO · Alterações salariais**.

⚠ **Excluir Cadastro é delete físico.** O OperaX não deleta — desliga, revoga,
inativa. É mudança de comportamento visível para o usuário e precisa entrar no
treinamento, não só no código.

✅ **Alterações salariais** já é a linha do tempo que `employee_compensation`
implementa — o cliente já opera por vigência. A regra 4 do PRD-RH não é
novidade para ele.

### 3b. Campos — dono do campo

Confrontado com a matriz de `SPEC-RH.md` §4. **Sync** = Secullum, **RH** =
editável no OperaX, **➕** = não estava na matriz.

| Campo | Dono proposto | Nota |
|---|---|---|
| matrícula, nome, admissão, status | Sync | inalterado |
| registro (empresa/CNPJ) | Sync | é o eixo do consolidado (regra 5) |
| unidade (lotação) | Sync | inalterado |
| **atuando (unidade)** | **derivado** | ver §4.1 — resolve pendência aberta |
| cargo, nível | RH | vigência |
| cód. de posto | RH ➕ | chave do Quadro de Postos |
| escala | derivado ➕ | vem do Quadro de Postos |
| carga horária, jornada | RH ➕ | jornada é **texto livre** hoje |
| salário base | RH | vigência · domínio remuneração |
| ajuda de custo, VR, cesta (S/N) | RH | vigência · domínio remuneração |
| vale transporte (S/N), tipo VT, VT unitário, VT ida+volta | RH ➕ | insumo da rotina de VT |
| plano de saúde (titular) | RH | domínio remuneração |
| CPF, RG, telefone, nascimento, endereço, filiação | RH | `employee_pii` |
| CNH: número, categoria, vencimento | RH | `app.document` |
| vencimento ASO | RH | `app.occupational_exam` — só validade/aptidão |
| idade atual, tempo de casa | derivado | nunca coluna |
| estado civil, raça/cor, grau de instrução, PCD | RH ➕ | `employee_pii`; PCD e raça/cor são dado sensível |
| triênios | RH ➕ | insumo de folha |
| uniforme | RH | já na matriz |
| dependentes (qtd) e (nomes) | RH ➕ | nome de terceiro — `employee_pii` |
| **banco / agência / conta** | — | ⚠ **fora do escopo v1** — ver §5.1 |
| **foto do colaborador** | RH ➕ | ver §5.3 |
| documentos anexados / de rescisão | RH | storage privado do tenant |
| férias (atual), obs. férias, histórico | RH | `app.leave_period` |
| movimentações (embutidas na ficha) | RH | `app.workforce_movement` |
| histórico de sinistros | RH | domínio remuneração |

---

## 4. Inventário — as rotinas (o que a planilha não mostrava)

### 4.1 Movimentações

Registro: funcionário, unidade atual, cód. posto atual, unidade origem, unidade
destino, cód. posto destino, início, fim, observações. Histórico com editar e
excluir.

A tela declara a regra: **"ao salvar, a ficha cadastral é atualizada com a
unidade destino e o cód. posto destino da movimentação vigente (sem data fim ou
fim futuro)"**.

Isso **resolve** um dos três campos que a `SPEC-RH.md` §4 marcou "confirmar com
o cliente": *unidade de atuação quando difere da lotação*. Ela difere, e não é
campo editável — é **projeção da movimentação vigente**. Vira coluna derivada,
com a mesma semântica, ou o OperaX e o legado divergem no primeiro remanejamento.

⚠ Excluir movimentação é delete físico e altera retroativamente onde a pessoa
estava. No OperaX: encerrar com data fim, nunca apagar.

### 4.2 Gestão de Benefícios — cestas (rotina mensal)

Período aquisitivo (mês) · Cestas com direito · **Perdeu direito** ("faltas
injustificadas ou admissão após início do período") · Unidades no pedido
(agrupadas) · tabela unidade / endereço / CNPJ / empresa / com direito / perdeu
direito / qtd.

➕ **Rotina nova por inteiro** — mas sobre base que existe: depende de
`app.leave_period` (falta injustificada), de admissão, e do endereço da unidade
com o CNPJ da empresa, que `app.unit` e `app.company` já guardam. O pedido sai
agrupado por unidade para o fornecedor.

Cuidado de leitura: `DECISAO-RH-UPLOAD-TELAS.md` §7 descarta a **aba** CESTAS da
planilha. Descartar a aba não descarta a **função** — a aba era o resultado, a
rotina é o que o produz. Sem isso o cliente mantém a planilha só para pedir cesta.

### 4.3 Gestão de Vale Transporte — rotina mensal com saída para banco

Período padrão **21 → 20** · dias úteis · total previsto · Excel · PDF ·
**Exportar arquivo banco**. Colunas: funcionário, registro, unidade (atuando),
**escala (quadro)**, VT unitário, ida+volta, dias base, **faltas período
anterior**, dias líquidos, total, **conta**.

A tela declara duas fontes: *"VT unitário e conta vêm da ficha cadastral; a
escala é obtida do **Quadro de Postos** (código do posto + unidade)"* e *"faltas
injustificadas: mês civil anterior ao início do período (regra 21→20)"*.

Três consequências:

1. **O Quadro de Postos já é fonte de escala em produção.** A pendência 3 do
   `DECISAO-RH-UPLOAD-TELAS.md` ("CÓD POSTOS como fonte de escala esperada —
   avaliar depois da v1") está respondida pelo uso. E o §7 do mesmo documento
   lista `QUADRO_POSTOS` como aba "fora — não se importa": correto para a aba,
   errado para a entidade. Precisa existir `app.work_post` (unidade + código →
   escala) ou a rotina de VT não roda — e o motor de detecção ganha, de graça, a
   fonte de escala que hoje ele infere. O que falta é o **elo posto → escala**,
   não um modelo de escala.
   ⚠️ **Corrigido em 05/09/2026.** Este item afirmava que a estrutura da escala
   *"já existe — `app.work_schedule_day` guarda `entry_1 / exit_1 / entry_2 /
   exit_2` por dia da semana"*. **Essa tabela não existe**, e a frase se propagou
   daqui para a `SPEC-DP.md` §0 e para o `CLAUDE.md`. A conclusão do item
   sobrevive — a escala existe e o que falta é o elo —, mas em três camadas com
   outros nomes: `secullum."HorarioDia"` (a escala por dia da origem),
   `app.schedule_rotation_map` (ciclo, onde a origem cala) e
   `app.expected_workday` (materializada por pessoa e data). Ver `SPEC-DP.md`
   §0-bis. Consequência de forma: o elo é um `secullum_schedule_id` no
   `app.work_post`, nunca uma FK para tabela de escala por dia.
2. **Conta bancária é insumo obrigatório**, não conveniência. §5.1.
3. O calendário 21→20 e "faltas do mês civil anterior" são regra de negócio
   escrita — copiar literal, não reinventar.

### 4.4 Benefícios — catálogos com reajuste

Saúde · Odonto · Vale refeição, cada um com **Relatório · Cadastro · Reajuste ·
Histórico**. Saúde: operadora, beneficiários (funcionário, plano, valor plano,
desconto).

Vale transporte: catálogo de tipos (Ônibus, Metrô, Integração ônibus e metrô)
com valor unitário e valor ida-e-volta, também com Reajuste e Histórico.

➕ **Grão que falta no modelo.** `employee_compensation` guarda o valor *por
colaborador*. O que não existe é o **catálogo do tenant** — operadora, plano,
tarifa — com vigência própria: um reajuste de tarifa muda 69 pessoas de uma vez,
e hoje isso seria 69 vigências à mão. Propostas: `app.benefit_plan` e
`app.transport_fare`, ambas com histórico, ambas alimentando o valor por
colaborador.

### 4.5 Gestão de Folha de Pagamento — por rubrica

Importar **PDF ou XLSX** · Modo (folha importada) · Tipo de folha (mensal) ·
funcionário · referência MM/AAAA · salário base (do cadastro) · Recalcular
líquido · Gravar · Excel. Totais: **Bruto (P+I) · Descontos (D) · Líquido**.
Tabela de verbas: **código · rubrica · tipo · qtd/% · ref. · valor · travar**.
Histórico de importações com data/hora, tipo de cálculo, colaborador, CPF,
registro, conta, valor, fonte.

✅ **O destino já existe e o grão bate.** `app.payroll_entry` tem
`code · description · nature · reference · amount` — exatamente código, rubrica,
tipo, ref. e valor da tela. E `nature` já é a classificação: `earning`,
`deduction`, `base`, `payroll_charge`, `informational` — o "P / D / I" do
legado, com dois casos a mais.

➕ **Isto destrava a pendência 3 da pauta do owner.** O mapa "código de evento de
folha → categoria" estava travado numa reunião com a contabilidade. A tabela de
destino existe, e o legado já tem os códigos e as rubricas **classificados pelo
cliente**. Falta só a tabela de mapeamento `code → nature/categoria` para semear
a partir do que já está lá. A reunião deixa de ser levantamento e vira
conferência de uma lista pré-carregada — o que o pacote P3 ia construir, quase
construído.

Duas colunas do legado não têm par: **qtd / %** (confirmar se `reference`
absorve) e **travar**, uma trava de recálculo por linha. Decisões pequenas do
sprint de folha, não da etapa de RH.

### 4.6 Férias

Data limite de férias (admissão · data limite · observação · **Calcular +12
meses** · salvar) e Novo período (início · fim · quantidade de dias · período
aquisitivo `2025/2026`). ✅ `app.leave_period` cobre o período; ➕ **data limite**
e **período aquisitivo** são campos novos.

### 4.7 Faltas e Atestados

Funcionário · tipo (falta injustificada, …) · início · fim · observações ·
**anexo de arquivo**. ✅ `app.leave_period` com rótulo neutro cobre — e o
anexo cai em storage privado, como os documentos.

**Dependência que precisa estar escrita:** falta injustificada aqui é o que
tira a cesta (§4.2) e reduz dias líquidos do VT (§4.3). Não é registro
isolado — é entrada de duas rotinas financeiras. Errar aqui custa dinheiro do
colaborador.

### 4.8 Laudos (por unidade) — módulo inteiro ausente do desenho

Cadastro por **unidade + tipo de laudo** (PCMSO, PGR, LTCAT + LTIP) com
vencimento, observações, situação (`EM DIA`), contador de histórico e ação
**Renovar** — "ao renovar, informe a nova data de vencimento; o vencimento
anterior fica no histórico". Filtros por unidade e por situação.

➕ **Entidade nova: `app.unit_compliance_report`.** Não é RH de pessoa — é
conformidade de local, com o mesmo padrão de vencimento/renovação que
`occupational_exam` usa para o ASO, e com histórico em vez de edição. Cabe no
módulo de Unidades, não na aba Colaboradores. **Não estava em nenhum dos quatro
domínios do PRD-RH** e precisa de decisão de escopo (§6, item 4).

---

## 5. Conflitos com regra vigente — parada obrigatória

### 5.1 Conta bancária (⚠ o mais grave)

`PRD-RH.md` §4 e `DECISAO-RH-UPLOAD-TELAS.md` §8: *"conta, agência e banco ficam
fora do escopo v1; se entrar um dia, é domínio sensível novo e decisão à parte"*.

O legado usa conta em **dois lugares de produção**: a coluna `CONTA` do relatório
de VT e o botão **Exportar arquivo banco**. Sem conta, a rotina de VT não
substitui o legado — entrega uma planilha que alguém completa à mão, que é
exatamente o que a etapa promete acabar.

Três caminhos, em ordem de preferência técnica:

- **A. Domínio sensível novo** (`banking`), com eixo de permissão próprio, campo
  mascarado na tela, e o arquivo de banco gerado pelo backend sem que a conta
  passe pelo navegador. Custo: uma migration, um domínio, asserções na suíte.
- **B. Fora do OperaX** — a rotina de VT entrega o arquivo sem conta e o cliente
  cruza com o cadastro do banco dele. Custo zero de segurança, custo alto de
  promessa: o legado sobrevive.
- **C. Adiar** — VT entra na v2. Honesto, mas o cliente perde a rotina que ele
  usa toda competência.

Recomendação registrada: **A**. É a única que cumpre "a planilha é aposentada"
sem afrouxar o modelo — e o modelo já tem três eixos de autorização justamente
para caber um quarto domínio sem gambiarra.

### 5.2 Nome de colaborador com parcela em aberto, no painel inicial (§2b)

Decisão do owner. Recomendação: contagem por unidade na home; nome só com o
domínio de remuneração.

### 5.3 Foto do colaborador

Não está em nenhum documento. É dado biométrico-adjacente sob LGPD, vai para
storage privado do tenant com URL assinada e prazo curto, nunca bucket público,
e não entra em template de import. Se não for necessária à operação, **não
migrar** é a resposta mais barata e mais segura — pergunta para o cliente.

### 5.4 Deletes físicos

Excluir Cadastro, Excluir movimentação, Limpar histórico de importações. Todos
viram encerramento/revogação no OperaX (regra 6 estendida). Não é bug do legado
a corrigir — é diferença de comportamento a comunicar.

### 5.5 Diagnóstico

Nada nas 16 telas mostra CID, diagnóstico ou restrição médica. O legado guarda
aptidão e validade de ASO, e o anexo de atestado é arquivo. **A regra 10
continua compatível com a operação real** — o que era premissa vira observação.

---

## 6. Decisões que este inventário coloca na mesa (owner)

1. **Card de sinistro na home** — contagem ou nome? (§5.2)
2. **Conta bancária** — A, B ou C? (§5.1) É a decisão de maior consequência.
3. **Retenção** — janela declarada ou novo rótulo? (§2a)
4. **Laudos por unidade** — entram nesta fase, viram fase própria, ou ficam
   fora? (§4.8) Não são RH de pessoa; a fase de RH não os cobre por desenho.
5. **Foto** — migra ou não? (§5.3)

Não entram nesta lista, e é bom que não entrem: a **janela do alerta de ASO** é
configuração, não decisão — `app.document_type` já tem `requires_expiry` e
`expiry_alert_days` por tipo de documento, e basta preencher; e **travar verba**
é decisão do sprint de folha (§4.5).

Duas pendências antigas **saem** da lista por observação, não por decisão:

- **Formato de exportação** (pauta item 6): o cliente já usa **Excel + PDF**, e
  mais um **arquivo de banco** para VT. Não é escolha — é requisito observado.
- **Mapa código de evento → categoria** (pauta item 3): o legado já tem os
  códigos, as rubricas e o tipo. A reunião com a contabilidade vira conferência.

E uma **muda de status**: `QUADRO_POSTOS` deixa de ser candidata a fonte de
escala e passa a ser dependência declarada da rotina de VT (§4.3).

---

## 7. O que este anexo NÃO cobre

- Os módulos **Comercial**, **Financeiro** e **Unidades** — presentes no menu,
  não abertos. `Unidades` é o mais urgente: é onde deve estar o Quadro de Postos.
- Regras de cálculo não visíveis na tela (arredondamento de dias úteis, feriados
  usados no VT, comportamento em admissão/desligamento no meio do período).
- O formato exato do arquivo de banco (layout, banco de destino).
- O mecanismo de persistência do legado ("salvar na nuvem", "todas as abas,
  dados + documentos") e, com ele, o **caminho de migração** do que já está lá.

Cada um desses é uma pergunta curta ao cliente, e nenhum deles bloqueia começar
pelo que já está mapeado.
