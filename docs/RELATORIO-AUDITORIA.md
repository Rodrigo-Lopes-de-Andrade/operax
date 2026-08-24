<!-- verificar-docs: inexistentes-de-proposito app.work_schedule_day public.rls_auto_enable -->
# Relatório de auditoria documental — OperaX

**Data:** 24/08/2026
**Auditor:** independente; sem participação prévia no projeto.

## Método

Foram lidos por inteiro os 12 documentos de `/home/claude/auditoria/docs/` (5.960 linhas):
`AVALIACAO-DESIGN.md`, `AVALIACAO-DESIGN-R2.md`, `AVALIACAO-DESIGN-R3.md`, `AVALIACAO-DESIGN-R4.md`,
`COBERTURA-ESCOPO.md`, `DECISAO-WHATSAPP.md`, `DICIONARIO-DE-DADOS.md`, `PLANO-BANCO-OPERAX.md`,
`PLANO-RECONCILIACAO-NUVEM.md`, `PRD-OPERAX.md`, `SPEC-TECNICA.md`, `SPRINTS.md`.

**O que não pôde ser verificado:** código, banco (local, staging ou produção), repositório, scripts, migrations,
o pacote de design (`OperaX.zip` e derivados), o `CLAUDE.md` e a **proposta comercial / escopo contratado** — todos
citados pelos documentos e ausentes do conjunto (lista completa na seção "Artefatos ausentes"). A auditoria é
estritamente documental: consistência interna, contradição entre documentos, desatualização, completude e
rastreabilidade de decisão. Toda afirmação abaixo traz citação literal curta; números que batem também foram
conferidos e constam da tabela.

Convenção de referência: SPEC = `SPEC-TECNICA.md`; PLANO-BANCO = `PLANO-BANCO-OPERAX.md`;
RECONC = `PLANO-RECONCILIACAO-NUVEM.md`; COBERTURA = `COBERTURA-ESCOPO.md`; DICIONARIO = `DICIONARIO-DE-DADOS.md`;
R1–R4 = `AVALIACAO-DESIGN*.md`; WHATS = `DECISAO-WHATSAPP.md`.

---

## Tabela-resumo dos números-chave (dimensão 1)

