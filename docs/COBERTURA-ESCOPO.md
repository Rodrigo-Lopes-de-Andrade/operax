# OperaX — cobertura do escopo da proposta

Confronto item a item entre o **escopo contratado** e o que existe hoje em
migrations, views, RPCs e nos documentos de produto. Verificado contra o schema
real gerado pela suíte, não de memória.

Legenda: ✅ coberto · ⚠️ parcial · ❌ falta · 🔒 bloqueado por dependência externa

**Resultado: 26 lacunas** (era 27; a cadência de sync fechou uma). Nove delas mudam o escopo de trabalho de forma
relevante; o resto é volume.

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

## 4.3 Dashboard de gestão de ponto

O escopo lista 18 indicadores como mínimo. Cobertos: 14. Faltam 4.

| # | Indicador | Status | Onde está / o que falta |
|---|---|---|---|
| 1 | Total de colaboradores ativos | ✅ | `active` no monitor diário — e é ele que revela `unrostered`, ativo sem jornada prevista |
| 2 | Colaboradores presentes no dia | ❌ 🔒 | A marcação **existe** em `app.batida_marcacao` e `app.employee.secullum_employee_id` liga a ela. O bloqueio é outro: é tabela de ingestão **congelada** pela 11b, nenhuma migration daqui a cria, o banco de dev não a tem, e a policy dela é só `util.has_tenant` |
| 3 | Colaboradores ausentes | ❌ 🔒 | Idem. O mais próximo honesto que existe é o indício `no_punches`, que **não** é a mesma afirmação e por isso não recebeu o nome |
| 4 | Colaboradores em férias | ✅ | `on_vacation` no monitor — de `app.expected_workday.day_type`, que é onde férias é fato do dia (ver `cadastro.py`), não de `app.employee.status` |
| 5 | Colaboradores afastados | ✅ | `on_leave`, mesma fonte |
| 6 | Colaboradores com atraso | ✅ | `late_entry` |
| 7 | Marcação incompleta | ✅ | `incomplete_punches` |
| 8 | Com horas extras | ✅ | direção `surplus` |
| 9 | Com horas faltantes | ✅ | direção `shortfall` |
| 10 | Ocorrências pendentes de justificativa | ⚠️ | `app.justification` existe, mas nada marca um desvio como *exigindo* justificativa nem como *pendente* |
| 11 | **Saldo consolidado de horas** | ❌ | Banco de horas não é modelado. Aparece também em 4.4 e 4.8 |
| 12 | Evolução das ocorrências por período | ✅ | `vw_deviation_daily_trend` |
| 13 | Comparação entre unidades | ✅ | `fn_ranking_by_unit` |
| 14 | **Comparação entre equipes e gestores** | ❌ | `employee.manager_employee_id` existe; nenhuma view ou RPC agrega por gestor |
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

Os indicadores 2 e 3 continuam ❌ e **não** foram aproximados. "Escalado e sem
indício" já existe na tela com a ressalva escrita ("não é confirmação de
presença"); rebatizá-lo de "presentes" transformaria a ressalva em mentira.

**Filtros exigidos:** período ✅ · empresa ✅ · unidade ✅ · **departamento ❌** ·
**gestor ❌** · colaborador ⚠️ · tipo de ocorrência ⚠️

Verificado: nenhum dos quatro RPCs aceita `department_id` nem `manager_id`.

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
| **Histórico de marcações** | ❌ | **Lacuna arquitetural**: as marcações vivem em `secullum."Batida"` e `batida_marcacao`, e a regra é que o painel nunca lê `secullum`. Precisa de uma view curada em `app` ou de endpoint no FastAPI |
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
execuções/dia por tenant só para Batida**, mais a passada diária de backfill de 7
dias. Cabem no rate limit da API? É a única coisa que ainda pode derrubar a
cadência.

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

O catálogo tem 8 métricas: `deviations_total`, `deviations_minutes`,
`ranking_by_unit`, `ranking_by_employee`, `daily_trend`, `recurrence`,
`documents_expiring`, `payroll_summary`.

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
- **Conflito:** o `PRD-OPERAX.md` lista "Exportação Excel/PDF" como fora do MVP —
  herdado do resumo técnico original de vocês. O escopo contratado exige. O PRD
  está errado e precisa mudar, não o escopo.

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
| 11. Multiempresa e multiunidade | ✅ com a ressalva do mapeamento curado de unidade |
| 12. Exibição em TV | ✅ no S5, só agregado |
| 13. Auditoria | ✅ `audit_log`, `sync_run`, `alert_sent`, `ai_query` |
| 14. Segurança | ✅ verificado por 34 asserções na suíte |

---

## As 27 lacunas, agrupadas por natureza

**Bloqueiam entrega do escopo contratado (9)**

1. Saldo de horas — aparece em três seções diferentes
2. ~~KPIs de headcount~~ — **3 dos 5 entregues em 25/08**. Restam presentes e ausentes, que dependem da tabela de ingestão congelada
3. Filtro e agregação por gestor e por departamento
4. Histórico de marcações na tela individual
5. Catálogo dos 11 relatórios + exportação
6. Importação do Excel do Domínio, ponta a ponta
7. Mapa de código de evento de folha → categoria
8. Ocorrências pendentes de justificativa
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

**Ajuste de documento (7)**

21. PRD: remover "exportação fora do MVP"
22. PRD: risco do Domínio deixa de ser alto
23. SPEC: Domínio vira file-first, não fallback
24. SPEC: rever a pendência do monitor diário
25. SPRINTS: Fase 3 não depende mais de acesso externo
26. SPRINTS: sprint novo de importação
27. Métricas do assistente no catálogo `app.metric`

---

## O que precisa de decisão antes de eu mexer

**Saldo de horas.** É o item que mais aparece no escopo e o que tem mais risco
de virar cálculo próprio divergente do oficial. O Secullum tem `NBanco` em
`Batida` e um bloco inteiro de compensação em `HorariosOpcoes`. A pergunta é se
o saldo vem espelhado de lá ou se o OperaX calcula. **Espelhar é a única resposta
que não recria a exposição jurídica que o resto do desenho evita.**

**Mapa de código de evento de folha.** Sem ele metade do dashboard financeiro não
existe. É trabalho de curadoria com a contabilidade, igual ao mapa de unidades —
e precisa estar dimensionado como atividade de implantação, não absorvido.

**Exportação.** O escopo exige, meu PRD excluía. Confirmar formato (Excel, PDF ou
os dois) muda o esforço do sprint de relatórios.
