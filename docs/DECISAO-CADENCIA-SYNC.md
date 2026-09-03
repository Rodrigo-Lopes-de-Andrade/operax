# Decisão — cadência da sincronização e releitura retroativa

**Data:** 24/08/2026 · **Decidiu:** Rodrigo (owner) · **Estado:** vigente

Duas decisões que estavam implícitas no comportamento de produção e explícitas em
lugar nenhum. Este documento é a fonte da verdade das duas; onde outro documento
disser diferente, ele está desatualizado e foi corrigido junto com este.

---

## 1. A cadência oficial é 15 minutos para batidas, 30 para cadastro

O que produção pratica desde que as Edge Functions entraram no ar **passa a ser a
regra escrita**, em vez de continuar sendo um desvio da documentação. Não é uma
mudança de comportamento: é a documentação alcançando o comportamento.

| Entidade | Função | Cadência | Execuções/dia por tenant |
|---|---|---|---|
| `Batida` | `sync-batidas` | **15 min** | **96** |
| `Funcionario` e demais | `sync-cadastro` | **30 min** | 48 |
| `Foto` | `sync-fotos` | **1x/dia** (`17 3 * * *`) | 1 |

⚠️ **A linha de `Foto` é herdada, não decidida aqui.** A cadência diária e o
minuto 17 vieram do `sync-fotos-cron` que a outra equipe criou em produção em
**02/09/2026**; a função passou a ser deste repositório no mesmo dia, e este
documento registra o que ela pratica. Mudar o horário é decisão em aberto — e
não se faz dentro da janela de convergência, onde trocar destino *e* cadência ao
mesmo tempo torna impossível saber qual das duas quebrou.

### As derivadas que mudam junto

Cada número abaixo saía de "30 minutos para tudo" e estava errado por isso.

**~96 execuções/dia de batidas, não 48.** Toda estimativa de volume, custo de
invocação e pressão sobre a origem dobra para a entidade que mais importa.

**O limiar de frescor deixa de ser um número só.** A regra continua sendo
**1,5 × a cadência** — uma execução perdida não alarma, duas seguidas alarmam —
mas a cadência agora difere por entidade, então o limiar também:

| Entidade | Cadência | Limiar (1,5×) |
|---|---|---|
| `Batida` | 15 min | **25 min** (22,5 arredondado para cima) |
| `Foto` | 1x/dia | **36 h** (2160 min) |
| demais | 30 min | 45 min |

⛔ **A linha de `Foto` não é conforto, é o que impede um painel inteiro vermelho.**
Sob o padrão de 45 min uma entidade diária está velha em toda leitura, e
`frontend/src/lib/freshness.ts` reduz o quadro à entidade **mais velha** — o
painel diria "atrasado" para sempre com a sincronização perfeita. A regra não
abriu exceção: 36 h continua sendo 1,5 × a cadência desta entidade. Está na
**migration 35**, que ainda não foi aplicada em produção.

`public.fn_data_freshness` passa a aplicar o limiar **por entidade** quando
nenhum valor é passado. Um valor explícito continua valendo para todas, como
antes — o parâmetro não mudou de significado, só ganhou um padrão que sabe
distinguir batida de cadastro.

**A pendência de rate limit do Secullum reabre.** A `COBERTURA-ESCOPO.md`
registrava a frequência de sync como resolvida e o rate limit como "resta
confirmar". Com 96 execuções/dia em vez de 48, mais a passada de backfill da
decisão 2, o volume real precisa ser recontado antes de qualquer conversa com a
origem — e o número apurado está no relatório do pacote P1.

---

## 2. A releitura retroativa de 7 dias vira entrega, não promessa

A `SPEC-TECNICA.md` contrata que **correção na origem até D-7 vira revogação** do
indício já emitido. Hoje isso não é verdade por implementação: `sync-batidas` lê
uma janela fixa de 2 dias e não sabe buscar o que perdeu
(`PLANO-RECONCILIACAO-NUVEM.md` §4b, risco 2). Uma correção feita no Secullum no
quinto dia nunca chega aqui.

A decisão é fechar essa distância com código:

- a janela deixa de ser constante e passa a ser configuração
  (`BATIDAS_WINDOW_DAYS`);
- entra uma **passada diária de backfill de 7 dias**, fora de pico, idempotente
  pela mesma chave natural do incremental — reler não duplica.

O vocabulário é o que o schema já registra do lado da detecção:
`app.detection_run.scope in ('incremental','backfill')` existe desde a migration
13, e `public.fn_detection_health` já reporta backfill atrasado. A sincronização
passa a usar as **mesmas duas palavras** em `app.sync_run.scope`, para que as
duas metades do mesmo conceito não tenham nomes diferentes.

### O teto de janela de manutenção muda

O `PLANO-RECONCILIACAO-NUVEM.md` impõe **48 h** à janela da fase 3, e o motivo é
o risco 2: mais que isso deixa buraco permanente. Com o backfill de 7 dias
entregue, **o teto passa a ser 7 dias** — uma parada de até uma semana é
recuperada pela passada retroativa seguinte, sem redeploy e sem restauração de
backup.

Isso não é autorização para janelas longas: é a diferença entre "buraco
permanente" e "recuperável". A janela da fase 3 continua sendo agendada pelo
owner.

---

## Estado da entrega

A decisão 1 é documental e vale a partir de agora.

A decisão 2 foi entregue no código em 25/08 (pacote P1): a janela é configuração,
`scope=backfill` lê 7 dias, e as duas coisas têm teste. **Ela ainda não está
agendada**: a passada diária depende de uma entrada de pg_cron no projeto da
nuvem, que é DDL em produção e não sai deste repositório. Até isso acontecer, o
contrato da SPEC é verdadeiro por capacidade e falso por operação — e os
documentos devem dizer as duas coisas.

## Volume real apurado (25/08/2026)

Contado no código, uma chamada de rede por vez, não estimado:

| Passada | Execuções/dia | Chamadas por execução | Total/dia |
|---|---|---|---|
| `sync-batidas` incremental | 96 | 1 login + 1 `GET /Batidas` | 192 |
| `sync-batidas` backfill | 1 | 1 login + 1 `GET /Batidas` | 2 |
| `sync-cadastro` | 48 | 1 login + 3 GET (`Funcionarios`, `Horarios`, `Afastamentos`) | 192 |
| | | **Total por tenant** | **386** |

**145 dessas 386 são login** — um terço do tráfego é autenticação, porque cada
invocação de Edge Function é um isolate novo e o token não sobrevive entre elas.
É o primeiro número a levar para a conversa de rate limit: se a origem apertar,
cachear o token em vez de baixar a cadência é a saída mais barata.
