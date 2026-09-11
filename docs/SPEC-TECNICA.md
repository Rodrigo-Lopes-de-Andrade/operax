# OperaX — Especificação técnica v1

Complementa `PRD-OPERAX.md` (o quê) com o como. O modelo de dados completo está
em `DICIONARIO-DE-DADOS.md`, gerado por introspecção do banco.

Itens marcados ⏳ dependem da documentação da API do Secullum, que ainda não
chegou. Estão escritos com a decisão já tomada e o parâmetro em aberto.

---

## 1. Arquitetura

```
                         Secullum (source, read-only)
                                   │ HTTPS
  ┌────────────────────────────────┼─────────────────────────────────┐
  │  BACKEND — FastAPI no Railway  │   (único lugar com service_role) │
  │                                ▼                                 │
  │   sync ──► motor ──► outbox ──► sender ──► WhatsApp / e-mail      │
  │     │        │         │                                         │
  │     │        │         │        API do painel  ·  assistente IA   │
  └─────┼────────┼─────────┼──────────────┬───────────────┬──────────┘
        │        │         │              │               │
        ▼        ▼         ▼              │               │
  ┌──────────────────────────────────┐    │               │
  │ SUPABASE                         │    │               │
  │  secullum   espelho cru · PII    │    │               │
  │  app        domínio · RLS        │◄───┘ service_role   │
  │  util       helpers de policy    │      (com filtro    │
  │  public     views + RPC ◄────────┼───┐   de tenant)    │
  └──────────────────────────────────┘   │                 │
     só `public` é exposto ao PostgREST   │ anon key        │ Bearer JWT
                                          │                 │
                                    ┌─────┴─────────────────┴─────┐
                                    │  FRONTEND — Next.js/Vercel  │
                                    │  agregado direto do Supabase│
                                    │  individual/sensível via API│
                                    └─────────────────────────────┘
```

**O `service_role` mora num lugar só: o backend FastAPI.** Nunca no Next.js,
nunca numa route handler da Vercel, nunca no navegador. Uma chave que ignora
toda a RLS não pode ter duas cópias em dois provedores de deploy diferentes.

### Por que a fronteira é schema e não policy

A chave pública do Supabase vive no bundle do painel. Qualquer pessoa abre o
DevTools, pega a chave e chama o PostgREST direto — sem passar pelo frontend.
Portanto:

- Convenção de código ("não fazer `select *`") **não é controle de segurança**.
- Tabela em schema não exposto é inalcançável pela API mesmo com policy errada.
- View sem `security_invoker = on` roda com privilégio do dono e **ignora a RLS
  das tabelas base** — é a forma mais comum de vazamento em projeto que "tem RLS".

### Componentes

| Componente | Módulo | Onde roda | Credencial | Responsabilidade |
|---|---|---|---|---|
| sync | `operax/sync/` | Railway, agendado | `service_role` + token do tenant (Vault) | Espelhar a origem em `secullum` |
| motor | `operax/motor/` | Railway, agendado | `service_role` | Materializar jornada e gravar `app.deviation_event` |
| outbox + sender | `operax/alertas/` | Railway, agendado | `service_role` + credencial do provedor | Enfileirar e consumir `app.alert_queue` |
| API do painel | `server/routers/` | Railway, FastAPI | `service_role` | Servir dado individual e sensível |
| assistente IA | `operax/agente/` | Railway, FastAPI | `service_role` + chave do modelo | Traduzir pergunta em métrica do catálogo |
| dashboard | `frontend/` | Vercel | anon key **apenas** | Apresentação |

**Regra que vale para todo código com `service_role`:** ele ignora RLS. Nenhuma
consulta sem filtro explícito de `tenant_id` — por isso todo acesso passa por
`operax/core/tenant.py`, que exige o tenant já resolvido do token. É onde
vazamento entre clientes acontece na prática, porque a rede de proteção está
desligada.

O frontend nunca recebe `service_role`. Quando precisa de dado individual ou
sensível, chama o FastAPI com o access token do Supabase; o backend valida contra
o JWKS, resolve tenant e papel, e revalida o domínio sensível antes de responder.

