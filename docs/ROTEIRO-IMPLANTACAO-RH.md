# OperaX — roteiro de implantação da carga de RH

Uma página. É o que a EURECA executa no cliente, do zero até a aba Colaboradores
respondendo. A planilha real **não sai da máquina da implantação** e não circula
por chat, e-mail ou repositório.

---

## Antes de ir

| # | Precisa estar pronto | Como confere |
|---|---|---|
| 1 | Sync do Secullum rodou e o quadro está no sistema | a lista de Colaboradores abre com gente |
| 2 | Você tem login com papel `owner`, `hr` ou `personnel` **no tenant do cliente** | o menu mostra "Administração" |
| 3 | Os domínios sensíveis que a carga toca estão no seu usuário (`pii`, `compensation`, `health`) | as abas Dados pessoais, Remuneração e ASO aparecem num colaborador |
| 4 | O bucket `imports` existe no projeto Supabase do cliente, privado | `POST /rh/imports` não responde 503 |
| 5 | `cd backend && uv sync` roda na máquina da implantação | `python3 scripts/rh_carga_inicial.py --help` |

O passo 1 não é formalidade: o conversor casa a planilha com o cadastro **pela
matrícula**, e matrícula que o sync não trouxe vira descarte com motivo, não
pessoa nova. O OperaX nunca cria colaborador a partir de planilha.

---

## Passo a passo

**1. Baixe os quatro modelos.** Administração → Importação → escolha o tipo →
"Baixar modelo". Um arquivo por tipo, todos no mesmo diretório:

```
~/implantacao/modelos/
  modelo-hr_link.xlsx
  modelo-hr_employee.xlsx
  modelo-hr_exam.xlsx
  modelo-hr_compensation.xlsx
```

Eles já vêm com matrícula e nome impressos — é o quadro atual do cliente.

> **Se o cliente já tem ID RH gravado no sistema**, baixe `hr_employee` e
> `hr_compensation` **depois** de subir o vínculo (passo 4). O vínculo pode
> mudar o ID RH de alguém, e um modelo baixado antes disso imprime o ID antigo —
> que o import recusa, corretamente, com "ID RH não existe neste cliente". Numa
> implantação do zero, com ID RH vazio em todo mundo, os três podem ser baixados
> de uma vez.

**2. Rode o conversor.** Ele lê a planilha do cliente, preenche os modelos e
escreve o relatório. **Não abre conexão com o banco e não grava nada.**

```bash
python3 scripts/rh_carga_inicial.py \
    --planilha ~/implantacao/planilha-rh-do-cliente.xlsx \
    --modelos  ~/implantacao/modelos \
    --saida    ~/implantacao/saida
```

Saída esperada: as cinco contagens do balanço e a linha `relatório`. **Se o
comando terminar com erro dizendo que o balanço não fecha, pare** — há linha da
planilha que não terminou em lugar nenhum, e isso é bug do conversor, não do
cliente. Registre e escale.

**3. Leia o relatório antes de subir qualquer coisa.**
`saida/RELATORIO-DE-DESCARTE.md`, nesta ordem:

- **seção 6, descartes** — matrícula fora do quadro costuma ser gente desligada
  que continua na planilha. Confirme com o RH e siga.
- **seção 7, conferência do DESLIGADOS** — quem aparece aqui está desligado na
  planilha e **ativo no Secullum**. A correção é no Secullum, com o RH, e é
  melhor fazê-la antes da carga do que depois.
- **seção 9, células que não puderam ser lidas** — valor fora do catálogo, data
  ilegível, período de férias pela metade. Cada uma é uma pergunta para o RH.

**4. Suba os quatro arquivos, na ordem do nome.** Administração → Importação →
tipo correspondente → "Conferir sem gravar" → leia o preview → "Confirmar".

| Ordem | Arquivo | O que grava |
|---|---|---|
| 1º | `01-hr_link.xlsx` | o ID RH do cliente em `app.employee` |
| 2º | `02-hr_employee.xlsx` | regime e CTPS |
| 3º | `03-hr_exam.xlsx` | o ASO vigente: tipo, realização, validade e aptidão |
| 4º | `04-hr_compensation.xlsx` | a faixa salarial vigente |

O ASO é o que faz a coluna de próximos vencimentos responder. Ele carrega **um
exame por pessoa** — o mais recente; se a planilha do cliente guarda histórico na
mesma aba, os anteriores saem convertidos em `parqueado/occupational_exam.csv` e
o relatório diz quantos foram.

O preview mostra erro por linha **antes** de gravar, e linha que já está como o
banco aparece como "já estava assim" — reenviar não reescreve ninguém.

**5. Corrija na planilha, não no arquivo gerado.** Linha recusada no preview: o
conserto é no arquivo do cliente, e o conversor roda de novo. Editar o `.xlsx`
gerado à mão funciona, mas some no relatório — e o relatório é a ata.

**6. Confira na tela.** Abra Administração → Colaboradores e verifique três
coisas: a coluna de próximos vencimentos responde, um colaborador qualquer mostra
regime e CTPS no cadastro, e a aba Remuneração traz a faixa vigente com a data
certa.

**7. Entregue.**

- `RELATORIO-DE-DESCARTE.md` — anexo da ata, é a prova de que CID e dado
  bancário foram vistos e recusados;
- a pasta `saida/parqueado/` — afastamentos, férias, ASO, CNH, acordos e
  parcelas já convertidos, **guardados** até a tabela de destino ganhar caminho
  de escrita. Não jogue fora: é a conversão pronta.

---

## Quando dá errado

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `nenhum modelo .xlsx em ...` | passo 1 não foi feito, ou o diretório está errado | baixe os modelos |
| `dois modelos do tipo 'hr_link'` | sobrou modelo de outra rodada no diretório | limpe o diretório e baixe de novo |
| `Arquivo sem a aba de controle` | tem `.xlsx` que não é modelo no diretório | tire-o de lá |
| No upload: "gerado para outro cliente" | modelo de outro tenant | baixe logado no tenant certo |
| No upload: "baixe o modelo atual" | o layout mudou desde o download | baixe de novo e rode o conversor de novo |
| Muitas linhas com "matrícula fora do quadro ativo" | o sync não rodou, ou rodou em outro ambiente | volte ao pré-requisito 1 |

---

## O que este roteiro não faz

- **Não cria colaborador.** Quem cria é o sync. A planilha completa quem já
  existe.
- **Não altera o que é do sync** — nome, admissão, unidade, status. Se a
  planilha discorda do Secullum, quem está certo é o Secullum, e a divergência
  vai para o relatório.
- **Não carrega documento, afastamento, movimentação nem acordo.** Os quatro
  estão convertidos e parqueados: `app.document` e `app.financial_agreement`
  exigem o arquivo que uma planilha não tem, e `app.leave_period` e
  `app.workforce_movement` ainda não concedem escrita ao painel. O relatório diz,
  destino por destino, o que falta.
- **Não substitui a conversa com o RH.** As seções 6, 7 e 9 do relatório são
  pauta de reunião, não log.
