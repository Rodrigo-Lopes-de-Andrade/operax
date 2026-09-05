<!-- verificar-docs: inexistentes-de-proposito public.vw_employee_photo public.fn_set_employee_photo -->

> ⛔ **SUPERADO — leia isto antes do resto. Versionado em 05/09/2026 pelo
> histórico, não pela decisão.**
>
> **A premissa deste documento caiu, e caiu para o lado oposto.** Ele decide, em
> 28/08, que *"o `sync-fotos` continua sendo da outra equipe, na Vercel"*, e
> recusa por escrito a alternativa de absorver o serviço neste repositório —
> *"custo alto, dono errado"*.
>
> **Em 02/09 o dono escolheu exatamente a alternativa recusada:** a quarta Edge
> Function (`sync-fotos`) passou a existir aqui, com a migration 35 junto. Em
> 04/09 a troca do runner reescreveu os `pg_cron` para as Edge Functions, e o
> `kastropark-jobs` deixou de ser o caminho. A porta estreita ficou sem para
> quem ser aberta.
>
> **Nunca existiram, e não vão existir:** `public.vw_employee_photo` e
> `public.fn_set_employee_photo`. O cabeçalho de exceção acima permanece porque
> o texto os cita.
>
> **O que sobrevive, e é o motivo de este arquivo entrar em vez de ser
> descartado:**
>
> - **§4 — a ordem de corte.** *"Tudo que é caro de desfazer acontece depois de
>   tudo que é barato"*, e o passo 4 (medir que o terceiro parou, não aceitar
>   "já migramos") é a lição do incidente de agosto escrita antes de ela ser
>   precisa de novo. Vale para qualquer corte, não só para este.
> - **§5 — a consequência operacional dos *exposed schemas*.** Enquanto `app` e
>   `secullum` estiverem expostos, tabela nova em `app` nasce exposta — o que
>   vale para as onze migrations da etapa DP. A troca do runner **derrubou o
>   bloqueio** para corrigir os exposed schemas; se a correção já foi aplicada é
>   outra medição, e este documento não a faz.
> - **O registro de que uma alternativa recusada foi escolhida cinco dias
>   depois.** É o tipo de reversão que só aparece se as duas pontas estiverem
>   versionadas.


# OperaX — decisão: porta estreita para o `sync-fotos`

**Decisão:** o `sync-fotos` continua sendo da outra equipe, na Vercel, e passa a
falar com o banco pela **superfície pública** — uma view e uma RPC em `public`.
Com isso os *exposed schemas* voltam a ser só `public` e `graphql_public`, e a
janela destrava.
**Quem decidiu:** Rodrigo (owner), 28/08/2026.
**Alternativas recusadas:** absorver o serviço neste repositório (custo alto,
dono errado) e aceitar `app` e `secullum` expostos indefinidamente (perda
permanente de invariante).

---

## 1. Por que esta é a saída, e não um meio-termo

O contrato "só `public` é exposto, e `public` só tem view com
`security_invoker` e RPC" não é preferência de estilo: é o que faz **toda
migration futura nascer segura sem ninguém pensar nisso**. Uma tabela nova em
`app` não vira endpoint por descuido, porque `app` não é endpoint.

Aceitar `app` exposto não abre uma porta hoje — as tabelas têm RLS e as policies
continuam valendo. O que se perde é a garantia de amanhã. Por isso "aceitar por
escrito" seria aceitar o item errado: não um risco pontual, e sim a suspensão de
um invariante.

O `sync-fotos` não precisa de `app`. Precisa saber **de quem** é a foto e
**gravar** onde ela ficou. Isso cabe numa view e numa RPC — o mesmo contrato que
o painel já usa. Dar a porta suportada é mais barato para os dois lados do que
qualquer um dos extremos.

## 2. O que precisa ser medido ANTES de escrever a migration

⚠️ **Este documento não autoriza a migration.** O contrato abaixo é uma
proposta construída sobre o que o serviço *provavelmente* faz. Escrever a view
sobre uma suposição é repetir o erro de agosto com outra roupa.

Três medições, nesta ordem:

1. **Quais chamadas o `sync-fotos` realmente faz.** Método, caminho, e o
   `Accept-Profile` de cada uma. Fonte: o código do serviço na Vercel, ou o log
   do PostgREST filtrado pelo período de execução dele. Sem essa lista, a view
   é chute.
2. **Com qual credencial.** `anon` + JWT de usuário, ou `service_role`? Cite o
   **nome** da variável de ambiente, nunca o valor. Se for `service_role` num
   serviço da Vercel, isso quebra a regra 4 do projeto e **é um achado maior que
   os exposed schemas** — trata-se em separado, não junto.