---

## 2. Sincronização

### Estratégia

Incremental por cursor, guardado em `app.sync_run.cursor_until`. Cada entidade
tem sua própria linha de execução: cadastro muda pouco, marcação muda o tempo todo.

| Entidade | Frequência sugerida | Janela de releitura |
|---|---|---|
| Empresa, Departamento, Horário | diária | completa |
| Funcionário, Estrutura | diária | completa |
| Afastamento | diária | 90 dias |
| Batida | **15 min** (decisão de 24/08) | 7 dias retroativos, 1×/dia |

A releitura retroativa de 7 dias existe porque marcação é corrigida depois do
fato. Sem ela, correção feita ontem em batida de anteontem nunca chega.

> **Backfill de 7 dias: entregue no código em 25/08, ainda não agendado.**
> `sync-batidas` aceita `{"scope":"backfill"}` e lê `BACKFILL_WINDOW_DAYS` (7), e
> a janela incremental virou configuração (`BATIDAS_WINDOW_DAYS`). O que falta
> para o contrato ser verdadeiro em produção é **uma entrada de pg_cron no
> projeto da nuvem** chamando a função com esse escopo uma vez por dia, fora de
> pico — DDL na nuvem, que este repositório não aplica sozinho.

### Idempotência

Upsert por chave natural da origem (`Id` do Secullum) + `tenant_id`. Reprocessar
a mesma janela não cria linha nova.

### Multi-tenant

O worker itera sobre `app.integration where provedor='secullum' and ativo`, resolve
a credencial no cofre e sincroniza um tenant por vez. Nenhuma consulta cruza
tenant. Falha em um tenant não interrompe os outros — registra em
`app.sync_run` com status `falhou` e segue.

> **Onde isto roda, desde 22/08/2026:** em Edge Functions do Supabase
> (`sync-cadastro`, `sync-batidas`, `sync-fotos`, `secullum-test-auth`), não no worker Python
> descrito acima. A decisão está registrada no `CLAUDE.md`. O que segue vale
> como contrato do que a sincronização precisa garantir, seja onde for que ela
> execute.

### ⏳ Pendências

Quatro das cinco fecharam em 22/08/2026, não por documentação, mas por leitura
do código que já roda: `supabase/functions/_shared/secullum-client.ts`.

- ~~**Autenticação**: escopo do token, validade, renovação.~~ **Respondido.**
  OAuth *password grant* em `autenticador.secullum.com.br` (`/Token`,
  `/ReinvidicacoesToken`), com `client_id` fixo `"3"` documentado pelo Secullum
  para o Secullum RH. Quando o usuário tem acesso a mais de uma conta, o banco é
  escolhido por `ListarBancos` e viaja no header
  `secullumidbancoselecionado` — daí o quinto secret, `SECULLUM_BANK_ID`, que
  não aparece no painel de secrets junto dos outros quatro.
- ~~**Tamanho de página.**~~ **Respondido, e a resposta é "não há".** O endpoint
  de Batidas não suporta paginação nem cursor por Id. A sincronização compensa
  com uma **janela deslizante fixa de três dias** (hoje − 2 .. hoje), que nunca
  reprocessa o passado.
- ~~**A API devolve valor apurado?**~~ **Devolve** — existe a rota `Calcular`.
  **E a sincronização atual não a usa.** A decisão de ingerir apuração como
  verdade, que reduziria muito o risco do motor, continua disponível e continua
  não tomada.
- ~~**Justificativa e afastamento são leitura ou escrita?**~~ **Leitura, por
  decisão estrutural.** Não existe sandbox do Secullum para este cliente: toda
  chamada roda contra produção real. Por isso o client expõe **somente** `get`
  para o webservice de integração — um verbo de escrita acidental não compila,
  em vez de falhar em produção.

Sobra uma:

