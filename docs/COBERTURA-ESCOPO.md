# OperaX — cobertura do escopo da proposta

Confronto item a item entre o **escopo contratado** e o que existe hoje em
migrations, views, RPCs e nos documentos de produto. Verificado contra o schema
real gerado pela suíte, não de memória.

Legenda: ✅ coberto · ⚠️ parcial · ❌ falta · 🔒 bloqueado por dependência externa

**Resultado: 21 lacunas** (era 27). Fecharam: a cadência de sync, a agregação
por gestor, a fila de pendentes de justificativa (27/08), as duas métricas que o
assistente não alcançava (28/08), e os itens 21 e 22 — que **já estavam
aplicados no PRD** e continuavam contados aqui. Nove delas mudam o escopo de
trabalho de forma relevante; o resto é volume.

---

## Mudança incorporada nesta rodada

O escopo agora decide: **a integração com o Domínio na v1 é upload de relatório
em Excel**, não API. Consequências:

| O que muda | Antes | Agora |
|---|---|---|
| Caminho da folha | API com fallback para arquivo | Arquivo é **o** caminho |
| Dependência de terceiro | Thomson Reuters / contabilidade liberar API | Contabilidade mandar uma planilha |
| Risco "Domínio não libera" | Alto, na tabela de riscos do PRD | **Neutralizado** |
| Prazo da Fase 3 | 3–4 semanas *após* liberação de acessos e documentação | Não depende mais de acesso externo |
| Trabalho novo | — | Template publicado, tela de upload, validação, relatório de erro |

O modelo de dados já suportava (`app.file_import`, `payroll_entry.source`), mas
**a funcionalidade de importação não existia em nenhum sprint** — estava como
plano B. Agora é caminho crítico da Fase 3.

---

## 27/08/2026 — a lista de lacunas estava contando trabalho já feito

Três correções, e nenhuma delas veio de memória:

| O que este documento dizia | O que a medição diz |
|---|---|
| "O catálogo tem 8 métricas" | `select count(*) from app.metric` = **9**. Faltava `data_freshness` |
| Itens 21 e 22: ajustar o PRD | O PRD já não contém nenhuma das duas afirmações — a auditoria de 24/08 registrou isso em A18 e ninguém deu baixa aqui |
| §4.5: "mais a passada diária de backfill de 7 dias" | Produção não faz backfill. O runner que roda lá desde 25/08 carimba janela deslizante fixa de 2 dias |

A lista de lacunas é lida por quem planeja a próxima sprint. Superestimada, ela
faz replanejar trabalho pronto — que é exatamente o que a auditoria apontou em
A17 sobre o `SPRINTS.md`.

---

## 4.3 Dashboard de gestão de ponto

O escopo lista 18 indicadores como mínimo. Cobertos: 14 + 2 com o rótulo que o
dado sustenta. Faltam 2.

