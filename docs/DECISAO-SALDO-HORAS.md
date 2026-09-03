# OperaX — decisão sobre saldo de horas

**Decisão:** o OperaX **calcula** o saldo, não apenas espelha.
**Quem decidiu:** Rodrigo (owner), 28/08/2026.
**O que esta decisão reverte:** a recomendação escrita em `COBERTURA-ESCOPO.md`,
seção "O que precisa de decisão antes de eu mexer" — *"Espelhar é a única
resposta que não recria a exposição jurídica que o resto do desenho evita."*

Este documento existe porque a reversão é de uma recomendação registrada. Uma
decisão que contraria documento anterior sem deixar rastro vira, seis meses
depois, "ninguém sabe por que está assim".

> ⛔ **Leia a §1 antes do resto.** O passo da §8 foi executado em 02/09/2026 e
> derrubou a premissa em que este documento foi escrito. A decisão continua de
> pé; o que muda é a natureza dela — deixa de ser escolha entre duas opções e
> passa a ser a única disponível.

---

## 1. O achado que muda a natureza da decisão

**A versão de 28/08, que a medição corrigiu.** A discussão foi enquadrada como
binária — espelhar **ou** calcular — e o argumento era que ela não é, porque
*"o espelho já existe: `secullum.Batida` tem a coluna `NBanco`, e o bloco de
compensação vive em `secullum.HorariosOpcoes`"*.

⛔ **Medido em produção (`nklobmlxyidqxarzisph`) em 02/09/2026: o espelho não
existe.** Não como "a coluna está vazia" — como "a coluna não é isso":

| O que se supunha | O que produção tem |
|---|---|
| `NBanco` = saldo do dia | `boolean not null`, **true em 0 de 1.653 batidas**, 0 colaboradores |
| `HorariosOpcoes` = bloco de compensação | `Compensacao` **null nas 94 escalas** |
| — | `Funcionario.BancoHorasId` **null nos 80 ativos** |

Uma varredura por qualquer coluna numérica de saldo, banco, compensação, crédito
ou minuto em **todo** o schema `secullum` não devolve nenhum acumulado por
colaborador: o que existe é **configuração** (modo, limites, fechamento) e
**marcas por dia**, nunca minutos acumulados.

**Este cliente não opera banco de horas no Secullum.** Não há política atribuída,
não há modo de compensação, e a marca de banco nunca foi acionada.

⚠️ **O contraste que sobra, e que é pergunta para o cliente, não inferência:**
`Compensado` está `true` em **1.379 de 1.653** batidas (83%) e `Neutro` em 129.
Compensação acontece — só não pelo instrumento "banco de horas" do Secullum. O
que essa marca significa na operação da FastPark não está no banco.

**Consequência para esta decisão:** ela deixa de ser reversão de julgamento e
passa a ser **restrição de origem**. Não há o que espelhar, então "só espelhar"
nunca foi opção. É a candidata (a) da §4, confirmada por medição.

O outro lado do enquadramento original **continua valendo**: o cálculo já
existe. A convenção de sinal do motor (`SPEC-TECNICA.md` §3) define positivo =
excedente, negativo = faltante, e diz que `sum(minutos)` responde *"saldo
líquido"*. O OperaX já produz um número com cara de saldo, hoje, sem ninguém ter
decidido nada. **O que nunca foi decidido é como chamá-lo.**

## 2. São dois objetos diferentes, e essa é a raiz do risco

| | Saldo de desvio (OperaX) | Saldo de banco de horas (Secullum) |
|---|---|---|
| O que é | soma com sinal dos minutos de desvio no período | instrumento legal de compensação |
| De onde vem | `app.deviation_event`, apurado pelo motor | ⛔ **não existe nesta base** — ver §1 |
| Governado por | `app.deviation_type_config` — o que conta como desvio | acordo de compensação, prazo, DSR, convenção |
| Serve para | gestão: onde está a distorção, quem repete | folha e obrigação trabalhista |
| Diverge? | **sim, e é esperado** | é o registro oficial |

Os dois produziriam números diferentes para a mesma pessoa no mesmo mês. Isso
não é bug — é consequência de serem coisas distintas. **O perigo não é calcular;
é chamar os dois de "saldo".**

Um gestor que vê "saldo: −4h20" numa tela do OperaX e age em cima disso está
agindo sobre um número que não é o da folha. É exatamente a exposição que a
regra de vocabulário do projeto já evita quando proíbe "hora extra": o registro
oficial é o Secullum, e divergência com ação de gestor em cima é exposição do
fornecedor.

⚠️ **E a medição da §1 agrava, não alivia.** Sem o oficial ao lado, o número do
OperaX vira o único número na tela — e um número sozinho é lido como *o* número.
A disciplina de nome da §3 deixa de ser boa prática e passa a ser a única
proteção que resta.

## 3. A forma da decisão

A decisão "o OperaX calcula" é adotada **na seguinte forma**, que a cumpre sem
recriar a exposição:

1. **O OperaX calcula o seu número e dá a ele o seu próprio nome.** Não é
   "saldo". Segue a disciplina que o produto já usa em *desvio* e *indício*:
   nome que declara o que a coisa é. Proposta: **"saldo de desvio no período"**,
   sempre com o período explícito ao lado.
