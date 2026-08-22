# OperaX — plano de reconciliação do projeto na nuvem

**Decisão de 22/08/2026:** reconciliar o projeto Supabase do cliente com este
repositório, em vez de tratá-lo como sistema legado.

Este documento existe porque a operação **não pode começar hoje** e porque o que
foi descoberto sondando o projeto se perde se ficar só numa conversa.

---

## 1. O que o projeto na nuvem é hoje

> **Nota para quem editar:** os identificadores da nuvem aparecem aqui **sem
> crases**, de propósito. `scripts/verificar_docs.py` confere que todo objeto
> de banco citado entre crases existe no schema deste repositório — e estes,
> por definição, não existem. Colocar crases neles deixa a suíte vermelha.

`nklobmlxyidqxarzisph` ("Kastro Park Ponto"). Levantado em 22/08/2026 pelo
PostgREST, com chave de serviço, **sem ler uma única linha** — as views são
`security_invoker` e os grants vão para `authenticated`, então uma chave de
serviço recebe 403 em tudo. O mapeamento abaixo saiu das mensagens de erro, que
nomeiam a tabela por trás de cada view.

### Superfície pública: nomenclatura anterior ao rename pt→en

| Na nuvem | Neste repositório |
|---|---|
| vw_unidade | `vw_unit` |
| vw_colaborador | `vw_employee` |
| vw_desvio_evento | `vw_deviation_event` |
| vw_desvio_resumo_unidade | `vw_deviation_summary_by_unit` |
| vw_desvio_tendencia_diaria | `vw_deviation_daily_trend` |
| vw_desvio_por_colaborador_dia | `vw_deviation_by_employee_day` |
| vw_documento_vencimento | `vw_document_expiry` |
| vw_folha_resumo | `vw_payroll_summary` |
| fn_kpi_periodo | `fn_kpi_period` |
| fn_ranking_unidade | `fn_ranking_by_unit` |
| fn_ranking_colaborador | `fn_ranking_by_employee` |
| fn_recorrencia | `fn_recurrence` |
| rls_auto_enable | **não existe aqui** — investigar antes de qualquer coisa |
| — | `fn_data_freshness` (migration 12) **falta lá** |
| — | `fn_whatsapp_readiness` (migration 14) **falta lá** |

As colunas seguem a mesma divergência: colaborador_id, data_ref, minutos,
direcao, horario_previsto, horario_realizado onde aqui é `employee_id`,
`reference_date`, `minutes`, `direction`, `expected_time`, `actual_time`.

### O estado é misto, e é isso que impede um `db push`

As tabelas por trás das views são app.unidade, app.colaborador,
app.documento, app.folha_evento — português — mas **`app.deviation_event`
está em inglês**. A nuvem recebeu a migration 04 na versão antiga e a 05 na
versão nova: é um retrato de meio-rename, não uma versão qualquer deste
repositório.

**Consequência:** aplicar as 16 migrations ali criaria app.employee ao lado de
app.colaborador, duplicando o modelo em vez de convergir. A reconciliação
precisa de uma migration de rename escrita **a partir do schema real**, não de
palpite.

### O que já está certo lá

`public` não expõe nenhuma tabela — só views e RPCs. A blindagem das migrations
00, 01 e 03 rodou.

---

## 2. O que bloqueia o início

1. **Senha do banco.** Duas candidatas rejeitadas em 18/08 e retestadas em
   22/08 nos dois projetos e em quatro regiões de pooler. Precisa de reset em
   Dashboard → Project Settings → Database. Sem ela não há DDL nem `pg_dump`:
   o PostgREST não faz nenhum dos dois.
2. **O código das Edge Functions não está aqui.** `sync-cadastro` e
   `sync-batidas` escrevem em app.colaborador, app.unidade e afins. **O
   rename quebra a sincronização**, e não dá para corrigi-la num repositório
   que não a contém. `supabase functions download` precisa vir antes do rename,
   não depois.

---

## 3. Sequência

Cada fase tem um critério de verificação. Nenhuma começa antes da anterior
fechar.

### Fase 0 — destravar (bloqueada no cliente)

- Resetar a senha do banco.
- `supabase login` e `supabase link` para o projeto.
- **Verificar:** `psql` conecta pelo pooler (`aws-0-us-east-1`, usuário
  `postgres.<ref>`, `@` da senha como `%40`; o host direto é IPv6-only e esta
  máquina não tem saída IPv6).

### Fase 1 — fotografar, sem tocar em nada

- `supabase functions download` → `supabase/functions/`. **Primeiro passo real**,
  porque hoje o que alimenta o produto inteiro existe em uma cópia só.
- `scripts/00_diagnostico.sql` e `scripts/01_preflight.sql` (read-only,
  verificados: zero DDL/DML fora de temp).
- `pg_dump --schema-only` → `scripts/_baseline.sql`.
- **Verificar:** `scripts/testar_migrations.sh` já procura por `_baseline.sql` e
  cai no stub simulado quando ele não existe. Com o baseline no lugar, a suíte
  passa a testar contra o schema real. Ganho imediato, risco zero, e não depende
  de decidir mais nada.

### Fase 2 — provar a fusão num banco descartável

- Escrever a migration de rename a partir do que o dump mostrar, usando
  `scripts/rename_map.py` como mapa canônico.
- Aplicar baseline + 16 migrations + rename no descartável.
- **Verificar:** `make db-test` verde, e nenhuma tabela duplicada
  (`colaborador` e `employee` coexistindo).

### Fase 3 — janela

- Backup completo e ponto de restauração.
- **Pausar as Edge Functions** — elas escrevem durante o DDL.
- Aplicar.
- Atualizar as funções para os nomes novos e religar.
- **Verificar:** um ciclo de sync completo sem erro; o dashboard deste
  repositório abre contra o projeto.

---

## 4. O que não decidir sozinho

- Qualquer DDL na nuvem antes da Fase 2 fechar verde.
- O que fazer com rls_auto_enable: função que existe lá e não aqui. Pode ser
  andaime de uma sessão anterior ou parte do desenho de alguém. Ler antes de
  remover.
- O segundo projeto (`wbzaqjlfpqteesehapnn`, vazio, é o que o `.env.cloud`
  aponta): abandonar ou virar staging.
