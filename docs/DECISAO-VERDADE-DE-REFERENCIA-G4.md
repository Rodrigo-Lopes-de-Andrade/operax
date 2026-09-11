# OperaX — decisão: a verdade de referência do G4

**Decisão:** o falso positivo do modo sombra passa a ser medido por **adjudicação
humana**, registrada em `app.deviation_adjudication`, e não mais contra "a
apuração do próprio Secullum". A `SPEC-TECNICA.md` §3.5 foi reescrita junto com
esta decisão — as duas mudam sempre juntas.
**Quem decidiu:** Rodrigo (owner), 09/09/2026.
**Alternativas recusadas:** sincronizar `POST /IntegracaoExterna/Calcular` para
obter o veredito da origem (§2 explica por que ele não responde à pergunta do
G4); e manter a §3.5 como estava, que é medir contra um conjunto que não existe.

---

## 1. O que estava escrito, e por que não era executável

A §3.5, passo 2, mandava comparar os indícios do OperaX com o que o Secullum
registrou: *"eventos que o OperaX viu e o Secullum não → candidato a falso
positivo"*.

**O espelho nunca traz o veredito do Secullum.** As 22 tabelas de `secullum` são
todas de entrada — `Batida`, `Funcionario`, `Horario`, `HorarioDia`,
`HorarioExtras`, tolerâncias, `FuncionarioAfastamento`, estrutura. Nenhuma
`Ocorrencia`, nenhuma `Inconsistencia`, nenhum cálculo. O produto espelha o que o
Secullum **lê**, nunca o que ele **conclui**. Um gate que compara com um conjunto
inexistente não reprova nem aprova: ele fica parado, que é onde o S6 esteve.

## 2. Por que buscar o veredito na origem também não resolve

A API pública documenta `POST /IntegracaoExterna/Calcular` e
`/Calcular/SomenteTotais`, com filtro `{funcionarioPis | funcionarioCpf,
dataInicial, dataFinal, centrosDeCustos[]}`. Ler o Swagger (09/09/2026) mostrou
duas coisas, e a segunda é a que decide:

1. **A resposta é indocumentada.** O `200` vem sem schema. O que ele devolve
   campo a campo, e se o plano desta conta o libera, só se descobre chamando — e
   chamar é um POST sobre o registro oficial do cliente, cujo efeito colateral
   ninguém mediu.
2. **O veredito seria função determinística do que já temos.** Medido em
   produção (`nklobmlxyidqxarzisph`), sobre 2.121 linhas de `secullum."Batida"`:

   | coluna de adjudicação da origem      | preenchida |
   |--------------------------------------|------------|
   | `"Ajuste"`                           | 1          |
   | `"Abono2"` / `"Abono3"` / `"Abono4"` | 0          |
   | `"Observacoes"`                      | 0          |
   | `status_dia_rotulo` (derivado por nós) | 80 (4%)  |

   Dos **326 dias-colaborador** que carregam os **820 indícios ativos em sombra**,
   **6** têm rótulo. O cliente praticamente não justifica dia no Secullum. Então o
   cálculo da origem parte das mesmas batidas, das mesmas escalas e das **mesmas
   tolerâncias** que o motor já lê (`backend/operax/motor/jornada.py` lê
   `HorarioDia."ToleranciaExtra"` e `."ToleranciaFalta"`).

**A prova disso são os seis supervisores.** Eles têm escala Seg–Sex 08:00–18:00,
não batem ponto, e não têm justificativa registrada. O Secullum apuraria falta
para eles exatamente como o OperaX emite `no_punches`. O veredito da origem
**concordaria** — e os indícios continuariam sendo ruído inútil para o gestor.
Concordância não é ausência de falso positivo.

📌 **O `Calcular` mede outra coisa, e essa coisa é valiosa.** Ele responde "o
OperaX calcula as mesmas horas que o registro oficial?" — um oráculo de
conformidade de implementação. Não responde "este indício merecia o tempo do
gestor?", que é o que a regra 8 protege. Fica como trabalho posterior à janela de
convergência, onde ele naturalmente mora (`supabase/functions/`), e não como
portão do G4.

## 3. Por que censo, e não amostra