| # | Número-chave | O que cada documento afirma | Situação |
|---|---|---|---|
| 1 | Total de migrations do repositório | SPEC §8: "aplica as 14 migrations"; SPRINTS S2: "14 migrations aplicam limpas"; PLANO-BANCO: "As 14 migrations do OperaX" **e**, no mesmo doc, tabela de ordem com 00–11 (12) e "antes das 12 migrations"; RECONC: "aplicar as 16 migrations" / "verde com as 17 migrations" (com a 11b); R2/R3/R4: "15 migrations" | ✖ divergente (A10) |
| 2 | Migration que cria `message_template`/`fn_whatsapp_readiness` | WHATS §3: "O que a migration 15 acrescenta"; RECONC: "`fn_whatsapp_readiness` (migration 14)", "`message_template` nasce na migration 14", arquivo `…_14_whatsapp_provedores.sql`; a 15 é `…_15_rebrand_fastpark.sql` | ✖ (A11) |
| 3 | Cadência de sync de Batida | PRD F6: "Cadência de 30 minutos"; SPEC §2: "30 min (decisão do cliente)"; COBERTURA 4.5: "A cadência é 30 minutos"; RECONC §1b: "sync-batidas-cron `*/15`… Batidas roda a cada 15 minutos, não 30" | ✖ (A4) |
| 4 | Cadência de sync de cadastro | SPEC §2: "Empresa, Departamento, Horário — diária"; RECONC §1b: "sync-cadastro-cron `*/30 * * * *`" | ✖ (A4) |
| 5 | Execuções de sync/detecção por dia | PRD risco: "48 execuções/dia"; SPEC 3.5b: "48×/dia"; COBERTURA: "48 execuções/dia por tenant"; DICIONARIO (`detection_run.scope`): "48x/day"; com `*/15` real seriam ~96 | ✖ (A4) |
| 6 | Janela de releitura retroativa de batidas | SPEC §2 (tabela): "7 dias retroativos, 1×/dia"; SPEC 3.5b: "Reprocessamento retroativo… 7 dias"; SPEC §2 (pendências): "janela deslizante fixa de três dias (hoje − 2 .. hoje), que nunca reprocessa o passado"; RECONC 4b: "`BATIDAS_WINDOW_DAYS = 2`… janela fixa de 48h" | ✖ (A5, A29) |
| 7 | Limiar de frescor do dado | SPEC 5b e DICIONARIO (`fn_data_freshness`): "45 min — 1,5× a cadência" (premissa de 30 min) | ✔ entre si; premissa afetada por #3 |
| 8 | Asserções funcionais de isolamento | SPEC §8, PLANO-BANCO DB-12, SPRINTS S2: 23 (dois tenants, quatro papéis) | ✔ |
| 9 | Verificações estruturais da suíte | SPEC §8 / PLANO-BANCO / SPRINTS: 11; R1 §5: "agora com 13 verificações estruturais" | ✖ (A26) |
| 10 | Total de asserções citado | COBERTURA §14: "34 asserções" (=23+11); não reflete as 2 estruturais novas (R1) nem as "Onze asserções novas em `scripts/97_teste_regras_alerta.sql`" (WHATS) | ✖ (A26) |
| 11 | Métricas do assistente | COBERTURA 4.8: "O catálogo tem 8 métricas"; R1: "O banco tem **nove**"; R1/R2/R3: 9 ativas + 4 previstas | ✖ (A16) |
| 12 | Telas | R1: "Sete das nove telas"; R2/R3: 9 de 9; R4 (mobile): "Pedi três telas. Vieram sete" | ✔ coerente como evolução |
| 13 | Identificadores de banco no handoff | R2: 27 citados, 22 existem, 5 inventados; R3/R4: 37/37 | ✔ coerente como evolução |
| 14 | Componentes / tabelas cruas / contraste | 78→108→126 instâncias; `<table>` cruas 5→0→0; pares reprovando 5→0 (R1–R3) | ✔ |
| 15 | Falso positivo do motor | PRD: "≤ 5% ao sair da sombra"; SPEC 3.5: "<= 5% por duas execuções seguidas"; SPRINTS G4: "≤5% em duas execuções" | ✔ |
| 16 | Confiança da jornada | SPEC/PLANO-BANCO/SPRINTS/DICIONARIO: `<80` não gera alerta; ">20%… abaixo de 80" → cadastro manual | ✔ |
| 17 | Divergência Empresa×Departamento | PRD: "~26%"; PLANO-BANCO: "26%"/"~26%"; SPRINTS: "~26%"; R1: "~26%" | ✔ |
| 18 | Papéis e domínios sensíveis | PRD F10: "Nove papéis… Quatro domínios"; COBERTURA §10: "nove perfis"; DICIONARIO enumera 9 papéis e 4 domínios (nomes divergem — A20) | ✔ nas contagens |
| 19 | Carga do dashboard | PRD/SPEC/SPRINTS: < 3 s; SPEC §6 medições: 760 ms / 612 ms / 552 ms | ✔ |
| 20 | Backoff da fila | SPEC §5: "1 min, 5 min, 15 min, 1 h, 6 h. Após 5 tentativas, descartado" | ✔ (fonte única) |
| 21 | Lacunas de escopo | COBERTURA cabeçalho: "**26 lacunas** (era 27…)"; título de seção: "As 27 lacunas" | ✖ interno (A24) |
| 22 | Indicadores 4.3 | COBERTURA: 18 exigidos, "Cobertos: 11. Faltam 7" (10 ✅ + 1 ⚠️ + 7 ❌) | ✔ interno (⚠️ contado como coberto) |
| 23 | Indicadores 5.3 | COBERTURA: "Dos 16 indicadores exigidos" com lista de 8 ✅ e 7 ❌ (soma 15); "8 dos 16… não saem" vs 7 ❌; SPRINTS repete "8 dos 16" | ✖ interno (A25) |
| 24 | Inventário `app` | RECONC: "49 objetos, 45 com par", "Só em produção: 4 (batida_marcacao, cursor_sincronizacao, empresa_evento_status, funcionario_evento_status)", "Só neste repositório: 1"; DICIONARIO lista 49 tabelas + 1 matview, **incluindo** 3 das "só em produção" e `work_schedule_day` (em nenhum inventário), **sem** `cursor_sincronizacao` | ✖ (A8) |
| 25 | Tabelas do schema `secullum` | RECONC: "vinte tabelas PascalCase" / "20 tabelas de `secullum`"; DICIONARIO lista 13 | ✖ (A8) |
| 26 | Identificadores pt→en pareados | RECONC §1b: "348 identificadores mapeados 1:1"; RECONC Fase 2: "353 identificadores pareados" | ✖ interno (A27) |
| 27 | Migrations na nuvem | RECONC: "23 migrations aplicadas. Onze anteriores… e doze deste repositório" (11+12=23) | ✔ interno |
| 28 | Datas de decisão | 22/08/2026 (SPEC nota; SPRINTS S1; RECONC decisões/Fases 0–1); 24/08/2026 (RECONC Fase 2) | ✔ |
| 29 | Custo WhatsApp | WHATS: US$ 0,0068/msg; ~2.000/mês → "≈ US$ 14"; ~6.000 → "≈ US$ 41" (aritmética confere) | ✔ |
| 30 | Dimensões do protótipo | WHATS e R1: "6 unidades, ~182 colaboradores"; R1: "43 ocorrências no dia" | ✔ |
| 31 | Views públicas | DICIONARIO: 8 views em `public`; RECONC: "As 8 views de public"; "9 views" da introspecção fecha com 8 + a matview | ✔ sob interpretação |
| 32 | Tipos de desvio / de alerta | PRD F3: 12 tipos de desvio; PRD F7 e COBERTURA 4.6: "Onze tipos de alerta. Dez cobertos" | ✔ |
| 33 | Nome do tenant/cliente | PRD/PLANO-BANCO/SPRINTS/RECONC: "Kastro Park" / tenant "kastro-park"; DICIONARIO: default `'<tenant fastpark>'::uuid` em ~20 tabelas; RECONC lista `…_15_rebrand_fastpark.sql` | ✖ (A15) |
| 34 | Prazo | SPRINTS: "total ~33–50 dias úteis" vs "proposta comercial fala em 30 a 45 dias corridos" — tensão declarada pelo próprio documento | ⚠ declarado |
| 35 | Postgres | PLANO-BANCO: "testadas em Postgres 16 local"; RECONC: produção "PostgreSQL 17.6" | ✖ (A28) |

---

## Achados

### Severidade ALTA

**A1 — PLANO-BANCO instrui a mexer num worker Python que uma decisão registrada declarou superado.**
Arquivos: `PLANO-BANCO-OPERAX.md` × `SPEC-TECNICA.md`, `SPRINTS.md`.
PLANO-BANCO se apresenta como "a instrução de execução para o Claude Code" e manda, no DB-3: "**Quebra o worker — aplicar junto com o código no mesmo PR**", com snippet de `backend/operax/core/db.py`. A SPEC registra: "**Onde isto roda, desde 22/08/2026:** em Edge Functions do Supabase (`sync-cadastro`, `sync-batidas`…), não no worker Python descrito acima". SPRINTS S1 confirma: "Edge Functions… — decisão de 22/08/2026, fora do backend Python".
Por que importa: um agente que siga o documento que se declara "instrução de execução" ajustará um componente que não é o que roda.

**A2 — PLANO-BANCO coloca `service_role` na Vercel; SPEC e SPRINTS proíbem exatamente isso.**
Arquivos: `PLANO-BANCO-OPERAX.md` × `SPEC-TECNICA.md`, `SPRINTS.md`.
PLANO-BANCO (DB-10/11): "Quem serve o dashboard a partir dela é a rota server-side no Vercel, com `service_role`". SPEC §1: "**O `service_role` mora num lugar só: o backend FastAPI.** Nunca no Next.js, nunca numa route handler da Vercel"; SPEC §6: "Matview de resumo | FastAPI apenas". SPRINTS (DoD 4): "`service_role` só existe no backend FastAPI".
Por que importa: é contradição de arquitetura de segurança sobre a chave que ignora RLS; seguir o PLANO-BANCO viola a regra que a SPEC chama de inegociável.