- **Rate limit.** O limite conhecido é por prefixo de rota, e o único codificado
  é `Calcular`: 100 req/hora — justamente a rota que não é usada. As três que
  são (`Funcionarios`, `Horarios`, `Batidas`) não têm limite documentado no
  código. O limitador local existe mas é *best-effort*: Edge Function não
  garante estado compartilhado entre invocações, então a defesa real contra
  estouro é a frequência do Cron Trigger, não ele.

---

## 3. Motor de detecção

O componente de maior risco do produto. A API entrega **batida bruta**, então o
OperaX apura — e apuração errada com aparência de precisão é pior que dado
nenhum.

### 3.1 Etapa 1 — materializar a jornada esperada

Antes de detectar qualquer coisa, preencher `app.expected_workday`: uma linha por
colaborador por dia, com o que era esperado.

```
para cada employee active, para cada dia do período:
    se existe leave_period cobrindo o dia:
        day_type = 'leave_period' ou 'ferias';  confidence = 100
    senão:
        horario = Horario vigente do employee
        dia = HorarioDia correspondente
        se dia tem entrada e saída previstas:
            day_type = 'trabalho'
            expected_entry, expected_exit, intervalo, tolerâncias := do Horario
            confidence = 100 se o padrão é semanal fixo
                        60  se a escala é cíclica inferida (12x36, 5x1, 6x1)
        senão:
            day_type = 'folga';  confidence = 60 se cíclica, 100 se semanal fixa
```

**Escala cíclica é o ponto crítico.** Estacionamento opera em 12x36 e revezamento.
Se `HorarioDia` do Secullum descreve semana fixa, a escala real não cabe nele, e
qualquer inferência tem confiança baixa por definição.

Consequências desenhadas:

- `confianca < 80` **nunca gera alerta automático** — entra no dashboard marcado
  como "escala não confirmada".
- Se mais de 20% dos colaboradores ficarem abaixo de 80, a saída é cadastrar a
  escala manualmente (`origem = 'escala_manual'`). Isso é trabalho de implantação,
  não bug — e precisa estar dimensionado na proposta.
- A precedência é rígida: **afastamento > folga > jornada**. Período de
  afastamento nunca gera desvio, inclusive sobrepondo a regra de folga.

### 3.2 Etapa 2 — detectar

Entrada: batidas do dia + `app.expected_workday` + `app.deviation_type_config` do tenant.
Saída: linhas em `app.deviation_event`.

```
para cada (employee, dia) com batidas ou jornada prevista:

    jd = expected_workday[employee, dia]
    se jd.day_type em ('leave_period','ferias'):  ignorar o dia inteiro
    batidas = ordenadas por hora

    se jd.day_type == 'folga':
        se batidas não vazio:  emitir batida_em_folga, minutes = +total trabalhado
        seguir para o próximo

    se batidas vazio:
        emitir sem_marcacao, minutes = -jd.workload_minutes
        seguir para o próximo

    se contagem de batidas é ímpar:
        emitir marcacao_incompleta, minutes = 0

    entrada = primeira batida
    delta = entrada - jd.expected_entry            # em minutes, com sinal
    se delta >  jd.tolerance_absence_minutes:  emitir entrada_atrasada,  minutes = -delta
    se delta < -jd.tolerance_extra_minutes:  emitir entrada_adiantada, minutes = -delta

    se há par de intervalo:
        intervalo = retorno - saida_intervalo
        se intervalo > previsto + tolerancia:  emitir intervalo_excedido,     minutes = -(intervalo - previsto)
        se intervalo < previsto - tolerancia:  emitir intervalo_insuficiente, minutes = +(previsto - intervalo)
    senão se saiu para intervalo e não voltou:
        emitir intervalo_sem_retorno, minutes = 0

    saida = última batida
    delta = saida - jd.expected_exit
    se delta < -jd.tolerance_absence_minutes:  emitir saida_antecipada, minutes = delta
    se delta >  jd.tolerance_extra_minutes:  emitir saida_postergada, minutes = delta

    trabalhado = soma dos pares
    se trabalhado > limite_jornada_configurado:
        emitir jornada_excedida, minutes = trabalhado - limite
```