3. **Se ele escreve, onde escreve.** Em `secullum` (espelho — o que seria
   grave, porque espelho não recebe escrita de terceiro), em `app`, ou só em
   Storage.

O resultado das três muda a forma do contrato. Traga-as antes de eu fechar o SQL.

## 3. Contrato proposto (a confirmar contra §2)

Dois objetos, ambos em `public`, ambos no padrão do projeto:

**Leitura** — `public.vw_employee_photo`, `security_invoker = on`. O mínimo para
correlacionar e decidir o que ressincronizar:

- identificador do colaborador na origem, matrícula, `photo_updated_at`,
  `photo_hash`.
- **Sem nome, sem CPF, sem RG, sem qualquer coluna de `employee_pii`.** Um sync
  de foto não precisa saber de quem é o rosto; precisa saber qual id ele
  atualiza. Se a outra equipe pedir o nome, a resposta é não, e o motivo é este.

**Escrita** — `public.fn_set_employee_photo(...)`, `security definer` com
`search_path = ''`, recebendo id de origem, caminho no Storage e hash. Grava em
`app`, registra em `app.audit_log` com a origem declarada, e é **idempotente**:
mesmo hash não gera escrita nova.

Escrita por RPC e não por `POST` em tabela é deliberado — assim o que o terceiro
pode fazer é uma lista fechada de operações, não "tudo que a policy permitir".

⛔ **Parada obrigatória:** view nova em `public` com coluna nova exposta. Está
previsto aqui; previsto não é autorizado.

## 4. A ordem de corte — onde isso quebra se for feito errado

Esta é a parte que importa. Em agosto a mudança de exposed schemas foi aplicada
com a premissa de que ninguém usava `app` por PostgREST; a premissa tinha
acabado de cair; produção quebrou. A sequência abaixo existe para que isso não
dependa de ninguém lembrar.

1. **Criar** a view e a RPC, com grant para o papel que o `sync-fotos` usa
   (§2.2). Aditivo, não quebra nada, `app` segue exposto.
2. **A outra equipe migra em homologação** e prova que funciona lá.
3. **A outra equipe migra em produção.**
4. **Medir que eles pararam.** Nenhuma requisição com `Accept-Profile: app` ou
   `secullum` durante uma janela declarada — sugestão: **72 horas cobrindo pelo
   menos um fim de semana**, porque job que roda semanalmente não aparece em
   24 h. A prova é a medição, não o "já migramos" no chat.
5. **Só então** corrigir os *exposed schemas*.
6. **Só então** reescrever os jobs do `pg_cron` e abrir a janela.

O passo 4 é o único que não pode ser pulado, e é o mais tentador de pular: ele
não produz nada visível e atrasa a janela em três dias. Foi exatamente esse
passo que faltou em agosto.

**Critério de reversão:** se depois do passo 5 qualquer coisa quebrar, a volta é
reexpor os schemas — segundos, sem migration. A view e a RPC ficam. É por isso
que a ordem é essa: tudo que é caro de desfazer acontece depois de tudo que é
barato.

## 5. O que fica registrado como risco enquanto isso não fecha

Entre hoje e o passo 5, `app` e `secullum` seguem expostos ao PostgREST. Isso
significa:

- As policies de RLS continuam valendo — não há leitura irrestrita.
- Mas **toda tabela nova em `app` nasce exposta**, e nenhuma delas passa pela
  disciplina de `security_invoker` das views de `public`.

**Consequência operacional, válida desde já:** enquanto os exposed schemas
estiverem errados, **nenhuma migration que crie tabela em `app` entra em
produção sem revisão explícita da superfície**. Isso vale para as onze da etapa
DP — o que reforça a ordem já escrita em `SPRINTS-DP.md`: a etapa não começa em
produção antes disso.

Dono do risco: Rodrigo. Revisão: na abertura da janela, ou em **15 dias**, o que
vier primeiro. Se a outra equipe não responder em 15 dias, isso deixa de ser
pendência técnica e vira escalonamento.

## 6. Se a outra equipe recusar

A recusa é possível e não é irracional — é trabalho no roadmap deles. Nesse
caso, a decisão volta a ser entre absorver o serviço e aceitar o buraco, e o
custo da opção C já terá sido medido (§2), o que torna a conversa concreta em
vez de hipotética.

O que **não** é opção: manter a situação atual sem dono, sem data e sem
registro. É assim que invariante de segurança morre — não por decisão, por
inércia.