| # | Indicador | Status | Onde está / o que falta |
|---|---|---|---|
| 1 | Total de colaboradores ativos | ✅ | `active` no monitor diário — e é ele que revela `unrostered`, ativo sem jornada prevista |
| 2 | Colaboradores presentes no dia | ⚠️ | Entregue como **"com marcação até a leitura de HH:MM"** (`with_punch`), lido de `app.batida_marcacao`. O número é o pedido; o rótulo "presentes" é a decisão **A12**, aberta com o dono — ver abaixo |
| 3 | Colaboradores ausentes | ⚠️ | Idem, como `without_punch`. "Sem marcação até a leitura" e "ausente" não são a mesma frase, e a diferença cai sobre uma pessoa com nome |
| 4 | Colaboradores em férias | ✅ | `on_vacation` no monitor — de `app.expected_workday.day_type`, que é onde férias é fato do dia (ver `cadastro.py`), não de `app.employee.status` |
| 5 | Colaboradores afastados | ✅ | `on_leave`, mesma fonte |
| 6 | Colaboradores com atraso | ✅ | `late_entry` |
| 7 | Marcação incompleta | ✅ | `incomplete_punches` |
| 8 | Com horas extras | ✅ | direção `surplus` |
| 9 | Com horas faltantes | ✅ | direção `shortfall` |
| 10 | Ocorrências pendentes de justificativa | ✅ | `deviation_type_config.requires_justification` + `justification.status` + `fn_pending_justification` (migration 23). O veredito ganhou produtor em 26/08 — `POST /ocorrencias/{id}/justificativa`, autorizado pela policy `justification_write` (quem enxerga a pessoa), não por `is_admin`. A **fila** ganhou tela em 27/08: `/dashboard/justificativas`, lendo a função pelo Caminho 1 |
| 11 | **Saldo consolidado de horas** | ❌ | Banco de horas não é modelado. Aparece também em 4.4 e 4.8 |
| 12 | Evolução das ocorrências por período | ✅ | `vw_deviation_daily_trend` |
| 13 | Comparação entre unidades | ✅ | `fn_ranking_by_unit` |
| 14 | Comparação entre equipes e gestores | ✅ | `app.manager` + `fn_ranking_by_manager` (migration 27). **Não sai de `manager_employee_id`**: aquela coluna aponta para um colaborador e nada a preenche. O gestor vem de `Funcionario.EstruturaId` → `secullum."Estrutura"`, que cobre 69 dos ~70 ativos |
| 15–18 | Rankings (atraso, extra, faltante, esquecimento) | ✅ | `fn_ranking_by_employee` + filtro de tipo |

### 25/08/2026 — três indicadores entregues, e por que dois não

Os indicadores 1, 4 e 5 vivem no **monitor diário**, não no dashboard, e a
escolha é de significado: "em férias" é fato de um dia, e num recorte de 30 dias
a pergunta não tem resposta única. O dashboard é tela de período; o monitor é a
tela do dia.

Eles não são quatro números novos, são cinco: `escalados + férias + afastados +
folga + sem jornada prevista = ativos`. O quinto não estava no escopo e é o mais
útil dos cinco — **antes desta mudança, quem o motor não materializou
simplesmente não aparecia**, porque o quadro saía de `app.expected_workday`. Seis
pessoas da administração da FastPark estão nesse estado de propósito, e falha de
cobertura do motor tem exatamente a mesma aparência. Contra o seed local, hoje,
os 40 ativos estão todos ali — antes a tela mostrava "0 escalados, 0 fora da
escala", indistinguível de "todo mundo de folga".

Os indicadores 2 e 3 entraram em 25/08 como contagem de **marcação**, não de
presença. `app.batida_marcacao` é lida através de `operax/motor/marcacao.py`, que
é o único lugar onde a ponte para o espelho está escrita — o mesmo caminho que
`regras.py` usa, para que motor e tela nunca discordem sobre quem bateu.

O rótulo é a entrega, tanto quanto o número. "Com marcação até a leitura de
09:15" é conferível: quem bateu às 09:16 está do outro lado da conta, e a hora ao
lado explica por quê. "Presentes" apagaria essa hora e viraria uma afirmação
sobre onde a pessoa estava — que é a **decisão A12**, aberta com o Rodrigo, e o
tipo de frase que um gestor repassa ao colaborador.

⚠️ **Sem leitura, os dois números não aparecem.** Zero e "ninguém leu a origem"
são a mesma imagem com significados opostos; a tela mostra a falta da leitura.
É também o estado do banco de desenvolvimento, que tem `secullum` com zero
tabelas — nenhuma migration deste repositório cria o espelho.

**Filtros exigidos:** período ✅ · empresa ✅ · unidade ✅ · departamento ✅ ·
gestor ✅ · colaborador ⚠️ · tipo de ocorrência ⚠️

