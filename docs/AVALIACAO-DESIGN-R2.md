<!-- verificar-docs: inexistentes-de-proposito app.alert_recipient app.compensation app.origin_unit_map app.payroll_import app.payroll_import_error -->

# OperaX — avaliação do design, rodada 2

Confronto entre o pacote recebido e as cinco correções pedidas em
`PROMPT-CLAUDE-DESIGN-CORRECOES.md`. Mesmo método da rodada 1: dependências de
CDN vendorizadas, protótipo aberto em navegador, cada tela e cada cenário
capturado e medido. Onde há número, veio de medição.

**Veredito: aprovado.** As cinco correções foram feitas, três delas acima do
pedido. Sobraram **dois defeitos**, ambos pequenos em código e específicos — e um
deles é do tipo que passa despercebido até o cliente encontrar.

---

## 1. As cinco correções

| # | Correção | Situação |
|---|---|---|
| 1 | Administração e Painel de TV | **Feita, acima do pedido** |
| 2 | Catálogo de métricas real | **Feita, exata** |
| 3 | Completar o design system | **Feita com ressalva de registro** |
| 4 | Readme do DS e seletor de cenário | **Feita** |
| 5 | Contraste | **Feita, exata** |

### Correção 1 — as duas telas

Administração saiu de 378 caracteres (página em branco) para **2.333**, com cinco
abas: mapeamento, unidades, usuários e papéis, integrações, auditoria.

A curadoria de vínculo veio melhor do que eu especifiquei. Pedi "resolver 200
itens numa sessão, não 5", e a tela entrega: **ação em lote** ("Aplicar sugestões
≥ 90%"), **confiança por linha** com barra colorida, **atalhos de teclado
visíveis na própria tela** (↑↓ percorre · Espaço marca · Enter aplica · Shift+Enter
aplica e avança), paginação 25/50/100, e o caso difícil resolvido — confiança de
22% não recebe "Aplicar" e sim **"Atribuir"**, com o rótulo "Sem sugestão".

E acrescentou uma regra de produto que eu não tinha pedido, mas que está certa:
*"Enquanto não for confirmado explicitamente, o vínculo permanece marcado como
não validado e não entra no consolidado de custo."* Isso amarra a curadoria ao
número da folha, que é o que faz alguém realmente sentar para fazê-la.

Painel de TV: **zero nomes de colaborador** — verifiquei o bloco inteiro no
código, não só na tela. "ÚLTIMA LEITURA 08:40" é o maior tipo do painel, rotação
em dois blocos a cada 12 segundos, e a restrição aparece escrita duas vezes na
própria tela. Fundo escuro por decisão de contexto, correto para parede.

### Correção 2 — catálogo de métricas

Os nove códigos reais estão lá, os quatro previstos também, e os **dez inventados
sumiram**, junto com o texto "14 métricas". Conferido código a código.

### Correção 3 — design system

Os componentes foram construídos: `Table`, `Chart`, `DivergingChart`,
`TrendChart`, `RankBarChart`, `Drawer`, `Tabs`, `EmptyState`, `Toast`,
`Skeleton`, `Pagination`, `Chip`.

E são usados de verdade. O número que mais importa: **as 5 `<table>` cruas viraram
0** — a tabela agora é uma só, usada 11 vezes.

| | Rodada 1 | Rodada 2 |
|---|---|---|
| Instâncias de componente | 78 | **108** |
| `<table>` cruas | 5 | **0** |
| Divs com estilo inline | 237 | 265 |

Os divs cresceram em número absoluto, mas o protótipo cresceu junto (131 KB →
157 KB, com duas telas novas). A proporção melhorou de 0,33 para 0,41
componente por div, e o problema que eu tinha apontado — três implementações
divergentes de tabela — deixou de existir.

**A ressalva.** Os componentes vivem em `_ds_extras.js` e **não foram registrados
no `_ds_manifest.json`**, que está byte a byte idêntico ao da rodada 1: os mesmos
16 componentes, os mesmos cards, e o starting point ainda é a tela
`visao-executiva` do Aegis.

Na prática: funciona no protótipo e funciona no handoff (o `COMPONENTES.md`
documenta a API de cada um). O que se perde é o registro — não aparecem no
navegador de componentes do design system, e uma sessão futura do Claude Design,
partindo do DS, não saberá que existem e vai reinventá-los. É dívida de
catálogo, não de código.

