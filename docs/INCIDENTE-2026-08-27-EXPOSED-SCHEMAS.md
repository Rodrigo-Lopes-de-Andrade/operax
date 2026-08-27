# Incidente — 27/08/2026, 17:30: corrigir os exposed schemas derrubou a sync

**Duração:** um ciclo (17:30 → 17:45). **Perda permanente:** nenhuma.
**Causa:** verifiquei o consumidor certo do runtime errado.

---

## Linha do tempo

| Hora (BRT) | Evento |
|---|---|
| — | Medição encontra `db_schema = public,graphql_public,app,secullum` em produção. O `CLAUDE.md` exige apenas os dois primeiros |
| — | Dono autoriza a correção **com uma premissa escrita**: *"nenhum consumidor de produção usa `app` via PostgREST (as funções vão por conexão direta, o painel não funciona — confirme e execute)"* |
| — | Confirmo a premissa **em `supabase/functions/`**: os dois repositórios usam `getSql` (conexão direta), e `postgres-client.ts` diz no topo que `secullum`/`app` nunca devem ser expostos |
| — | Na mesma investigação descubro que **produção não tem Edge Function nenhuma** (`GET /v1/projects/.../functions` → HTTP 200 `[]`) e que o `pg_cron` chama a Vercel via `vercel_jobs_base_url` |
| ~17:05–17:20 | **Aplico** `db_schema = public,graphql_public` e `disable_signup = true` |
| 17:15 | Último ciclo saudável — HTTP 200, `batidasFetched: 232, batidasUpserted: 232` |
| **17:30** | **Os dois jobs → HTTP 500 `FUNCTION_INVOCATION_FAILED`** |
| ~17:43 | Reverto `db_schema`. Mantenho `disable_signup = true` (não afeta chamada de máquina) |
| 17:45 | HTTP 200 de novo, `batidasFetched: 232, batidasUpserted: 232` — recuperado |

O ciclo perdido não deixou buraco: a janela de batidas é de 2 dias e o upsert é
idempotente, então a passada seguinte releu o mesmo intervalo.

---

## Causa

A premissa da autorização era verdadeira sobre `supabase/functions/` — e
irrelevante, porque **não é isso que roda**. Quem roda é o serviço
`kastropark-jobs` na Vercel, e ele **fala com o banco por PostgREST**. Tirar
`app` e `secullum` da lista de schemas expostos o derrubou.

O 500 é a prova de (b) na lista de perguntas que a leitura da Vercel ainda
precisa responder: o runner de produção usa PostgREST, não conexão direta.

---

## Os três aprendizados

### 1. `cron.job_run_details` mente — o sinal real é `net._http_response`

As duas execuções das 17:30 aparecem como **`succeeded`** em
`cron.job_run_details`, com `return_message = '1 row'`. Elas *foram* bem
sucedidas: o job entregou o `net.http_get`. O que aconteceu do outro lado o
`pg_cron` não sabe e não registra.

Quem sabe é **`net._http_response`**, que guarda `status_code` e `content`. Foi
ele que mostrou o 500 e o `FUNCTION_INVOCATION_FAILED`.

```sql
select to_char(created at time zone 'America/Sao_Paulo','HH24:MI:SS') as quando,
       status_code, left(content, 90) as corpo
from net._http_response
where created > now() - interval '3 hours'
order by created desc;
```

⛔ **Nenhuma verificação de "rodou" ou "religou" pode se apoiar em
`job_run_details`.** É a mesma classe de erro que o §4b do plano de reconciliação
já nomeava — "do lado do agendador, um 500 e um 200 são iguais" — e eu a repeti
usando a ferramenta que ele avisava não servir.

### 1b. Existe rastro de execução — e ele não registra a própria queda

Eu afirmei, no meio da investigação, que não havia observabilidade da sync em
produção, porque `app.sync_execucao` tem zero linhas. **Errado.** O runner da
Vercel escreve em **`app.job_execucao`** — tabela que existe em produção e que
**nenhuma migration deste repositório cria** (foi o ensaio de 27/08 que a
revelou, como a única divergência de catálogo entre produção renomeada e o
repositório).

Ela tem `job`, `host`, `status`, `iniciado_em`, `finalizado_em`, `erro`, `resumo`
e uma chave única de "em andamento" — é lock e diário ao mesmo tempo.

⛔ **Mas o incidente não aparece nela como falha: aparece como buraco.** Há
`sync_batidas` às 17:15, 17:45 e 18:00 com `success`, e **nenhuma linha às
17:30**. A função morreu na invocação, antes de conseguir escrever. Ou seja, o
diário registra o que terminou, não o que caiu — e ausência é o único sinal.

É o risco 4 do §4b ("não há alarme nenhum") vivo no runner da Vercel, com uma
volta a mais: quem só olhar `job_execucao` procurando `status = 'error'` não
encontra nada e conclui que está tudo bem.

### 2. Escrita esparsa é normal, e não é sintoma

Cheguei ao revert olhando "43 minutos sem escrita" com um job de 30 em 30
minutos. Errado: o cadastro rodou às 15:30, 16:00 e 16:30 **sem carimbar**
`atualizado_em` nem `sincronizado_em`. Só a passada das 17:00 escreveu, e tocou
as 175 linhas de uma vez.

O revert foi a decisão certa pelo motivo errado — quem provou foi o
`net._http_response`, que só consultei depois de já ter revertido. Decisão certa
por acaso não é método.

### 3. O erro foi de sequência, não de técnica

Quando `GET /functions` voltou `[]` e o Vault apontou para `vercel_jobs_base_url`,
eu tinha acabado de descobrir que **não conhecia o consumidor**. Era ali que a
mudança tinha de parar. Segui porque a autorização já estava dada — sem notar que
ela fora dada sob uma arquitetura que a minha própria investigação, minutos
antes, havia derrubado.

---

## A regra que nasce daqui

> ### Autorização de produção é condicionada às premissas escritas nela
>
> Toda autorização do dono para mexer em produção vale **enquanto as premissas
> declaradas nela continuarem verdadeiras**. Premissa derrubada pela própria
> investigação = **autorização revogada na hora**. Voltar e perguntar, com o que
> mudou na mão.
>
> Não é preciso que o dono revogue. A revogação é automática, e reconhecê-la é
> obrigação de quem executa.
>
> **Aplicação retroativa (27/08/2026):** as autorizações concedidas até esta data
> foram dadas sob a arquitetura "a sync roda em Edge Functions", que caiu.
> **Estão todas revogadas até nova ordem.**

---

## O que isso muda no plano

- **Exposed schemas deixou de ser correção avulsa de painel.** Só se corrige na
  janela de convergência, junto com um `kastropark-jobs` que não dependa mais de
  `app`/`secullum` expostos — ver `RUNBOOK-JANELA-CONVERGENCIA.md`.
- A mitigação que segura hoje continua: `anon` sem `usage` em nada,
  `authenticated` sem alcance a `secullum`, 49 tabelas de `app` com RLS, e
  **`disable_signup = true`**, que ficou aplicado.
- Toda verificação de "religou" nos documentos deste repositório passa a ler
  `net._http_response`.