**Convenção de sinal, que sustenta os KPIs:** positivo = excedente (trabalhou
além), negativo = faltante (trabalhou aquém). `sum(minutos)` responde "saldo
líquido"; `sum(abs(minutos))` responde "minutos de desvio". Sem essa convenção,
os dois números precisariam de consultas diferentes e divergiriam.

Emitir **sempre todos os tipos**. Se o tipo conta como desvio nos indicadores é
decidido em `app.deviation_type_config.counts_as_deviation`, aplicado nas views. Assim
a decisão do cliente sobre "conta só hora extra ou também atraso" é um `UPDATE`,
e mudar de ideia não exige reprocessar histórico.

### 3.3 Gravação idempotente

```sql
insert into app.deviation_event
  (tenant_id, employee_id, company_id, unit_id, reference_date, type,
   minutes, expected_time, actual_time, punch_ids, mode, run_id)
values (...)
on conflict (employee_id, reference_date, type)
  where status = 'active' and mode = 'producao'
do update set
  minutes           = excluded.minutes,
  actual_time = excluded.actual_time,
  punch_ids        = excluded.punch_ids,
  updated_at     = now();
```

`company_id` e `unit_id` são gravados **no momento do fato**. Se o colaborador
mudar de unidade depois, o histórico não pode se reescrever.

### 3.4 Correção retroativa

Batida corrigida ou justificada na origem depois do relatório enviado:

```
para cada evento active cuja batida de source mudou:
    se o desvio deixou de existir:
        app.revoke_deviation(id, 'batida corrigida na source', 'revogado')
    se mudou de magnitude:
        revogar o antigo e inserir o novo com supersede_id apontando para ele
```

Nunca deletar. O dashboard mostra o estado atual; a auditoria mostra o caminho.

### 3.5 Modo sombra

⚠️ **O passo 2 mudou em 09/09/2026, e com ele o passo 3.** A versão anterior
mandava comparar com "a apuração do próprio Secullum" — e a origem não tem
apuração a dar: o espelho traz entrada, nunca veredito. A verdade de referência
passa a ser **adjudicação humana**, gravada em `app.deviation_adjudication`. A
medição que fechou aquela porta, e o que a decisão custa, estão em
`docs/DECISAO-VERDADE-DE-REFERENCIA-G4.md`.

```
1. executar com mode='shadow' no período de referência
2. exportar o censo e julgar CADA indício ativo da janela:
     - verdadeiro positivo -> merecia o tempo do gestor
     - falso positivo      -> não merecia, e a causa diz por quê
3. classificar cada falso positivo: escala errada, tolerância errada, bug,
   não bate ponto por função, justificado fora do sistema
4. corrigir e repetir
5. promover para produção quando falso positivo <= 5% por duas execuções
   seguidas — e só com o censo COMPLETO
6. LIBERAR a entrega: `adjudicacao liberar --autor` grava app.alert_release
   com a taxa medida; o sender exige essa linha além do motor promovido
```

**Censo, não amostra.** Medido em produção em 09/09/2026: 820 indícios ativos em
sombra, sobre 326 dias-colaborador e 67 pessoas. Julgar tudo cabe numa tarde e
dispensa a conversa sobre intervalo de confiança. A ferramenta:

```bash
python -m operax.motor.adjudicacao exportar --saida censo.xlsx
python -m operax.motor.adjudicacao importar --arquivo censo.xlsx --autor "Nome"
python -m operax.motor.adjudicacao medir
```

⛔ **Taxa sobre censo parcial não responde ao gate.** `medir` imprime a cobertura
ao lado da taxa e recusa dizer "passou" enquanto faltar veredito na janela — 5%
sobre os 40 casos que alguém julgou não diz nada sobre os 820.

⛔ **O falso negativo saiu do gate.** O passo 2 antigo também pedia "eventos que o
Secullum viu e o OperaX não". Sem veredito da origem esse conjunto não existe, e
quem lê o dia julga o que o motor emitiu, não o que ele deixou de emitir. O G4
mede falso positivo e só.

As views do dashboard leem apenas `modo = 'producao'`, então a sombra pode rodar
em paralelo sem contaminar nada. Evento em sombra só é visível para administrador.