2. ~~**O saldo oficial é espelhado de `NBanco`**~~ — ⛔ **impossível, ver §1.**
   Fica no lugar a obrigação de **dizer que não existe**: onde o usuário
   esperaria o número da folha, a tela diz que o Secullum desta conta não opera
   banco de horas. Ausência declarada, nunca campo vazio — pela mesma razão que
   entidade que não escreve vira ausência e ausência não alarma.
3. **Onde os dois aparecerem juntos, a divergência é mostrada**, não escondida.
   Duas linhas e a diferença. Vale se e quando o oficial passar a existir.
4. **Nenhum alerta que implique obrigação sai do número calculado.** Alerta de
   desvio continua sendo sobre desvio. "Você tem X horas a compensar" só pode
   sair do oficial, se sair de algum lugar — e hoje não sai.
5. **Métrica do assistente:** entra a calculada em `app.metric`, com título que a
   distingue em português claro. O assistente jamais escolhe "o saldo" — ele
   escolhe um número nomeado, e a UI mostra qual escolheu, como já faz.

## 4. Justificativa — a completar com as palavras do owner

> ⚠️ **Campo aberto.** Esta seção precisa da razão do Rodrigo, escrita por ele.
> Sem isso o documento registra o *quê* e não o *porquê*, que é a metade que
> importa daqui a seis meses.

Candidatas levantadas em 28/08, e o que a medição de 02/09 fez com elas:

- **(a) `NBanco` não é confiável ou não vem preenchido** — ✅ **confirmada, e mais
  forte que o enunciado.** Não é falta de preenchimento: o instrumento inteiro
  está desconfigurado nesta conta (§1). A decisão é forçada pela origem.
- **(b) O escopo pede projeção** — continua possível e não foi medida. Se for
  também esta, o que se decidiu é *acrescentar*, e a forma da §3 é exatamente
  isso.
- **(c) O cliente quer o número do OperaX como o número de gestão** — continua
  aberta, e agora com menos margem: sem oficial ao lado, é o único número.

## 5. Riscos aceitos por esta decisão

1. **Um número sozinho é lido como *o* número.** Era "dois números para uma
   pergunta"; a §1 piorou para "um número sem contraponto". Mitigação: §3.1 e
   §3.2 — nome próprio e ausência declarada.
2. **Regra trabalhista dentro do produto.** Compensação, prazo, DSR e 12x36 são
   intrincados. Calcular é assumir essa intrincação — e errar nela tem custo
   fora do software.
3. ~~**Reversão de recomendação escrita.**~~ A §1 desfez isto: não houve reversão
   de julgamento, houve fato novo. A linha em `COBERTURA-ESCOPO.md` ganha
   ponteiro para cá e **não é apagada**.

## 6. Condições — não é decisão livre, é decisão com trava

Estas condições fazem parte da decisão. Implementar sem elas é implementar outra
coisa:

- ~~**Modo sombra**, comparando contra `NBanco` numa amostra validada~~ — ⛔ **a
  comparação perdeu o comparador** (§1). O modo sombra **continua**, mas contra
  o que o cliente reconhece como verdade: uma amostra de meses fechados que a
  FastPark confirme à mão. Sem contraparte, "explicar a divergência" vira
  "explicar o número", e é isso que passa a ser exigido antes de a tela existir.
- **Nenhum rótulo "saldo" solto** em tela, relatório, WhatsApp ou resposta do
  assistente. Verificável por varredura, como as verificações 12 e 13 da suíte.
- **As regras implementadas ficam escritas** — o que entra na conta, o que fica
  fora, e por quê. Cálculo trabalhista sem regra documentada é passivo.
- ~~**`NBanco` continua sendo ingerido**~~ — ele já é, e seguirá sendo: é coluna
  do espelho literal. O que muda é que ele **não é fonte de saldo**, e nenhum
  código deve tratá-lo como tal. A confusão custou o enquadramento deste
  documento uma vez; que não custe duas.

## 7. O que reverteria esta decisão

A reversão prevista era: se o calculado divergir do `NBanco` sem explicação
estável, volta-se a "só espelhar". ⛔ **Essa saída não existe mais** — não há
para onde voltar.

A saída que resta é outra, e é mais dura: se o número calculado não passar na
validação com o cliente (§6), ele **não aparece**. O produto entrega desvio e
indício, que já entrega, e o saldo fica fora do escopo até a origem oferecer um
oficial. Publicar um número que ninguém consegue explicar é dar precisão
aparente a um erro — e sem contraponto, ninguém o pegaria.

## 8. O passo imediato — EXECUTADO em 02/09/2026

> Enunciado: *"Antes de qualquer linha de código: contar, em produção, quantas
> `Batida` têm `NBanco` preenchido, e em quantos colaboradores distintos."*

Feito, por agregado, sem PII, pela Management API:

```
NBanco = true ............... 0 de 1.653 batidas · 0 colaboradores
Funcionario.BancoHorasId .... null nos 80 ativos
HorariosOpcoes.Compensacao .. null nas 94 escalas
Compensado = true ........... 1.379 de 1.653 (83%)  ← contraste
Neutro = true ...............   129
```

A pergunta foi respondida e ultrapassada: `NBanco` é `boolean not null`, uma
marca de dia, não minutos — então "quantas têm preenchido" não era a pergunta
certa. A certa era "existe saldo no espelho?", e a resposta é não.

**Próximo passo, agora:** perguntar à FastPark o que `Compensado` significa na
operação deles. É a única marca com volume, e é a pista de como a compensação
acontece sem banco de horas. ⛔ Não inferir: o que essa marca quer dizer não
está no banco.