Departamento e gestor entraram nos quatro RPCs na migration 22, como parâmetros
opcionais no fim da lista — chamada antiga continua com o mesmo significado. O
filtro passa por `app.employee`, nunca por `app.department.company_id`: derivar
empresa do departamento é a regra 5, e ~26% dos vínculos da FastPark divergem.

```
fn_kpi_period(p_de, p_ate, p_company_id, p_unit_id)
fn_ranking_by_unit(p_de, p_ate, p_company_id, p_limite)
fn_ranking_by_employee(p_de, p_ate, p_company_id, p_unit_id, p_limite)
fn_recurrence(p_de, p_ate, p_min_dias, p_unit_id)
```

---

## 4.4 Consulta individual do colaborador

| Item | Status | Observação |
|---|---|---|
| Dados cadastrais, unidade, departamento, gestor | ✅ | `vw_employee` |
| Jornada contratada | ⚠️ | `expected_workday` é por data; falta o resumo do contrato |
| **Histórico de marcações** | ✅ | Coluna "Marcações" no dia a dia do período — endpoint no FastAPI (Caminho 2), como a lacuna previa. A policy autoriza a pessoa primeiro; só então a ponte para o espelho é atravessada, e um 404 nunca chega nela |
| Histórico de atraso, falta, extra, faltante | ✅ | `vw_deviation_event` |
| Justificativas apresentadas | ✅ | `app.justification` |
| **Saldo de horas** | ❌ | Mesma lacuna do 4.3 #11 |
| Indicadores consolidados por período livre | ✅ | RPCs aceitam intervalo |

---

## 4.5 Monitoramento diário — 🔒 revisão importante

Continuava marcado como bloqueado por "a API expõe o dia corrente?". O
`pg_stat_statements` mostrou que **`secullum."Batida"` tem `Data` e
`batida_marcacao` tem `hora`** — o dado existe com granularidade suficiente.

**Resolvido.** A cadência é **15 minutos para batidas** e 30 para cadastro
(decisão de 24/08 — `docs/DECISAO-CADENCIA-SYNC.md`). A tela é viável sem mudança
de API.

O que entra junto: `public.fn_data_freshness()` (migration 12) e a exibição
permanente da idade do dado. Sem isso a tela mente por omissão — mostra um
retrato de até 15 min atrás como se fosse o agora.

Resta uma pendência real, e ela **reabriu** com a cadência escrita: são **~96
execuções/dia por tenant só para Batida**. Cabem no rate limit da API? É a única
coisa que ainda pode derrubar a cadência.

⚠️ **A "passada diária de backfill de 7 dias" saiu desta conta em 27/08.** Ela é
contrato do runner **deste** repositório; produção roda o `kastropark-jobs` na
Vercel desde 25/08, e toda passada dele carimba janela deslizante fixa de **2
dias**, sem escopo de backfill — medido no log. A carga real hoje é ~96 + ~48
chamadas/dia. Ver `docs/PLANO-RECONCILIACAO-NUVEM.md`.

---

## 4.6 e 4.7 Alertas

Onze tipos de alerta. Dez cobertos pelo catálogo `app.deviation_type` + regras.

| Item | Status | Observação |
|---|---|---|
| **Hora extra sem autorização registrada** | ❌ | Não existe entidade de *autorização de hora extra*. O Secullum tem `ControleHorasExtrasAutorizadas` e `QuantidadeExtrasAutorizadas` em `HorariosOpcoes` — dá para espelhar, mas não está modelado |
| Marcação fora do perímetro | ⚠️ | Tipo `outside_perimeter` existe; a origem do dado de perímetro não |
| Demais tipos | ✅ | |
| Distribuição por unidade e responsável (4.7) | ✅ | `unit_responsible` + `alert_rule_target` |
| Conteúdo do alerta (9 campos) | ✅ | Todos disponíveis no join de `deviation_event` |

---

## 4.8 Assistente de IA — 3 das 9 perguntas-exemplo não têm métrica