A população é pequena o bastante para dispensar estatística: **820 indícios
ativos, todos em `mode='shadow'`, sobre 326 dias-colaborador e 67 pessoas**, em
11 tipos — mediana de 13 indícios por pessoa, máximo 20. O ruído é sistêmico e
espalhado, não concentrado em alguém.

Julgar tudo custa uma tarde de uma pessoa do DP com as batidas do dia na tela, e
elimina a discussão sobre intervalo de confiança que uma amostra traria junto.
Quando a base crescer a ponto de o censo não caber, amostragem estratificada por
tipo passa a ser a conversa — e aí ela será uma decisão com número na mão.

## 4. O que a decisão custa, e está declarado

⛔ **O falso negativo saiu do gate.** O passo 2 antigo também pedia "eventos que
o Secullum viu e o OperaX não". Sem veredito da origem esse conjunto não existe,
e adjudicação humana não o produz: quem lê o dia julga o que o OperaX **emitiu**,
não o que ele **deixou de emitir**. O G4 passa a medir falso positivo e só —
que é o que a regra 8 sempre disse (*"falso positivo ≤5%"*), mas a §3.5 pedia
mais e agora pede menos. Fechar o falso negativo exige uma verdade externa, e a
candidata continua sendo o `Calcular` do §2.

⚠️ **O julgamento é de quem julga.** Duas pessoas podem discordar sobre o mesmo
dia, e nada aqui mede isso. A mitigação é barata e não foi implementada porque
ninguém a pediu: julgar uma fatia em duplicata e comparar. Se a taxa ficar
perto do teto de 5%, isso deixa de ser opcional — uma diferença de julgamento
passa a decidir o gate.

## 5. Como fica na prática

```bash
python -m operax.motor.adjudicacao exportar --saida censo.xlsx
# a planilha vai para o DP, com dropdown de veredito e de causa
python -m operax.motor.adjudicacao importar --arquivo censo.xlsx --autor "Nome"
python -m operax.motor.adjudicacao medir
```

O vocabulário da causa são as três da §3.5 (`wrong_schedule`, `wrong_tolerance`,
`engine_bug`) mais duas que a medição de 09/09 tornou inevitáveis:
`exempt_from_punching` — a pessoa não bate ponto por função, que é a classe dos
seis supervisores — e `justified_outside_system`, o combinado que nunca chegou ao
Secullum e que o `"Ajuste"` preenchido **uma vez em 2.121 linhas** prevê.

📌 **`exempt_from_punching` existe para dar número a uma decisão pendente.**
Desligar um tipo por colaborador ou por escala mexe no grão de
`app.deviation_event`, que é parada obrigatória do `CLAUDE.md`. O censo mede o
tamanho da classe antes de a decisão ser tomada, em vez de depois.

**A medição carrega a cobertura, sempre.** `medir` recusa chamar de resultado do
gate uma taxa sobre censo parcial: 5% sobre os 40 casos que alguém julgou não diz
nada sobre os 820. Enquanto faltar veredito, ela imprime a taxa parcial marcada
como parcial e o gate responde "ainda não sei" — nunca "passou".

## 6. A liberação é um registro, não um deploy (11/09/2026)

Em 09/09 o motor foi promovido para o DP ver dado no painel, com o censo em
zero adjudicações — e o gate do sender, que perguntava só "existe execução em
produção?", abriu num deploy em vez de numa medição. O que impedia uma mensagem
de sair era não existir regra de alerta cadastrada.

Desde a migration 38 o sender exige **duas** coisas: motor promovido **e** uma
linha vigente em `app.alert_release`. A linha é gravada por

```bash
python -m operax.motor.adjudicacao liberar --autor "Nome" [--nota "..."]
python -m operax.motor.adjudicacao liberar --revogar --autor "Nome" --nota "por quê"
```

e o comando só grava depois de `medir` responder `PASSA` sobre censo completo.
O schema recusa o mesmo que o comando: taxa acima de 5% e censo parcial não
existem como liberação. `revoked_at` preenchido fecha a porta de novo — uma
trava que só fecha seria porta de mão única.

⚠️ **A §3.5 pede duas execuções seguidas; a liberação registra uma.** O comando
avisa. Exigir a segunda no schema seria modelar uma série de medições que hoje
não existe — fica como disciplina de quem libera, escrita na saída do comando.