**Nenhum alerta ou relatório sai antes desta etapa fechar.** Duração estimada:
1 a 2 semanas de dados reais.

### 3.5b Cadência do motor

O sync roda a cada 30 min, mas reprocessar 90 dias a cada meia hora é desperdício.
Duas cadências:

| O quê | Quando | Janela |
|---|---|---|
| Detecção incremental | após cada sync, 48×/dia | **só o dia corrente** |
| Reprocessamento retroativo | 1×/dia, fora do horário de pico | 7 dias |

O retroativo existe porque marcação é corrigida depois do fato: sem ele, ajuste
feito ontem numa batida de anteontem nunca vira revogação.

`app.refresh_dashboard()` faz `REFRESH MATERIALIZED VIEW CONCURRENTLY`. A 48
execuções/dia isso precisa ser medido — se o refresh completo passar de alguns
segundos, a matview vira particionada por data e só a partição do dia corrente é
recalculada.

### 3.6 Ao final de cada execução

```sql
select app.refresh_dashboard();   -- REFRESH CONCURRENTLY da matview
```

---

## 4. Ciclo de relatório

### Montagem

```
para cada unit com regra de relatório ativa:
    criar app.report_cycle (period_start, period_end)
    reservar os eventos:
        update app.deviation_event
           set report_cycle_id = <ciclo>
         where tenant_id = ... and unit_id = ...
           and report_cycle_id is null
           and status = 'active' and mode = 'producao'
           and reference_date <= period_end
    enfileirar em app.alert_queue com key de idempotência
```

A reserva é o que garante **um desvio em exatamente um ciclo**: só entra quem
ainda não tem ciclo. Deve rodar em transação — falha no meio não pode deixar
evento reservado para ciclo que nunca foi enviado.

### A divergência que precisa ser declarada

O dashboard filtra por `reference_date` (data do fato). O relatório agrupa por ciclo.
Desvio detectado com atraso pertence à data D mas ao ciclo C+1. Os dois números
**estão certos e são diferentes**.

Solução: o relatório declara. Texto obrigatório quando aplicável:

> *Inclui 3 ocorrências de dias anteriores detectadas após o último envio.*

Sem isso, o gestor abre o dashboard, vê outro número e conclui que o sistema está
errado. É o tipo de erro de produto que não se recupera com explicação depois.

### Conteúdo

Cabeçalho com unidade e período; total de ocorrências e minutos; ocorrências por
tipo; até 10 nomes com mais ocorrências; pendências sem justificativa; e o link
profundo:

```
https://<domain>/dashboard?unit=<uuid>&de=<YYYY-MM-DD>&ate=<YYYY-MM-DD>
```

O dashboard precisa aceitar e aplicar esses parâmetros no carregamento.

---

## 5. Alertas

### Outbox

O motor **nunca envia**. Ele grava em `app.alert_queue`. Um sender consome:

```sql
begin;
select * from app.alert_queue
 where status in ('pendente','falhou')
   and next_attempt_at <= now()
 order by next_attempt_at
 limit 50
 for update skip locked;
-- envia, marca status, incrementa attempts, grava em app.alert_sent
commit;
```

`for update skip locked` permite mais de um sender sem entrega duplicada.
Backoff: 1 min, 5 min, 15 min, 1 h, 6 h. Após 5 tentativas, `descartado` com
registro do erro.

`idempotency_key` é única na tabela. Sugestão de composição:
`<regra>:<data>:<destino>:<hash do conteúdo>`. Reprocessar não reenvia.

### Guardrail individual × grupo

Imposto por trigger no banco: regra com `conteudo = 'individual'` não aceita
destino do tipo grupo. Tentar configurar retorna erro com a explicação.

### Provedor

Abstrair atrás de uma interface `enviarWhatsApp(destino, payload)`. Evolution API
é a implementação inicial; a oficial entra sem tocar no motor. Registrar
`app.alert_sent.cost_cents` desde o primeiro envio — sem isso não há como
saber se o volume comeu a margem da sustentação.

### Destino em claro