O catálogo tem **11** métricas: `deviations_total`, `deviations_minutes`,
`ranking_by_unit`, `ranking_by_employee`, `daily_trend`, `recurrence`,
`documents_expiring`, `payroll_summary`, `data_freshness` — este documento vinha
omitindo o nono — e, desde **28/08/2026**, `ranking_by_manager` e
`pending_justification`.

✅ **As duas leituras que o banco tinha e o assistente não alcançava entraram**
pela migration 29. `fn_ranking_by_manager` (27) e `fn_pending_justification` (23)
já eram `security invoker` e já tinham `execute` para `authenticated` — faltava a
linha em `app.metric`, e nada de novo foi exposto para criá-la. Duas decisões
ficaram registradas na migration: `manager` é dimensão de **saída** no ranking,
como `unit` em `ranking_by_unit`; e `pending_justification` **não** declara
gestor, porque o `p_manager_id` da função filtra `manager_employee_id`, a coluna
que nada preenche — um filtro que devolve zero em silêncio responderia "nenhuma
pendência" sobre uma fila cheia.

| Pergunta do escopo | Métrica | Status |
|---|---|---|
| Quem teve mais atrasos nos últimos 3 meses | `ranking_by_employee` | ✅ |
| Qual unidade tem mais horas extras | `ranking_by_unit` | ✅ |
| Marcações incompletas hoje | `deviations_total` | ✅ |
| **Quem tem o pior saldo de horas** | — | ❌ saldo não modelado |
| Hora extra registrada no mês | `deviations_minutes` | ✅ |
| Evolução das faltas em 6 meses | `daily_trend` | ✅ |
| Quem repete o mesmo tipo de ocorrência | `recurrence` | ✅ |
| **Unidades com aumento de custo no período** | — | ❌ falta métrica de comparação entre períodos |
| **Custo estimado das horas extras do mês** | — | ❌ exige cruzar minutos de desvio com valor-hora |

Como o assistente recusa o que está fora do catálogo — por desenho —, essas três
perguntas hoje recebem "não tenho esse dado". Está correto do ponto de vista de
segurança e errado do ponto de vista de escopo: são exemplos que a proposta usa
para vender.

---

## 4.9 Relatórios — ❌ e em conflito com o que escrevi antes

O escopo lista 11 relatórios e diz que devem ser **visualizados e exportados**.

- Não existe catálogo de relatórios nem definição dos 11 tipos.
- `app.report_cycle` cobre só o ciclo consolidado enviado por WhatsApp/e-mail.
- ~~**Conflito** com o PRD~~ — **não existe mais, e talvez nunca tenha existido
  nesta versão do PRD.** Conferido em 27/08: o "Não entra" do `PRD-OPERAX.md`
  não menciona exportação. A auditoria de 24/08 já havia registrado isso (A18).
  O que continua aberto é o **formato** — Excel, PDF ou os dois —, que muda o
  esforço do sprint e é decisão do dono.

---

## 5. Domínio via Excel — a funcionalidade não existe em nenhum sprint

O modelo suporta (`app.file_import` com `layout_version`, `rows_total`,
`rows_ok`, `rows_error`, `report jsonb`), mas falta tudo em volta:

| O que falta | Onde entra |
|---|---|
| Template padronizado publicado | Entregável de implantação (§6 do escopo obriga) |
| Tela de upload com preview | Frontend, sprint novo |
| Parser + validação de campos obrigatórios | Backend `operax/imports/` |
| Relatório de erro por linha, devolvido ao usuário | Backend + frontend |
| Detecção de duplicidade e reimportação | Backend |
| **Mapa de código de evento → categoria** | Sem isto não dá para separar o que é hora extra, férias ou rescisão dentro de `payroll_entry.code` |

O último é o mesmo problema do mapeamento de unidades: o plano de contas de
eventos da folha é do cliente, e transformar `code` em categoria de produto
exige curadoria validada. **Sem isso, 8 dos 16 indicadores de 5.3 não saem.**