**A3 — SPEC e PLANO-BANCO ainda apontam Evolution API; a decisão registrada é outra (três provedores, `meta_cloud` padrão).**
Arquivos: `SPEC-TECNICA.md`, `PLANO-BANCO-OPERAX.md` × `DECISAO-WHATSAPP.md`, `DICIONARIO-DE-DADOS.md`.
SPEC §5: "Evolution API é a implementação inicial; a oficial entra sem tocar no motor". PLANO-BANCO (risco 4): "**Evolution API.** Solução não oficial…". WHATS: "Decisão do cliente: **API oficial da Meta, Z-API e uazapi**, os três suportados… `meta_cloud` é o **padrão** no schema"; o CHECK de `app.integration.provider` no DICIONARIO lista `meta_cloud/z_api/uazapi/smtp/resend/…` — sem Evolution.
Por que importa: contradiz decisão registrada; o contrato mudou de texto livre para "template-first" ("Nenhum recebe string pronta" — WHATS §6), e a interface da SPEC (`enviarWhatsApp(destino, payload)`) descreve o desenho anterior.

**A4 — A cadência real de produção é 15 min; quatro documentos afirmam 30 min e derivam contas dela.**
Arquivos: `PLANO-RECONCILIACAO-NUVEM.md` × `PRD-OPERAX.md`, `SPEC-TECNICA.md`, `COBERTURA-ESCOPO.md`, `DICIONARIO-DE-DADOS.md`.
RECONC §1b: "**Batidas roda a cada 15 minutos, não 30** — a documentação deste repositório fala em 30 min para as duas". Contra: PRD F6 "Cadência de 30 minutos"; SPEC §2 "**30 min** (decisão do cliente)"; COBERTURA 4.5 "A cadência é **30 minutos**, por decisão do cliente". Derivados da premissa de 30: "48 execuções/dia" (PRD risco; COBERTURA; SPEC 3.5b "48×/dia"; DICIONARIO "48x/day") — com `*/15` seriam ~96 — e o limiar de frescor "45 min — 1,5× a cadência" (SPEC 5b; DICIONARIO). O cadastro também diverge: SPEC diz "diária", o cron roda `*/30`.
Por que importa: a pendência aberta de rate limit ("48 execuções/dia… cabem no rate limit?", COBERTURA) está dimensionada com metade do volume real, e nenhum documento registra quem decidiu 15 min.

**A5 — O contrato de releitura retroativa (7 dias) não existe na sincronização real (2–3 dias, "nunca reprocessa o passado") — e a própria SPEC afirma os dois.**
Arquivos: `SPEC-TECNICA.md` (autocontradição) × `PLANO-RECONCILIACAO-NUVEM.md`.
SPEC §2 (tabela): "Batida … 7 dias retroativos, 1×/dia", justificado por "correção feita ontem em batida de anteontem nunca chega [sem ela]"; SPEC 3.5b exige "Reprocessamento retroativo | 1×/dia | 7 dias". A mesma SPEC §2 (pendências): "janela deslizante fixa de **três dias** (hoje − 2 .. hoje), **que nunca reprocessa o passado**". RECONC 4b: "`BATIDAS_WINDOW_DAYS = 2`… **não** [recupera de queda longa], por nenhum caminho".
Por que importa: a revogação por correção retroativa (SPEC 3.4, PRD F3 "Correção retroativa na origem revoga o desvio") depende de o espelho enxergar correções de até 7 dias; com a janela real, correções além de D-2 nunca chegam — o mecanismo, como documentado, não se sustenta, e nenhum documento resolve o conflito.

**A6 — SQL copiável da SPEC e do PLANO-BANCO usa valores e nomes em português que o schema (em inglês) rejeita ou ignora em silêncio.**
Arquivos: `SPEC-TECNICA.md`, `PLANO-BANCO-OPERAX.md` × `DICIONARIO-DE-DADOS.md`.
SPEC 3.3 e §4: `where status = 'active' and mode = 'producao'`; SPEC §5 (outbox): `where status in ('pendente','falhou')`. O DICIONARIO define os CHECKs: `mode` ∈ ('shadow','production'); `alert_queue.status` ∈ ('pending','sending','sent','failed','discarded'). PLANO-BANCO: "`deteccao_execucao.modo = 'sombra'`" (a tabela é `detection_run`, os valores 'shadow'/'production'), "Preencher `alerta_enviado.custo_centavos`" (é `alert_sent.cost_cents`), "`tolerancia_*_min`" (é `tolerance_*_minutes`).
Por que importa: o consumo da fila com `('pendente','falhou')` retorna **zero linhas sem erro** — a fila represa em silêncio; é exatamente a classe de armadilha ("seis corpos de view filtram por VALOR… devolviam zero linha — sem erro, só tela vazia") que a própria RECONC documentou no ensaio.

**A7 — O exemplo de consumo do DICIONARIO contradiz a assinatura e as colunas do próprio DICIONARIO.**
Arquivo: `DICIONARIO-DE-DADOS.md` (autocontradição).
Seção "Como consumir": `supabase.rpc('fn_kpi_period', { p_de…, p_unidade_id: … })` e `.select('reference_date, direction, eventos, minutos_abs')`. A assinatura no mesmo documento é `fn_kpi_period(p_de, p_ate, p_company_id, p_unit_id)` e a coluna da view é `minutes_abs`.
Por que importa: é o documento-referência ("Gerado por introspecção… Não editar à mão"); um agente que copie o exemplo canônico recebe erro do PostgREST — e o documento que deveria ser a verdade carrega resíduo pt→en.

**A8 — Os inventários de schema divergem, e `app.cursor_sincronizacao` — "o achado que importa" — não existe no DICIONARIO.**
Arquivos: `PLANO-RECONCILIACAO-NUVEM.md` × `DICIONARIO-DE-DADOS.md`.
RECONC: "app.cursor_sincronizacao existe em produção e **em nenhuma migration deste repositório**… Precisa entrar no baseline… ou **a sincronização perde a memória de onde parou**"; inventário: "Só em produção: 4 (batida_marcacao, cursor_sincronizacao, empresa_evento_status, funcionario_evento_status)"; "secullum.* — **vinte** tabelas PascalCase". O DICIONARIO, porém, **lista** `app.batida_marcacao`, `app.empresa_evento_status`, `app.funcionario_evento_status` e ainda `app.work_schedule_day` (ausente de ambos os inventários da RECONC), **não lista** `cursor_sincronizacao`, e traz só **13** tabelas em `secullum`.
Por que importa: nenhum documento registra a absorção parcial que o DICIONARIO evidencia; um agente que confie no dicionário como mapa completo perde a tabela de cursor no baseline/rename — com a consequência que o próprio projeto descreveu.