`app.alert_queue.destination` guarda o número; `app.alert_sent.destination_hash`
guarda só o hash. O log de longo prazo não precisa do telefone, e o painel não lê
a fila.

---

## 5b. Frescor do dado — consequência direta da cadência de 30 min

Com sync a cada 30 min, **o painel nunca mostra o agora**. Mostra o que era
verdade há até meia hora. Três regras que saem disso:

1. **Toda tela com dado do dia exibe a idade do dado.** `public.fn_data_freshness()`
   devolve, por entidade, quando foi o último sync bem-sucedido e se passou do
   limiar. O padrão é 45 min — 1,5× a cadência, para uma execução perdida não
   virar alarme falso e duas seguidas virarem.

2. **Alerta carrega o horário observado, nunca "agora".** Um atraso de 10 min
   detectado no ciclo seguinte chega até 40 min depois do fato. A mensagem diz
   "entrada registrada às 08:12, prevista 08:00" — não "fulano está atrasado".
   A diferença importa quando o gestor liga para a pessoa.

3. **A promessa comercial é "quase em tempo real", com o intervalo declarado.**
   O escopo diz "acompanhamento da operação em tempo real" no item 2. Com 30 min
   de cadência isso não é literalmente verdade, e a diferença entre prometer
   tempo real e entregar meia hora é o tipo de coisa que gera atrito na
   homologação. Vale ajustar a redação para "atualização a cada 30 minutos".

## 6. Dashboard

### Stack

Next.js 16 (React 19) na Vercel, Tailwind v4, Recharts. A decisão de export
estático foi revertida — mas o servidor que guarda segredo é o **FastAPI no
Railway**, não a Vercel. O Next.js aqui é frontend puro: renderiza, autentica
pelo Supabase e consome dois endpoints.

### Divisão de responsabilidade

| Tipo de dado | Caminho | Credencial |
|---|---|---|
| Agregado não sensível | browser → views e RPCs de `public` | anon key |
| Individual identificável | browser → FastAPI → `app` | `service_role` no backend |
| Sensível (PII, folha, saúde) | browser → FastAPI → `app` | `service_role` + checagem de domínio |
| Matview de resumo | FastAPI apenas | `service_role` |

A matview contém todos os tenants e não respeita RLS. Nunca é exposta.

O mesmo access token do Supabase serve os dois caminhos: o PostgREST o valida
sozinho; o FastAPI o valida contra o JWKS do projeto. **Não existe JWT próprio
nem tabela de usuários própria.**

### Superfície disponível

```ts
// KPIs do período
await supabase.rpc('fn_kpi_period', {
  p_de, p_ate, p_company_id, p_unit_id
})

// Rankings
await supabase.rpc('fn_ranking_by_unit',     { p_de, p_ate, p_company_id, p_limite })
await supabase.rpc('fn_ranking_by_employee', { p_de, p_ate, p_company_id, p_unit_id, p_limite })
await supabase.rpc('fn_recurrence',         { p_de, p_ate, p_min_dias, p_unit_id })

// Séries e listagens (grão de dia — o cliente filtra o intervalo)
supabase.from('vw_deviation_daily_trend')
supabase.from('vw_deviation_summary_by_unit')
supabase.from('vw_deviation_by_employee_day')
supabase.from('vw_deviation_event')          // drill-down
supabase.from('vw_employee')            // sem PII, por construção
supabase.from('vw_unit')
supabase.from('vw_document_expiry')
supabase.from('vw_payroll_summary')
```

O cliente **não** envia `tenant_id`. A RLS resolve por quem está autenticado, e
não adianta mandar — a policy não confia em parâmetro do cliente.

### Filtros e estado

Estado de filtro vive na URL. É requisito, não preferência: o link do relatório
abre o dashboard já filtrado.

As chaves são curtas e legíveis porque um humano lê a URL dentro de uma mensagem
de WhatsApp — `?emp=` empresa, `?un=` unidade, `?per=` período, `?ev=` ocorrência,
`?dia=` o dia do monitor. Empresa e unidade viajam como *slug* do código, não
como uuid: o código é estável, único por tenant e cabe na tela; o uuid é ruído.
Quem resolve slug → id é o servidor, contra as unidades que a sessão enxerga.