---

## 5.3 e 5.4 Dashboard de folha e alertas financeiros

`vw_payroll_summary` entrega proventos, descontos, encargos e headcount por
competência/empresa/unidade. Dos 16 indicadores exigidos:

✅ valor total, evolução mensal, custo por empresa, custo por unidade, custo por
departamento, custo médio por colaborador, custo com encargos, admissões e
desligamentos (via `workforce_movement`).

❌ custo de horas extras · custo com férias · custo com desligamentos ·
projeção de 13º · comparação entre períodos · variação percentual · desvio
contra média histórica — **todos dependem do mapa de código de evento acima**.

**5.4:** `app.financial_threshold` cobre os limiares. Falta um: *"divergência
entre os dados de ponto e os dados financeiros"* — exige reconciliar minutos de
desvio contra horas extras pagas. Não modelado. ❌

---

## 7. Base integrada de pessoas — 6 entidades faltando

Verificado: nenhuma tabela em `app` para disciplinar, treinamento, benefício,
equipamento, feedback ou anotação.

✅ cadastro, cargo, unidade, departamento, gestor, tipo de contratação, admissão,
histórico de remuneração, histórico de função, documentos, vencimentos, exames,
ASO, férias, afastamentos.

❌ feedbacks · **advertências e ocorrências** · treinamentos · benefícios ·
equipamentos entregues · anotações administrativas.

A de advertências é uma **inconsistência do meu próprio modelo**: declarei
`disciplinary` como um dos quatro domínios sensíveis em `app.sensitive_domain`,
com permissão configurada por papel — e não criei nenhuma tabela que use esse
domínio. O eixo de autorização existe protegendo o vazio.

---

## Seções cobertas sem ressalva

| Seção | Status |
|---|---|
| 8. Documentos e vencimentos | ✅ `document`, `document_type`, `vw_document_expiry` |
| 9. Valores e descontos | ✅ `financial_agreement` + `agreement_installment`, com autorização documentada obrigatória |
| 10. Controle de acesso | ✅ nove perfis mapeados em o enum `app.user_role` |
| 11. Multiempresa e multiunidade | ✅ e a curadoria do mapa tem tela desde 25/08 — `/dashboard/administracao/mapeamento` |
| 12. Exibição em TV | ✅ no S5, só agregado |
| 13. Auditoria | ✅ `audit_log`, `sync_run`, `alert_sent`, `ai_query` |
| 14. Segurança | ✅ verificado por 34 asserções na suíte |

---

## As 27 lacunas, agrupadas por natureza

**Bloqueiam entrega do escopo contratado (9)**

1. Saldo de horas — aparece em três seções diferentes. **Decidido em 28/08: o
   OperaX calcula**, não espelha (ver abaixo)
2. ~~KPIs de headcount~~ — **os 5 entregues em 25/08**; os dois de marcação com o rótulo da leitura, e não como presença (A12)
3. ~~Filtro por gestor e por departamento~~ — **entregue em 25/08** (migration 22); ~~agregação por gestor~~ — **entregue em 26/08** (migration 27). ⚠️ O `p_manager_id` da 22 filtra por `manager_employee_id`, que continua sem fonte: quem quiser filtrar por gestor hoje tem de usar a dimensão nova
4. ~~Histórico de marcações na tela individual~~ — **entregue em 25/08**
5. Catálogo dos 11 relatórios + exportação — **formato decidido em 28/08: Excel
   *e* PDF**
6. Importação do Excel do Domínio, ponta a ponta
7. Mapa de código de evento de folha → categoria — **a tabela existe desde
   28/08** (`app.payroll_event_map`, migration 30); falta a curadoria, que é
   atividade de implantação com a contabilidade