### Correção 4 — readme e cenários

O `readme.md` foi reescrito. Zero ocorrências de `equipamentos`, `severity`,
`exposure_hours`, "Alarme", "Anomalia", "Visão Executiva", "Operador" ou
"Visualizador". Agora descreve o OperaX de verdade: nove papéis, quatro domínios
sensíveis, `deviation_event` como tabela-fato, e o vocabulário vinculante
(desvio/indício, nunca "hora extra"; minutos com sinal; escala não confirmada).

O seletor de cenário está no cabeçalho e **funciona** — testei os três clicando:

| Cenário | Resultado medido |
|---|---|
| Dia com ocorrências | "Retrato de 08:40 — há 25 minutos" · 1.696 caracteres |
| Dia sem ocorrência | estado vazio · 807 caracteres |
| Dado atrasado | "Retrato de 07:12 — há 1h52" · 1.767 caracteres |

### Correção 5 — contraste

Os cinco tokens estão nos valores exatos que sugeri. Recalculei em WCAG:

| Token | Antes | Agora |
|---|---|---|
| `--alert-foreground` | 2,55:1 reprova | **4,60:1** |
| `--foreground-quaternary` | 2,68:1 reprova | **4,54:1** |
| `--accent-orange` | 3,33:1 | **4,53:1** |
| `--bad-foreground` | 3,88:1 | **4,50:1** |
| `--good-foreground` | 3,61:1 | **4,50:1** |

Todos passam AA. O tema escuro não foi tocado, como pedido.

---

## 2. Defeitos novos

### A. O cenário "Dado atrasado" ainda mostra 08:40 — prioridade 1

O banner diz corretamente **"Retrato de 07:12 — há 1h52"**. Mas na mesma tela,
dois textos seguiram com o horário fixo da leitura normal:

1. O card de resumo: **"Sem marcação · 6 · até 08:40"**
2. O detalhe da ocorrência: **"Nenhuma marcação de entrada registrada até a
   leitura de 08:40."**

Medido no navegador, não lido no código: alternei para "Dado atrasado", extraí o
texto renderizado e contei as linhas que ainda citam 08:40.

No código, o padrão certo já existe e é usado onze vezes — `velho ? '07:12' :
'08:40'`. Estes dois pontos ficaram de fora. Também escapou o texto do estado
vazio, "Todas as unidades dentro do previsto na leitura das 08:40".

Isto é a regra 1 exatamente, e o defeito que ela existe para impedir: uma tela
que anuncia dado velho e, três centímetros abaixo, afirma um horário que aquele
dado não sustenta. E é do tipo que chega em produção, porque só aparece num
cenário que ninguém demonstra em reunião.

### B. Cinco tabelas do handoff não existem no banco — prioridade 1

O `README.md` do handoff promete: *"cada tela abaixo aponta a view ou a função
que a alimenta"*. Extraí os 27 identificadores de banco citados nos três
documentos e validei contra o schema real. **22 conferem. Cinco não existem:**

| Citado no handoff | O que existe de verdade |
|---|---|
| `app.alert_recipient` | `app.alert_rule_target` |
| `app.compensation` | `app.employee_compensation` |
| `app.origin_unit_map` | `app.unit_secullum_map` |
| `app.payroll_import` | `app.file_import` |
| `app.payroll_import_error` | não existe — os erros por linha estão em `file_import.report` (jsonb) |

O `DICIONARIO-DE-DADOS.md` estava entre os arquivos subidos, com os nomes
corretos. Os cinco foram inventados por plausibilidade mesmo com a fonte à mão —
o que vale registrar, porque é o modo de falha que mais se repete: nome que
*parece* certo passa por revisão humana sem levantar suspeita.

O impacto é direto. `app.origin_unit_map` é a tabela da tela de mapeamento, a
mesma que veio tão bem desenhada. O Claude Code vai procurá-la, não achar, e
então inventar uma migration criando-a — duplicando `unit_secullum_map`.

---

## 3. O que continua íntegro

Verificado de novo, para descartar regressão:

- **"hora extra"**: 0 ocorrências. **CPF, RG, PIS**: 0.
- **"agora"**: uma ocorrência, e é legítima — o botão "Executar agora" da aba de
  integrações. Regra 3 trata de frase de alerta, não de rótulo de ação.
