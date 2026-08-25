# Prompt da etapa RH — para a sessão do Claude Code em andamento

> **Como usar:** cole como mensagem na sessão do Claude Code que já está
> trabalhando no repositório. Não é um kickoff — é a próxima etapa entrando na
> fila. Cole inteiro, do `---` em diante.

---

Nova etapa: **RH — upload por template, telas de edição e carga inicial.** O
projeto que você já conhece continua valendo; isto entra por cima, sem tocar em
motor, alertas ou folha.

## Leia antes de escrever qualquer código

Nesta ordem, e trate como fonte da verdade nesta sequência:

1. `docs/DECISAO-RH-UPLOAD-TELAS.md` — as decisões e os porquês.
2. `docs/SPEC-RH.md` — o como: migration 16, template, pipeline, matriz
   dono-do-campo, endpoints, testes.
3. `docs/PRD-RH.md` — escopo, regras de produto da etapa, critérios de sucesso.
4. `docs/SPRINTS-RH.md` — a ordem de execução com os gates.

Em conflito entre eles e qualquer documento mais antigo (SPEC geral, PRD geral),
**estes quatro prevalecem para esta etapa**. O `CLAUDE.md` prevalece sobre
todos, como sempre.

## A ordem é R1 → R2 → R3 → R4, com gate entre cada um

Não avance de sprint com gate vermelho. Resumo do que cada um entrega:

- **R1** — migration 16 (`hr_code` + tipos de import), matriz dono-do-campo em
  `operax/rh/ownership.py`, validadores puros em `operax/rh/validators.py`,
  fixture sintética. Gate: `make db-test` + pytest dos seis casos de erro.
- **R2** — gerador de template pré-preenchido (aba `_meta`, colunas bloqueadas,
  dropdowns), preview sem gravação, confirmação parcial, template de vínculo.
  Gate: E2E de API com erro simulado e reimport.
- **R3** — aba **Colaboradores** na Administração (lista + detalhe por domínio,
  proveniência por campo, vigências como linha do tempo). Gate: Playwright
  cobrindo papel e domínio.
- **R4** — conversor de implantação + relatório de descarte + ensaio da carga
  com fixture. Gate: 100% das linhas com destino ou descarte justificado.

## Regras desta etapa que não se negociam

1. **Um funil só.** O validador do formulário e o do import são a MESMA função
   por domínio. Se você se pegar escrevendo a mesma regra duas vezes, pare — o
   desenho está errado.
2. **Escrita só pelo caminho 2.** Nenhum grant de escrita novo para o painel;
   toda rota `/rh` revalida papel e domínio; toda gravação em `audit_log`.
   Nenhuma rota DELETE — encerrar, revogar, inativar.
3. **Chaves divergentes são erro de linha**, com os dois nomes na mensagem —
   nunca escolha silenciosa entre matrícula e `hr_code`.
4. **Campo do sync é intocável** pelo RH: bloqueado no template, somente-leitura
   na tela com "Secullum · leitura de HH:MM", e linha que o altere falha no
   preview.
5. **CID e diagnóstico não existem** nesta etapa: sem coluna, sem campo, sem
   tabela. Conta/agência/banco ficam fora do escopo.
6. **Vigência, não edição**, para salário e cargo. Corrigir = revogar + criar.
7. **Dado real nunca entra em teste.** Fixtures são sintéticas; a planilha do
   cliente só é lida pelo conversor, na implantação, fora do repositório.

## Pare e pergunte (não decida sozinho)

- Os **três campos pendentes da matriz** (supervisor, unidade de atuação, data
  de demissão antecipada): trate como sync até decisão do Rodrigo. Se alguma
  tarefa depender deles, pergunte.
- Qualquer coisa que pareça exigir policy de RLS nova, tabela em `public` ou
  mudança no grão de `app.deviation_event` — as três paradas de sempre.
- Se o handoff da rodada 7 do design não tiver chegado quando R3 começar:
  construa a versão funcional com os componentes existentes (`COMPONENTES.md`)
  e siga; o refinamento visual entra depois. Não bloqueie, não invente
  componente novo.

## Definição de pronto da etapa

`make test && make lint && make db-test` verdes; os quatro gates cumpridos; e a
demonstração final: planilha de fixture → conversor → templates → preview →
confirmação → aba Colaboradores respondendo "o que vence nos próximos 30 dias?"
sem planilha auxiliar.