8. ~~Ocorrências pendentes de justificativa~~ — **entregue em 25/08** (migration 23); ~~sem tela que aceite ou rejeite~~ — **entregue em 26/08**: `POST /ocorrencias/{id}/justificativa` e o veredito no drawer da ocorrência. "Aceita" e "escrita" deixaram de ser a mesma coisa. ~~Falta a *fila*~~ — **entregue em 27/08**: `/dashboard/justificativas`. Item fechado
9. Tabela de ocorrência disciplinar

**Volume, sem risco técnico (5)**

10–14. Feedbacks, treinamentos, benefícios, equipamentos, anotações administrativas

**Dependem de decisão ou dado externo (6)**

15. Autorização de hora extra
16. Origem do dado de perímetro
17. ~~Frequência de sync~~ — **resolvido: 15 min (batidas) / 30 (cadastro)**. O rate limit reabriu com o volume real
18. Três métricas do assistente
19. Reconciliação ponto × folha
20. Oito indicadores de folha (derivam do item 7)

**Ajuste de documento (7 — dois deles já feitos)**

21. ~~PRD: remover "exportação fora do MVP"~~ — **já aplicado**. O "Não entra" do
    PRD atual não menciona exportação. O que segue aberto é o **formato**
    (Excel, PDF ou os dois), que é decisão do dono, não ajuste de texto
22. ~~PRD: risco do Domínio deixa de ser alto~~ — **já aplicado**. A tabela de
    riscos do PRD não tem risco de Domínio; tem "Plano de contas de eventos não
    mapeado", que é outro item e continua aberto (item 7)
23. SPEC: Domínio vira file-first, não fallback
24. SPEC: rever a pendência do monitor diário
25. SPRINTS: Fase 3 não depende mais de acesso externo
26. SPRINTS: sprint novo de importação
27. ~~Métricas do assistente no catálogo `app.metric`~~ — **entregue em 28/08**
    (migration 29): `ranking_by_manager` e `pending_justification`, as duas
    leituras que existiam no banco e o assistente não alcançava. Ver §4.8

---

## As três decisões que faltavam — tomadas em 28/08/2026

**Saldo de horas: o OperaX calcula.** Decisão do dono, contra a recomendação
registrada aqui, que era espelhar `NBanco` do Secullum. Fica escrito o que a
recomendação dizia, porque é o risco que o trabalho passa a carregar: o registro
oficial da jornada é o sistema de ponto, e um saldo calculado aqui **vai
divergir** do dele em algum momento — arredondamento, regra de compensação,
feriado municipal. Quando divergir, quem vale é o Secullum, e a diferença aparece
numa tela que um gestor mostra para uma pessoa. Duas consequências práticas para
quem for implementar:

- a regra de compensação precisa ser **escrita e versionada** antes do primeiro
  número (banco de horas tem prazo, teto e forma de quitação — nada disso é
  derivável das batidas);
- o vocabulário da regra do CLAUDE.md passa a valer em dobro: o que a tela mostra
  é **indício** e **saldo apurado pelo OperaX**, nunca "banco de horas oficial".

**Exportação: Excel e PDF, os dois.** O sprint de relatórios cresce — são dois
geradores e dois layouts, e o PDF é o que exige decisão de leiaute (cabeçalho,
marca do tenant, paginação). O catálogo dos 11 relatórios continua sendo o
pré-requisito de ambos.

**Mapa de código de evento: a tabela foi criada.** `app.payroll_event_map`
(migration 30), com o mesmo desenho de `app.unit_secullum_map` — chave
`(tenant_id, code)`, nove categorias, `validated_by`/`validated_at`, RLS de
admin. Isso destrava o caminho, **não os indicadores**: eles precisam da
curadoria com a contabilidade, que continua sendo atividade de implantação e
precisa estar dimensionada como tal. Linha sem `validated_at` é provisória, e a
tela tem de mostrar isso como faixa própria — somar provisório com confirmado faz
a curadoria parecer terminada com metade do trabalho por fazer.