> **FECHADO em 24/08/2026, commit `11fd5e6`.** A causa era uma só: `make db-test`
> gerava o dicionário a partir de `scripts/_test_stub_supabase.sql`, um espelho
> *simulado* — o próprio `testar_migrations.sh` já chamava aquilo de "um palpite,
> não o schema real" e procurava um `scripts/_baseline.sql` que nunca fora
> escrito. O dicionário não estava errado sobre o banco que descrevia; estava
> descrevendo o banco errado.
>
> `scripts/gerar_baseline_nuvem.py` passou a montar o baseline a partir do
> catálogo de produção, e o dicionário regenerado agora traz **20 tabelas em
> `secullum`** (eram 13) e **`app.cursor_sincronizacao`**. `app.work_schedule_day`
> saiu: ele só existia porque o stub o criava e a migration 03 o varria para
> `app` — produção nunca o teve, e **nenhuma migration o referencia**. A ausência
> dele nos dois inventários da RECONC estava certa; a presença no dicionário é
> que era o resíduo.
>
> O baseline passou a ser versionado, contra a regra `scripts/_*` e com o motivo
> escrito no `.gitignore`: o achado só existiu porque o gate significava coisas
> diferentes em máquinas diferentes.
>
> **Supersede** a instrução do veredito ("Quem for gerar baseline, rename ou seed
> a partir do dicionário precisa antes reconciliar esses inventários") no que diz
> respeito a A8 — os inventários estão reconciliados. As linhas 24 e 25 da
> tabela-resumo descrevem o estado anterior a este commit.

**A9 — Riscos declarados "mais urgentes que o rename" não aparecem em nenhum plano de execução.**
Arquivos: `PLANO-RECONCILIACAO-NUVEM.md` × `SPRINTS.md`, `PLANO-BANCO-OPERAX.md`.
RECONC 4b: "Não existe transação em nenhuma escrita"; "Qualquer queda de `sync-batidas` que passe de 48 h deixa um buraco… que nenhum caminho de código consegue preencher"; "O handler responde **HTTP 200, `{ok: true}`**, com zero batidas gravadas"; "Não há alarme nenhum"; e a diretiva: "Os riscos 3 e 4 valem a pena fechar **antes** do rename". SPRINTS e PLANO-BANCO não contêm nenhuma entrega, gate ou sprint para transação, alarme, janela de batidas ou a própria Fase 3 da reconciliação.
Por que importa: o plano de sprints não reflete os riscos que o documento mais recente declara urgentes; quem executar "pelo plano" deixará os quatro em aberto.

### Severidade MÉDIA

**A10 — Contagem de migrations diverge entre quatro documentos e dentro do PLANO-BANCO.**
Arquivos: `SPEC-TECNICA.md`, `SPRINTS.md`, `PLANO-BANCO-OPERAX.md`, `PLANO-RECONCILIACAO-NUVEM.md`, `AVALIACAO-DESIGN-R3/R4.md`.
SPEC §8: "aplica as 14 migrations"; SPRINTS S2 (aceite): "14 migrations aplicam limpas"; PLANO-BANCO: "As 14 migrations" e, no mesmo doc, ordem de execução com 12 (00–11) e "antes das 12 migrations"; RECONC: "aplicar as 16 migrations" / "verde com as **17** migrations"; R3/R4: "as 15 migrations".
Por que importa: critérios de aceite (S2) e a descrição da suíte apontam para um total que não é o atual; ninguém saberá qual contagem é "verde".

**A11 — WHATS atribui à migration 15 o que a RECONC atribui à 14.**
Arquivos: `DECISAO-WHATSAPP.md` × `PLANO-RECONCILIACAO-NUVEM.md`.
WHATS §3: "**O que a migration 15 acrescenta**" (lista `message_template`, `fn_whatsapp_readiness`…). RECONC: "`fn_whatsapp_readiness` (migration 14)", "`message_template` nasce na migration 14", e a sequência da Fase 3 nomeia `…_14_whatsapp_provedores.sql` e `…_15_rebrand_fastpark.sql`.
Por que importa: em qualquer operação por número de migration (aplicação seletiva, rollback, conferência), os dois documentos apontam alvos diferentes.

**A12 — Três estados afirmados para "marcações no schema `app`".**
Arquivos: `SPEC-TECNICA.md` × `DICIONARIO-DE-DADOS.md` × `PLANO-RECONCILIACAO-NUVEM.md`.
SPEC §6 (monitor): "As marcações não são espelhadas para o schema `app` — ficam no espelho da origem". DICIONARIO lista `app.batida_marcacao` (com policy de leitura por tenant). RECONC: "**Produção espelha marcação dentro de `app`.** Este repositório não" — e avisa que a frase do monitor "deixa de estar [certa] quando a reconciliação fechar… É decisão de produto".
Por que importa: a semântica central do monitor ("sem indício" ≠ presença) depende desse fato, e os três documentos não concordam sobre qual é o fato hoje.

**A13 — A tabela de pendências da SPEC (§10) lista como "travando implementação" itens que a própria SPEC (§2) e a COBERTURA dão por resolvidos.**
Arquivos: `SPEC-TECNICA.md` (autocontradição) × `COBERTURA-ESCOPO.md`.
SPEC §10 mantém abertas: "1 API expõe marcação do dia corrente?", "2 Rate limit e paginação", "3 API devolve valor apurado?", "4 Escopo e renovação do token", "5 Justificativa é escrita via API?". SPEC §2: "Quatro das cinco fecharam em 22/08/2026" (autenticação, paginação — "não há", valor apurado — "Devolve", leitura/escrita — "Leitura, por decisão estrutural"); COBERTURA 4.5 sobre o dia corrente: "**Resolvido.** A cadência é 30 minutos… A tela é viável sem mudança de API".
Por que importa: pendência resolvida num lugar e aberta noutro faz um agente esperar por (ou re-investigar) o que já foi fechado.

**A14 — PLANO-BANCO declara decisões "que já viraram configuração"; PRD e SPEC as mantêm como pendências que travam.**
Arquivos: `PLANO-BANCO-OPERAX.md` × `PRD-OPERAX.md`, `SPEC-TECNICA.md`.
PLANO-BANCO: "Não precisam mais de decisão para o schema avançar; são `UPDATE`: … Periodicidade do relatório… Gestor com acesso ao painel". PRD (pendências): "Decisões do cliente — periodicidade do relatório… e se o gestor terá acesso próprio"; SPEC §10: "8 Periodicidade do relatório | Regras de ciclo" e "10 Gestor terá login?".
Por que importa: são enunciados divergentes da mesma pendência (decisão de produto ainda existe; só o schema deixou de bloquear) — sem essa distinção, um documento parece contradizer o outro.

**A15 — Rebrand "fastpark" existe nos artefatos e em nenhuma decisão registrada.**
Arquivos: `DICIONARIO-DE-DADOS.md`, `PLANO-RECONCILIACAO-NUVEM.md` × `PRD-OPERAX.md`, `PLANO-BANCO-OPERAX.md`, `SPRINTS.md`.
DICIONARIO traz default `'<tenant fastpark>'::uuid` em ~20 tabelas; RECONC lista `20260822160000_15_rebrand_fastpark.sql`. Todos os demais documentos dizem "Kastro Park" e "Tenant `kastro-park` criado" (SPRINTS S0; PLANO-BANCO DB-2); RECONC chama produção de "Kastro Park Ponto".
Por que importa: uma migration de *rebrand* sem decisão registrada quebra a rastreabilidade — não há como saber o que foi renomeado, quando e por ordem de quem.

**A16 — Catálogo do assistente: 8 métricas na COBERTURA, 9 nas avaliações de design.**
Arquivos: `COBERTURA-ESCOPO.md` × `AVALIACAO-DESIGN.md` (e R2/R3).
COBERTURA 4.8: "O catálogo tem 8 métricas: `deviations_total`… `payroll_summary`". R1: "O banco tem **nove**, em inglês" (a tabela inclui `data_freshness`); R2/R3 confirmam "9+4".
Por que importa: o catálogo fechado é o guardrail do assistente; dois documentos normativos discordam do seu tamanho e conteúdo.

**A17 — SPRINTS está uma geração atrás da realidade que os outros documentos descrevem.**
Arquivos: `SPRINTS.md` × `SPEC-TECNICA.md`, `PLANO-RECONCILIACAO-NUVEM.md`.
SPRINTS S0: "O frontend ainda não existe" (idem PLANO-BANCO DB-1) — mas a SPEC §6 mede "dashboard 760 ms (pior 2 022 ms), monitor diário 612 ms, painel de TV 552 ms" em "build de produção". SPRINTS S1: as Edge Functions "vivem noutro repositório… até o código delas ser versionado aqui" — RECONC: "baixado para `supabase/functions/` (commit `f210fa1`)". E não existe sprint para a reconciliação/rename (Fase 3), que a RECONC descreve como o caminho crítico atual.
Por que importa: um agente que planeje pelo SPRINTS vai re-planejar trabalho pronto e ignorar o trabalho que de fato falta.

**A18 — COBERTURA afirma conflitos com o PRD que o PRD atual não contém.**
Arquivos: `COBERTURA-ESCOPO.md` × `PRD-OPERAX.md`.
COBERTURA 4.9: "o `PRD-OPERAX.md` lista 'Exportação Excel/PDF' como fora do MVP… O PRD está errado e precisa mudar" e "Risco 'Domínio não libera' | Alto, na tabela de riscos do PRD". O "Não entra" do PRD atual não menciona exportação, e sua tabela de riscos não contém risco de Domínio (contém "Plano de contas de eventos não mapeado").
Por que importa: as correções pedidas (itens 21 e 22 da própria COBERTURA) foram aplicadas sem baixa no documento que as pediu — a lista de 26/27 lacunas superestima o que está aberto.

**A19 — O deep link do relatório é especificado de duas formas incompatíveis dentro da SPEC.**
Arquivo: `SPEC-TECNICA.md` (autocontradição).
§4: link "`/dashboard?unit=<uuid>&de=<YYYY-MM-DD>&ate=<YYYY-MM-DD>`". §6: "As chaves são curtas… `?emp=` empresa, `?un=` unidade, `?per=` período… Empresa e unidade viajam como *slug* do código, **não como uuid**".
Por que importa: é o contrato relatório→dashboard, base da métrica número 1 do PRD ("Divergência dashboard × relatório — zero"); implementado por um trecho, o link do outro não abre filtrado.

**A20 — A matriz de sensibilidade do DICIONARIO usa nomes de domínio que o enum do próprio documento não aceita.**
Arquivo: `DICIONARIO-DE-DADOS.md` (autocontradição).
Matriz: domínios "`pii` … `remuneracao` … `saude` … `disciplinar`". As policies do mesmo documento usam `'compensation'::app.sensitive_domain` e `'health'::app.sensitive_domain`.
Por que importa: quem popular `app.domain_permission` ou escrever policy a partir da matriz usa valor de enum inexistente.

**A21 — Gates e aceites referenciam um documento que não está no conjunto (proposta comercial/escopo).**
Arquivos: `SPRINTS.md`, `COBERTURA-ESCOPO.md`, `SPEC-TECNICA.md`.
SPRINTS S8 (aceite): "critérios do **item 18 da proposta comercial** atendidos"; SPRINTS Fase 3: "§6 do escopo obriga"; COBERTURA inteira confronta "o escopo contratado" (4.3, 4.5, 5.3, item 9, item 20…); SPEC 5b: "O escopo diz 'acompanhamento da operação em tempo real' no item 2".
Por que importa: o critério de aceite final do projeto não é verificável com os documentos disponíveis; qualquer auditoria ou homologação depende de artefato ausente.

**A22 — O defeito de exposição de dado na tela de login (R4) tem prompt de correção, mas nenhum registro de execução.**
Arquivo: `AVALIACAO-DESIGN-R4.md`.
R4: "**a tela de login mostra dado do colaborador antes de autenticar**, e isso não pode ir para o Claude Code"; o documento termina no prompt de correção e em "Depois disso o pacote de design fica fechado" — nenhum documento posterior confirma a correção (as pendências repetidas em R4 §4 são outras: templates em inglês e handoff contra 15 migrations).
Por que importa: o handoff pode entrar no repositório carregando a tela que o próprio avaliador classificou como exposição nominal sem autenticação.

**A23 — A numeração de "sprints do produto" do PLANO-BANCO não corresponde à do SPRINTS.**
Arquivos: `PLANO-BANCO-OPERAX.md` × `SPRINTS.md`.
PLANO-BANCO ("Encaixe nas sprints do produto"): "2 — Motor de detecção… 3 — Relatório consolidado… 4 — Dashboard". SPRINTS: S2 = "Modelo completo e superfície de API", S4 = "Motor em modo sombra", S5 = "Dashboard", S6 = "Alertas e relatório consolidado".
Por que importa: referências cruzadas por número ("Sprint 2 depende de DB-5") apontam para sprints diferentes conforme o documento lido.

### Severidade BAIXA

**A24 — COBERTURA: "26 lacunas" no cabeçalho, "As 27 lacunas" no título da seção.**
Arquivo: `COBERTURA-ESCOPO.md`. Cabeçalho: "**Resultado: 26 lacunas** (era 27…)"; seção: "## As 27 lacunas, agrupadas por natureza" (o item 17 aparece riscado dentro dela). Título não acompanhou a baixa.

**A25 — "8 dos 16 indicadores… não saem" vs lista de 7 ❌.**
Arquivos: `COBERTURA-ESCOPO.md` (interno; ecoado em `SPRINTS.md`). COBERTURA 5.3 lista 7 itens ❌ ("custo de horas extras · … · desvio contra média histórica") e 8 ✅ (soma 15 de "16"); §5 e SPRINTS afirmam "8 dos 16". Uma das contagens está errada ou um indicador não está listado.

**A26 — Contagens da suíte desatualizadas: 11 vs 13 verificações estruturais; "34 asserções".**
Arquivos: `SPEC-TECNICA.md`, `PLANO-BANCO-OPERAX.md`, `SPRINTS.md`, `COBERTURA-ESCOPO.md` × `AVALIACAO-DESIGN.md`, `DECISAO-WHATSAPP.md`. SPEC/PLANO-BANCO/SPRINTS: "11 verificações estruturais"; R1: "agora com 13 verificações estruturais"; COBERTURA: "34 asserções" (23+11), sem as 2 novas nem as "Onze asserções novas em `scripts/97_teste_regras_alerta.sql`". Desatualização inócua, mas em três documentos normativos.

**A27 — 348 vs 353 identificadores pareados, sem explicação.**
Arquivo: `PLANO-RECONCILIACAO-NUVEM.md` (interno). §1b: "**348 identificadores** mapeados 1:1"; Fase 2: "São **353** identificadores pareados um a um". Possivelmente escopos distintos (histórico vs histórico+catálogos), mas o documento não diz.

**A28 — Suíte testada em Postgres 16; produção é PostgreSQL 17.6.**
Arquivos: `PLANO-BANCO-OPERAX.md` × `PLANO-RECONCILIACAO-NUVEM.md`. "escritas e testadas em Postgres 16 local" vs "em PostgreSQL 17.6" — a própria RECONC achou um efeito de versão ("`MAINTAIN` (PG17) sumia dos grants"). Divergência de ambiente declarável.

**A29 — A mesma janela de batidas é "três dias (hoje − 2 .. hoje)" na SPEC e "2 dias / 48h" na RECONC.**
Arquivos: `SPEC-TECNICA.md` × `PLANO-RECONCILIACAO-NUVEM.md`. Provavelmente o mesmo mecanismo em enquadramentos diferentes (2 dias retroativos = 3 datas), mas o teto "48 h no máximo" da janela da Fase 3 é derivado do número menor — vale unificar o enunciado antes de dimensionar paradas.

**A30 — `app.refresh_dashboard()` e `app.revoke_deviation()` são citadas pela SPEC e pelo PLANO-BANCO e não constam do DICIONARIO.**
Arquivos: `SPEC-TECNICA.md`, `PLANO-BANCO-OPERAX.md` × `DICIONARIO-DE-DADOS.md`. O dicionário documenta tabelas, views, RPCs de `public` e helpers de `util`, mas nenhuma função do schema `app` — lacuna de completude no documento que a SPEC chama de "modelo de dados completo".

**A31 — O pseudocódigo do motor emite tipos em português; o catálogo real usa códigos em inglês.**
Arquivos: `SPEC-TECNICA.md` × `COBERTURA-ESCOPO.md`, `AVALIACAO-DESIGN-R3.md`. SPEC 3.2: "emitir entrada_atrasada… sem_marcacao… batida_em_folga"; os códigos reais citados são "`late_entry`, `break_exceeded`, `no_punches`" (R3) e "`late_entry`", "`incomplete_punches`" (COBERTURA). Ilustrativo, mas no componente onde valor literal errado grava linha inválida (ver A6).

---

## Artefatos ausentes do conjunto (dimensão 4)

Tudo abaixo é citado pelos 12 documentos e **não** está entre eles. Não é defeito por si; é o que esta auditoria
não pôde conferir e a próxima precisa localizar.

**Documentos e pacotes**
- `CLAUDE.md` (citado por SPEC, RECONC — inclusive como fonte de decisões: "A decisão está registrada no CLAUDE.md")
- Proposta comercial / escopo contratado (SPRINTS "item 18 da proposta comercial"; COBERTURA inteira; SPEC "item 2 do escopo"; PRD "item 9/20" via COBERTURA)
- "resumo técnico original de vocês" (COBERTURA 4.9)
- `PROMPT-CLAUDE-DESIGN.md`; `docs/PROMPT-CLAUDE-DESIGN-CORRECOES.md` (R1)
- Pacote de design `OperaX.zip` e artefatos do handoff: `TELAS.md`, `COMPONENTES.md`, `README.md` (do handoff), `readme.md` (do DS), `_ds_extras.js`, `_ds_manifest.json`, `tokens/colors.css`
- `docs/preflight-YYYYMMDD.txt` (saída prevista do pré-voo)

**Scripts** (todos sob `scripts/`)
- `gerar_dicionario.py`, `testar_migrations.sh`, `01_preflight.sql`, `00_diagnostico.sql`, `_test_stub_supabase.sql`
- `97_teste_regras_alerta.sql`, `98_teste_isolamento_tenant.sql`, `99_verificacao_rls.sql`, `verificar_docs.py`
- `sb_sql.sh`, `introspeccao_nuvem.py`, `rename_map.py`, `gerar_rename_nuvem.py`, `ensaiar_rename_nuvem.sh`, `ensaiar_rename_staging.sh`, `conferir_copia.py`, `comparar_catalogos.py`, `provar_postgrest.sh`
- `_producao.sql` (declarado gitignored) e `_baseline.sql` (declarado inexistente — "e isso é honesto")
- `<a criar>_sync_batidas_cron.sql` (citado por `sync-batidas/index.ts` como arquivo que "não existe neste repositório")

**Migrations citadas por nome**
- `00_blindagem_imediata` … `11_performance` (série `20260815100000…`)
- `20260815101150_11b_rename_pt_en.sql`, `20260815101200_12_data_freshness.sql`, `20260815101300_13_detection_cadence_alert_contract.sql`, `20260815101400_14_whatsapp_provedores.sql`, `20260822160000_15_rebrand_fastpark.sql`
- Na nuvem: os 11 stubs `20260811120000`…`20260813164000` (DDL "se perdeu") e a `20260813163000` citada pelo código

**Código**
- `supabase/functions/` (`sync-cadastro`, `sync-batidas`, `secullum-test-auth`, `_shared/secullum-client.ts`, `_shared/batida-sync.ts`, `_shared/postgres-client.ts`, `index.ts`)
- Backend: `operax/core/tenant.py`, `backend/operax/core/db.py`, `operax/motor/{jornada,deteccao,revogacao}.py`, `operax/alertas/{outbox,sender,ciclo}.py`, `operax/alertas/provedores/`, `operax/agente/` (`catalogo.py`, `executor.py`), `operax/imports/`, `server/routers/` (`employee.py`)
- Frontend: `frontend/`, `lib/tv/queries.ts`; teste E2E da tela de TV (SPEC §6)
- Ambientes: `backend/.env.staging`, `frontend/.env.local.staging`

---

## Inventário consolidado de pendências (dimensão 5)

### Abertas e consistentes entre documentos
| Pendência | Onde aparece | Dono declarado |
|---|---|---|
| Rate limit da API Secullum (única sobra das 5 da SPEC §2) | SPEC §2/§10#2; PRD risco; COBERTURA 4.5 e item 17 | **nenhum** |
| Decidir ingerir a apuração do Secullum (rota `Calcular`) | SPEC §2 ("continua disponível e continua não tomada"); SPEC §10#3 (enunciado antigo) | **nenhum** |
| Saldo de horas: espelhar × calcular | COBERTURA ("Espelhar é a única resposta…"), R1 (métrica `hour_balance`), R3 §5, R4 §4 | Owner ("são suas") |
| Mapa de código de evento de folha → categoria | COBERTURA §5/5.3; SPRINTS Fase 3 ("bloqueante"); R3/R4 | Owner + contabilidade |
| Formato de exportação de relatórios (Excel/PDF) | COBERTURA 4.9 e "antes de eu mexer"; R3/R4 | Owner |
| Cláusula de propriedade intelectual | PRD ("Pendente de redação"); SPRINTS S0 + G6 | produto/comercial, sem nome |
| Estrutura real da Kastro Park (CNPJs, unidades, escalas) | PRD; SPEC §10#6; SPRINTS S3 | **nenhum** |
| Policy do bucket de Storage espelhar `util.can_see_employee` | SPEC §8; PLANO-BANCO risco 5; DICIONARIO (nota em `app.document`) | **nenhum; sem sprint** |
| Papéis LGPD / contrato de tratamento; retenção e expurgo | SPEC §8 | **nenhum; sem sprint** |
| Token de exibição da TV (principal novo no modelo de autorização) | SPEC §6 ("Fica registrado como decisão pendente") | **nenhum** |
| Fase 3 da reconciliação (janela ≤48h, aplicar 11b+12–15, religar com prova positiva) | RECONC §3 | implícito, sem data |
| Fechar riscos 3 e 4 do §4b **antes** do rename (alarme; 200 com ingestão zero) | RECONC 4b | **nenhum; sem sprint** (A9) |
| Decidir destino de `public.rls_auto_enable` | RECONC §5 ("decisão do dono") | "o dono", sem nome |
| Limpar o resíduo pt dos 29 nomes compostos "nos dois lugares ao mesmo tempo" | RECONC §1b | **nenhum** |
| Decisão de produto do monitor pós-reconciliação (afirmar presença com `batida_marcacao`) | RECONC §1b ("É decisão de produto") | **nenhum** |
| Trocar os 5 códigos de template para inglês | R3 §3A/§5; R4 §4 | Owner/autor |
| Rodar o handoff contra o repositório atualizado (+`verificar_docs.py`) | R3 §5; R4 §4 | autor |
| Registro dos componentes novos no `_ds_manifest.json` | R2 (ressalva); R3 §3B ("se houver rodada 4… peça o registro") | **nenhum** |
| Correção da tela de login do celular (exposição pré-autenticação) | R4 §2/§3 — prompt escrito, execução **não registrada** (A22) | autor |
| Verificação de negócio Meta + aprovação de templates na WABA do cliente | WHATS §5 | cliente |
| Cláusula contratual: risco de banimento (provedor não oficial) é do cliente | WHATS §5 ("Registrar em contrato…") | **nenhum** |
| Exibir `fn_whatsapp_readiness` na tela de Administração | WHATS §5 ("a tela… deveria mostrá-lo") | **nenhum** |
| Ajustar redação comercial "tempo real" → cadência declarada | SPEC 5b#3 | **nenhum** |
| Particionar `audit_log` ao passar de ~50M linhas | PLANO-BANCO risco 6; DICIONARIO nota | **nenhum** (gatilho por volume) |
| Homologação de regras com cliente + jurídico/RH (G5) | PRD princípio 6; SPRINTS S6/G5 | produto |

### Conflitos de estado (mesma pendência, estados diferentes)
1. **Dia corrente / monitor viável** — COBERTURA 4.5: "**Resolvido.**"; SPEC §10#1 segue listando "API expõe marcação do dia corrente?" como trava (A13).
2. **Paginação, valor apurado, token** — respondidos na SPEC §2 ("fecharam em 22/08/2026"); abertos na SPEC §10 (A13).
3. **Periodicidade do relatório e login do gestor** — "já viraram configuração" (PLANO-BANCO) vs pendências que travam (PRD; SPEC §10#8/#10) (A14).
4. **Exportação e risco do Domínio no PRD** — COBERTURA manda corrigir (itens 21/22); o PRD atual já não contém nenhum dos dois; a COBERTURA continua afirmando o conflito (A18).
5. **Frequência de sync** — COBERTURA item 17: "resolvido: 30 min"; RECONC prova 15 min em produção — a resolução registrada carrega o valor errado (A4).
6. **Diagnóstico do banco atual** — pendência no PRD e SPEC §10#7 e pré-requisito G1; a RECONC executou introspecção completa da nuvem (Fases 0–2 ✅) sem que PRD/SPEC dessem baixa.

### Pendências duplicadas com enunciados divergentes
- **Saldo de horas**: a COBERTURA já embute a resposta ("Espelhar é a única resposta que não recria a exposição jurídica"), enquanto R1/R3/R4 a mantêm como escolha aberta ("decisão: espelhar do Secullum ou calcular").
- **Valor apurado**: SPEC §10#3 pergunta "API devolve valor apurado?" (já respondida: "Devolve"); a pendência real mudou de enunciado ("ingerir apuração como verdade… continua não tomada", SPEC §2).

---

## Riscos declarados × planejamento (dimensão 6)

- Os seis riscos do PRD têm mitigação declarada e, em geral, gate correspondente (G1–G6, modo sombra, instrumentação de custo). ✔
- Os **quatro riscos operacionais do RECONC §4b** (sem transação; janela de 48h sem recuperação; HTTP 200 com ingestão zero; ausência total de alarme) não têm dono, não têm mitigação planejada e não aparecem em SPRINTS nem em PLANO-BANCO — apesar de o próprio documento dizer que "dois deles são mais urgentes que o rename" (A9).
- **Storage do bucket**, **retenção/expurgo LGPD** e **contrato de operadora** são riscos/pendências declarados na SPEC §8 sem nenhuma entrega em SPRINTS (S8 cobre apenas backup/restauração e monitoramento).
- O risco "Evolution API" do PLANO-BANCO está **superado** pela decisão registrada em WHATS e não foi baixado (A3).
- O risco de rate limit segue aberto e está **subdimensionado** pela metade (48 vs ~96 execuções/dia — A4).

## Coerência do plano de execução (dimensão 7)

- Em substância, os gates batem: G1↔pré-voo/PascalCase (PLANO-BANCO DB-0), G2↔DB-12/suíte, G3↔S3/confiança 80, G4↔sombra ≤5% (SPEC 3.5), G5↔regra nasce desligada (PRD princípio 6; DICIONARIO `alert_rule.active` default false), G6↔cláusula IP. ✔
- Incoerências: numeração de sprints divergente entre PLANO-BANCO e SPRINTS (A23); aceite de S2 com contagem de migrations errada (A10); aceite de S8 referencia "item 18 da proposta comercial", critério que nenhum documento do conjunto define (A21); e o plano não contém a fase de execução real do momento — reconciliação/rename e correção dos riscos §4b (A9, A17).
- O DoD do SPRINTS ("`service_role` só existe no backend FastAPI") é violado pelo próprio PLANO-BANCO (A2).

---

## Veredito de prontidão (dimensão 8)

**Como está, o conjunto não orienta com segurança um agente de código.** Não por falta de qualidade — a cultura de
verificação é rara de se ver (medições em vez de leitura, ensaios reproduzíveis, separação explícita entre deduzido e
medido no RECONC) — mas porque os documentos estão em **gerações diferentes da mesma história**, e três dos
normativos apontam para trás:

1. **PLANO-BANCO é o documento mais perigoso do conjunto.** Ele se declara "a instrução de execução para o Claude
   Code" e prescreve um worker Python que uma decisão de 22/08 aposentou (A1), `service_role` numa rota Vercel que a
   SPEC e o próprio SPRINTS proíbem (A2), Evolution API que a decisão registrada substituiu (A3) e nomes/valores de
   objetos anteriores ao rename (A6). Um agente obediente a ele erra em série.
2. **A dupla confiável é DICIONARIO + RECONC — e mesmo ela tem furos.** O dicionário contradiz a si mesmo no exemplo
   canônico (A7), nomeia domínios sensíveis que o enum não aceita (A20) e não contém `cursor_sincronizacao` nem 7 das
   20 tabelas de `secullum` que o RECONC atesta (A8). Quem for gerar baseline, rename ou seed a partir do dicionário
   precisa antes reconciliar esses inventários.
3. **Os pontos onde o agente seria induzido a erro silencioso** — os piores — são: consumir a fila com
   `('pendente','falhou')` e vê-la represar sem erro (A6); implementar a revogação retroativa de 7 dias sobre um
   espelho que só enxerga 2–3 (A5); dimensionar rate limit e frescor sobre cadência de 30 min quando produção roda 15
   (A4); e montar o deep link com `unit=<uuid>` quando a outra metade da SPEC exige slug (A19).
4. **Planejamento**: SPRINTS descreve um projeto que ainda não começou ("O frontend ainda não existe") enquanto a SPEC
   mede o dashboard em produção; não há sprint para a reconciliação nem para os quatro riscos operacionais que o
   RECONC declara mais urgentes que o rename (A9, A17). O plano vigente, se seguido, executa o passado e ignora o
   presente.
5. **Rastreabilidade**: duas mudanças relevantes não têm decisão registrada em lugar nenhum — a cadência real de 15
   min e o rebrand "fastpark" (A4, A15). O conjunto que impressiona pela disciplina de registrar decisões falha
   exatamente nas duas mais recentes.

O que tornaria o conjunto seguro é menos escrever documentos novos e mais **uma passada de baixa**: atualizar ou
marcar como superado o PLANO-BANCO; corrigir os literais/nomes pt na SPEC e no exemplo do DICIONARIO; unificar
contagens (migrations, verificações, métricas); dar baixa nas pendências resolvidas (SPEC §10, COBERTURA 21/22);
registrar as decisões de 15 min e do rebrand; e incorporar ao SPRINTS a fase de reconciliação e os riscos §4b. Até
lá, qualquer agente deveria ser instruído a tratar RECONC + DICIONARIO como fonte primária, PRD como intenção de
produto, e SPEC/PLANO-BANCO/SPRINTS como históricos que exigem confirmação item a item.