### Desempenho

Alvo abaixo de 3 s. Séries e rankings vêm agregados do Postgres. O navegador não
soma linha de evento. Sem realtime na v1 — os dados só mudam quando o worker roda.

Medido em build de produção contra o seed de desenvolvimento, mediana de sete
navegações: dashboard 760 ms (pior 2 022 ms), monitor diário 612 ms, painel de
TV 552 ms.

### Monitor diário

**Caminho 2, não Caminho 1** — e a escolha não é de estilo. A escala do dia vive
em `app.expected_workday`, que não está na superfície pública. Levá-la para lá
seria expor coluna nova numa view de `public`, uma das três decisões que este
projeto sempre para e pergunta. Não precisa ser tomada: a tela é sobre pessoa
nomeada num dia específico, que é Caminho 2 de qualquer forma. `GET
/monitor/diario?dia=&unidade=` lê por `user_scope`, e é a policy
`expected_workday_read` que faz o supervisor ver uma unidade.

O que a tela **não** pode afirmar é mais estreito do que parece, e o formato da
resposta diz isso. As marcações não são espelhadas para o schema `app` — ficam no
espelho da origem, que nunca é exposto. Então "sem indício" significa "a última
leitura não encontrou nada", nunca "presente", e a idade dessa leitura fica ao
lado da contagem.

A urgência é carregada por agrupamento e ordem — *Agora*, *Ainda hoje*, *No
fechamento* — e não por uma terceira escala de cor. A paleta já gasta matiz na
direção do desvio; um segundo eixo de matiz na mesma tabela deixa os dois
ilegíveis. O ranking de tipo → urgência vive num único lugar, em Python, e há
teste que falha se um `case` no SQL começar a rankear também.

### Tela para TV

Rota separada (`/tv`), sem chrome — nem barra lateral, nem crachá de usuário, nem
botão de sair: ninguém está sentado nela, e o único controle que um painel de
parede não pode ter é o que desloga o andar inteiro por esbarrão.

Só agregado. **Nenhum nome de colaborador** — e a regra não é "esconder os
nomes": é que nenhuma consulta desta rota devolve um. `vw_deviation_event` e
`vw_deviation_by_employee_day` estão ausentes de `lib/tv/queries.ts` mesmo sendo
legíveis pela sessão, porque uma tela que nunca pede um nome não vaza um por
refactor, tooltip ou descuido. O teste E2E lê os nomes que o dashboard mostra
hoje e exige que nenhum deles apareça no painel.

Tema escuro por `data-theme="dark"` no subtree da rota, **não** por
`prefers-color-scheme`: o painel é escuro porque um retângulo claro a três metros
num corredor iluminado é ilegível, o que não tem relação com a preferência de
sistema de quem abre o dashboard. O par de direção clareia junto com a superfície
— #7FC4D0 excedente, #FE8F53 faltante.

Auto-refresh a cada 3 min por `router.refresh()`, não `location.reload()`: uma
tela que roda por semanas não pode rebaixar o bundle e piscar branco num corredor
escuro a cada ciclo.

**Divergência assumida: não existe token de exibição.** Esta spec previa "sem
autenticação individual e com token de exibição"; o que existe é uma sessão
Supabase comum, autenticada uma vez no navegador da TV. O motivo é que um token
de exibição não é uma flag — as views são `security_invoker` e a RLS decide por
`auth.uid()`, então o token precisaria de um **principal novo** no modelo de
autorização, o que é mudança de policy e para por regra. Fica registrado como
decisão pendente, não como esquecimento. O custo prático: alguém precisa logar a
TV uma vez, e o refresh do SDK sustenta dali em diante.

---

## 7. Assistente de IA

### Fluxo

Agente LangChain 1.x com `create_agent`, em `backend/operax/agente/`, exposto por
`POST /assistente/perguntar` com streaming SSE.