- Minutos com sinal, "escala não confirmada", "Conferir no Secullum", papel que
  remove blocos em vez de desabilitar: todos preservados.
- Tema claro segue como padrão, sem `data-theme` — decisão mantida.

---

## 4. O que ficou fora desta rodada

O pacote subido para o Claude Design é o da rodada 1 — **13 migrations**. Ele não
conhece `app.message_template`, `public.fn_whatsapp_readiness()` nem a decisão
dos três provedores de WhatsApp, que veio depois.

Consequência: a tela de Regras de alerta não tem seletor de provedor, nem o
estado "template não aprovado", que é o estado de falha silenciosa que
`fn_whatsapp_readiness()` existe para tornar visível. Não é defeito da rodada —
é o assunto da rodada 3.

---

## 5. Prompt da rodada 3

Três blocos. Suba o pacote atualizado antes (**15 migrations**), senão o bloco 3
não tem o que ler.

### Bloco 1 — coerência do cenário "Dado atrasado"

> No cenário **Dado atrasado** o banner diz "Retrato de 07:12 — há 1h52", mas
> três textos da mesma tela continuam com o horário da leitura normal:
>
> 1. o card de resumo — "Sem marcação · 6 · **até 08:40**";
> 2. o detalhe da ocorrência — "Nenhuma marcação de entrada registrada até a
>    leitura de **08:40**";
> 3. o estado vazio — "Todas as unidades dentro do previsto na leitura das
>    **08:40**".
>
> Faça os três derivarem do cenário, como o banner já faz. Vale varrer a tela
> inteira: **nenhum horário de leitura pode ser fixo**. É a regra mais dura do
> produto — a tela não pode afirmar um horário que o dado não sustenta, e o
> cenário de dado velho é justamente onde isso engana.

### Bloco 2 — nomes reais de tabela no handoff

> Cinco tabelas citadas em `TELAS.md` e `README.md` não existem no banco.
> Substitua pelos nomes reais — estão todos no `DICIONARIO-DE-DADOS.md`:
>
> - `app.alert_recipient` → **`app.alert_rule_target`**
> - `app.compensation` → **`app.employee_compensation`**
> - `app.origin_unit_map` → **`app.unit_secullum_map`**
> - `app.payroll_import` → **`app.file_import`**
> - `app.payroll_import_error` → não existe; os erros por linha ficam em
>   **`file_import.report`** (jsonb)
>
> Depois disso, confira **todos** os identificadores de banco citados nos
> documentos do handoff contra o dicionário. O handoff promete que cada tela
> aponta a view que a alimenta; um nome inventado faz o Claude Code criar uma
> migration duplicando tabela que já existe.

### Bloco 3 — os três provedores de WhatsApp

> Decisão nova, posterior ao desenho: o OperaX suporta **três provedores de
> WhatsApp** — `meta_cloud` (API oficial da Meta), `z_api` e `uazapi` (não
> oficiais). Isso muda a tela de **Regras de alerta** e a aba **Integrações** da
> Administração.
>
> O que o desenho precisa carregar:
>
> - **A mensagem é um template, não um texto livre.** O provedor oficial exige
>   template aprovado pela Meta com antecedência, com variáveis numeradas. A
>   prévia da mensagem que já existe deve mostrar o template com as variáveis
>   destacadas, não só o texto final.
> - **Estado de aprovação do template**, por tenant: rascunho · em análise ·
>   aprovado · reprovado · pausado. Reprovado precisa mostrar o motivo.
> - **O estado de falha silenciosa.** Regra ligada + provedor oficial + template
>   não aprovado = o alerta some sem erro visível. Esse é o pior estado do
>   produto e hoje não tem desenho. Precisa de um aviso claro na tela de regras,
>   que impeça ligar a regra ou avise antes.
> - **Na aba Integrações**, escolher o provedor. Os dois não oficiais conectam
>   por QR Code e são mais rápidos de subir; em compensação o número do cliente
>   pode ser banido pela Meta sem recurso. O desenho deve informar esse risco no
>   momento da escolha — sem dramatizar e sem esconder.
> - Um tenant tem **no máximo um provedor de WhatsApp ativo**.
