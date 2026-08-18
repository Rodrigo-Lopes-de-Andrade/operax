# OperaX — avaliação do design, rodada 4 (mobile)

Verificação da rodada do celular. Mesmo método: dependências vendorizadas,
protótipo renderizado em navegador, telas capturadas e texto extraído.

**Veredito: aprovado, com um defeito que precisa ser corrigido antes do
handoff.** As sete telas de celular cobrem o que foi pedido — e quatro delas eu
não tinha pedido, são estados que ele identificou sozinho. O desktop saiu
intacto. Mas **a tela de login mostra dado do colaborador antes de autenticar**,
e isso não pode ir para o Claude Code.

---

## 1. O que foi entregue

Pedi três telas. Vieram **sete**, e as quatro extras são estados legítimos:

| # | Tela | Pedida? |
|---|---|---|
| 1 | Chegada — ocorrências no recorte do link | sim |
| 2 | Detalhe da ocorrência | sim |
| 3 | Justificar | sim |
| 4 | Enviado — "em análise" | não |
| 5 | Revogada — o indício não existe mais | sim (era regra, virou tela) |
| 6 | Login com retorno ao link | sim (era regra, virou tela) |
| 7 | Sinal ruim — offline, enviando, tentar de novo | sim (era regra, virou tela) |

### As sete regras do celular

Todas cumpridas. Três merecem nota:

**Idade do dado (regra 1).** Está em todas as telas do celular, e o detalhe traz
a frase que amarra a cadeia inteira: *"Detectado na leitura de 08:40. O alerta
pode chegar até 40 minutos depois do fato — o horário acima é o observado, não o
de agora."* É a regra 1 e a regra 3 na mesma linha.

**Ocorrência revogada (regra 2).** Melhor do que pedi. Não só informa que o
indício sumiu — mostra **o que mudou**: "como estava no alerta, 13:47 · previsto
13:30 · −17 faltante" contra "13:29 · previsto 13:30 · dentro do previsto". E
fecha com o tom certo: *"O dado melhorou — não é erro. Não há nada para
justificar."*

**Justificar (regra 3 do produto).** *"Vai para análise do departamento pessoal.
Você não decide sozinho se a justificativa vale."* Escrito na tela, no momento do
envio. É a diferença entre uma justificativa e uma absolvição.

Cor não carrega sozinha: cada valor traz sinal **e** palavra — "−12 · faltante",
"sem par". "Escala não confirmada · não gera alerta" sobreviveu ao tamanho da
tela.

### O desktop saiu intacto

Era o principal risco desta rodada, e não se materializou:

| | Resultado |
|---|---|
| Blocos de tela da rodada 3 | 48, **nenhum removido** |
| Blocos novos | 2 (`isCelular`, `o.naoConfirmada`) |
| `tokens/colors.css`, `_ds_extras.js`, `_ds_manifest.json`, `readme.md` | **byte a byte idênticos** |

### Pontos de quebra documentados

`TELAS.md` responde o que pedi: 390px de referência (360–430 se mantém, abaixo de
360 empilha), ~700px seria tablet — e ele **declara que não desenhou** —, ~1150px
o cabeçalho do desktop vira duas linhas. Declarar o que não foi feito vale tanto
quanto o que foi.

### Handoff

37 identificadores de banco citados, **37 existem**. Zero CPF, RG ou PIS. Zero
"hora extra".

---

## 2. O defeito — prioridade 1

### A tela de login expõe o colaborador antes de autenticar

A tela 6 mostra, **acima do campo de e-mail**, num navegador sem sessão:

> **O LINK APONTA PARA**
> **Marisol Tavares · Shopping Norte**
> `entrada 08:12 · previsto 08:00`

Nome, unidade, horário registrado e horário previsto — para quem ainda não provou
ser ninguém.

**Por que é grave.** É exposição nominal de desvio a quem não foi autenticado. É
a mesma classe de risco que a regra "conteúdo individual nunca vai para grupo"
existe para impedir, e aqui é pior: naquele caso o destinatário ao menos pertence
à operação; aqui basta ter o link. Uma mensagem de WhatsApp encaminhada leva
junto o nome e o desvio da pessoa.

**E não é implementável.** Verifiquei rodando contra o banco, como `anon`:

```
set local role anon;
select count(*) from public.vw_deviation_event;  -- ERROR: permission denied
select count(*) from public.vw_employee;         -- ERROR: permission denied
```

Um navegador deslogado que abrir o deep link não recebe zero linhas: recebe
**erro de permissão**. Para desenhar essa tela seria preciso um endpoint não
autenticado que ignora a RLS — exatamente o buraco que as verificações 3 e 10 da
suíte existem para impedir que alguém abra.

Ou seja: o desenho pede uma coisa que a arquitetura recusa por construção. Isso é
bom — foi a suíte fazendo o trabalho dela, três camadas antes do código existir.

**A correção é pequena.** A tela de login continua existindo e o retorno ao link
continua sendo a decisão certa. Só não pode adiantar conteúdo: mostra que há um
link pendente, não o que ele contém.

---

## 3. Prompt de correção

> Bloco único. Cole na mesma sessão.

---

Uma correção na tela **6 · Login com retorno**, e só nela.

Hoje ela mostra, acima do campo de e-mail e **antes de qualquer autenticação**, um
bloco "O LINK APONTA PARA" com o nome do colaborador, a unidade e os horários
registrado e previsto.

Isso não pode existir. É exposição nominal de um desvio a quem ainda não provou
ter acesso — quem tiver o link, tem o dado, mesmo sem conta. E, do lado técnico,
não é construível: o banco recusa qualquer leitura de ocorrência ou de
colaborador para sessão não autenticada, com erro de permissão. Não existe
informação para preencher esse bloco antes do login.

Substitua por uma confirmação **neutra** de que há um link pendente — algo como
"Você abriu um link de ocorrência. Entre para vê-la." Sem nome, sem unidade, sem
horário, sem tipo de ocorrência.

**Mantenha** o resto da tela como está: o retorno direto para a ocorrência depois
do login (não para a página inicial) é a decisão certa e é o que faz o link do
WhatsApp valer a pena. E mantenha a nota de rodapé sobre o acesso de supervisor,
que fala do papel e não de nenhuma pessoa.

Vale varrer as outras seis telas do celular com a mesma pergunta: **alguma
mostra dado de colaborador antes de haver sessão?** As telas 1 a 5 e 7 são
posteriores ao login e podem mostrar o que mostram.

---

## 4. Depois disso

O pacote de design fica fechado. O que resta do meu lado antes de acionar o
Claude Code:

1. Trocar os cinco códigos de template para inglês na migration de seed
   (`deviation_individual_v3` e companhia), para não conviver com duas
   convenções ao lado de `deviation_type.code`.
2. Rodar o handoff contra o repositório com as 15 migrations.

E seguem sendo suas as três decisões de `COBERTURA-ESCOPO.md`: saldo de horas,
mapa de código de evento → categoria de folha, e formato de exportação.