```
question
   ↓
FastAPI valida o JWT do Supabase → resolve tenant e role
   ↓
agente recebe: question + catálogo de app.metric + domínios permitidos ao role
   ↓
agente devolve JSON: { metric, parameters }   ← nunca SQL
   ↓
catalogo.py valida: métrica existe? está ativa? o role tem o domínio?
   ↓
executor.py roda a view/RPC COMO O USUÁRIO (herda a RLS dele)
   ↓
agente formata o result em text, com stream de tokens
   ↓
registra em app.ai_query (métrica, parâmetros, latência, tokens)
```

O evento `metric` sai antes dos tokens de texto, para a interface mostrar
período e filtros usados enquanto a resposta ainda está sendo escrita.

### Por que não text-to-SQL

Com salário e dado de saúde em base multi-tenant, SQL gerado livremente é
vazamento cruzado e resposta errada apresentada com confiança. O catálogo fechado
troca cobertura por previsibilidade — e "não tenho esse dado" é resposta melhor
que um número inventado.

### Guardrails

- Métrica fora do catálogo → recusa registrada com motivo.
- Domínio sensível sem permissão → recusa antes de consultar.
- Resposta sempre acompanha período e filtro usados, para o usuário conferir.
- Tokens e latência registrados: custo de modelo sai da sustentação mensal.

---

## 8. Segurança e conformidade

O banco já implementa: schemas isolados, RLS em toda tabela de domínio, PII e
saúde apartadas com política de escopo **e** domínio, views com privilégio do
invocador, funções sem execução anônima, credencial em cofre, auditoria.

Pendente fora do banco:

- **Storage.** A policy do bucket de documentos precisa espelhar
  `util.can_see_employee`. RLS de tabela **não** protege o objeto.
- **Papéis LGPD.** Cliente é controlador, EURECA é operadora. Exige contrato de
  tratamento de dados.
- **Retenção.** Definir prazo por categoria e rotina de expurgo.
- **Backup e restauração.** Testar restauração, não só configurar backup.

### Suíte de verificação

```bash
./scripts/testar_migrations.sh
```

Sobe banco descartável, aplica as 14 migrations, roda 23 asserções funcionais de
isolamento (dois tenants, quatro papéis) e 11 verificações estruturais, e regenera
o dicionário de dados. **Roda a cada PR que toca policy, view ou permissão.**

---

## 9. Observabilidade

| Sinal | Onde | Alerta quando |
|---|---|---|
| Falha de sincronização | `app.sync_run` | qualquer `falhou` |
| Sincronização atrasada | `cursor_until` | mais de 2 janelas sem avançar |
| Fila de alerta represada | `app.alert_queue` | > 100 pendentes ou tentativa > 3 |
| Falso positivo do motor | comparação da sombra | > 5% |
| Jornada de baixa confiança | `app.expected_workday` | > 20% abaixo de 80 |
| Custo de mensagem | `app.alert_sent` | acima do orçado no mês |
| Custo de IA | `app.ai_query` | acima do orçado no mês |
| Latência do dashboard | Vercel | p95 > 3 s |

Os dois últimos custos existem porque a sustentação é valor fixo e o custo é
variável. Sem medir desde o primeiro dia, a margem vira negativa sem aviso.

---

## 10. Pendências que travam implementação

| # | Pendência | Trava |
|---|---|---|
| 1 | API expõe marcação do dia corrente? | Monitor diário e alertas em tempo real |
| 2 | Rate limit e paginação | Frequência de sincronização |
| 3 | API devolve valor apurado? | Se sim, reduz muito o risco do motor |
| 4 | Escopo e renovação do token | Cofre e onboarding de tenant |
| 5 | Justificativa é escrita via API? | OperaX vira ferramenta de trabalho, não só de consulta |
| 6 | Escalas praticadas na Kastro Park | Confiança da jornada e volume de cadastro manual |
| 7 | Diagnóstico do banco atual | Confirma nomes e volume reais |
| 8 | Periodicidade do relatório | Regras de ciclo |
| 9 | Domínio do painel | Redirect URLs do Auth |
| 10 | Gestor terá login? | Convite de usuário e escopo |
