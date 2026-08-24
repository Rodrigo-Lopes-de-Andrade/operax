# Anexo ao relatório de auditoria — contexto que o auditor não tinha

O relatório principal foi produzido por um agente com contexto limpo, lendo só os
12 documentos. Este anexo acrescenta o que vem do histórico da sessão de trabalho
— proveniência das divergências e correções que já existem prontas — e registra
uma regra de precedência nova, decidida hoje.

---

## 1. A origem da deriva: dois repositórios evoluíram em paralelo

O repositório em andamento no Claude Code partiu de um pacote **anterior** às
últimas sincronizações de documentação desta sessão. Resultado: cada lado tem
verdades que o outro não tem.

**Já corrigido na sessão, nunca chegou ao repo em andamento** (explica A3, A10,
A26 e parte de A6):

- SPEC §Provedor reescrita para **template-first, três provedores** (a versão
  em andamento ainda diz Evolution API + `enviarWhatsApp(destino, payload)`).
- Contagens sincronizadas: 15 migrations, 24 asserções de alerta/cadência/
  provedor, 13 verificações estruturais (em andamento: 14/11/34).
- Rótulos de `app.metric` sem resíduo pt→en, com verificações 12 e 13 na suíte.

**Só existe no repo em andamento, e é mais novo que a sessão** (o auditor está
certo em tratá-lo como fonte primária): PLANO-RECONCILIACAO-NUVEM inteiro —
Edge Functions como sincronização real, cadência de batidas 15 min, migration
11b de rename, staging, riscos §4b. **Nenhum documento da sessão conhecia isso.**

Consequência prática: a "passada de baixa" que o veredito pede não parte do
zero — parte das edições já prontas do lado da sessão, aplicadas sobre o repo
em andamento, que é o canônico daqui em diante.

## 2. Achados que têm resposta pronta, não investigação

- **A15 (rebrand sem decisão registrada).** A decisão **existe e está
  documentada** — manual de marca FastPark analisado, white-label decidido,
  tokens validados em contraste — em `PROMPT-CLAUDE-DESIGN-R6-FASTPARK.md` e na
  anotação de white-label do `CLAUDE.md` da sessão. Esses arquivos não estão no
  conjunto auditado porque nunca entraram no repo em andamento. A correção é
  copiar o documento de decisão, não escrever um novo.
- **A22 (correção do login sem registro).** A correção **foi feita e verificada
  empiricamente** no pacote da rodada 5: a tela passou a mostrar "Você abriu um
  link de ocorrência. Entre para vê-la", com zero dado de colaborador
  pré-autenticação (medido no protótipo renderizado). O que falta é o registro —
  uma AVALIACAO-DESIGN-R5 curta de uma página, que nunca foi escrita porque a
  verificação aconteceu em conversa.
- **A16 (8 vs 9 métricas).** As 9 estão certas; a COBERTURA é anterior à
  migration 12, que registrou `data_freshness` no catálogo.
- **A11 (migration 14 vs 15 do WhatsApp).** Os dois lados numeram certo nos
  seus contextos: o arquivo é o 15º (índice `_14_`, contagem a partir de 00). A
  baixa deve padronizar a referência por **nome de arquivo**, nunca por ordinal.

## 3. Regra de precedência registrada hoje (decisão do Rodrigo, 24/08)

> **Para a fase de RH, a documentação específica de RH é a fonte da verdade.**
> A conciliação dela com a documentação geral vem depois da baixa desta
> auditoria — e, no que conflitar dentro do escopo de RH, os documentos de RH
> prevalecem.

Documentos dessa fase (existem no pacote da sessão; **ausentes do repo em
andamento**): `PRD-RH.md`, `SPEC-RH.md`, `SPRINTS-RH.md`,
`PROMPT-CLAUDE-CODE-RH.md`, `DECISAO-RH-UPLOAD-TELAS.md`.

Dois pontos que a conciliação vai ter que tratar, anotados desde já:

1. **Numeração de migration.** SPEC-RH chama de "migration 16" a que cria
   `hr_code` e os tipos de import. No repo em andamento a linha do tempo tem
   11b (rename) e um `_15_rebrand_fastpark` que a sessão não conhecia — o
   número real será outro. Referenciar por nome de arquivo, conforme A11.
2. **Caminho de escrita.** SPEC-RH assume escrita via FastAPI (caminho 2). A
   sincronização migrou para Edge Functions, mas a API do painel segue FastAPI
   na SPEC geral — a conciliação só precisa confirmar que isso continua de pé.

## 4. Ordem recomendada, juntando auditoria + contexto

1. **Passada de baixa dos 9 ALTA no repo em andamento** — A1/A2 (PLANO-BANCO é
   o documento mais defasado do conjunto: ou ganha aviso de "superado pela
   reconciliação" no topo, ou a baixa o reescreve), A4 (decidir e registrar:
   15 ou 30 min — hoje a produção pratica 15 sem decisão escrita), A5 (o
   conflito 7 dias × 2 dias é decisão de produto, não redação), A6/A7 (SQL
   copiável corrigido para os valores do schema), A8 (dicionário regenerado
   contra produção + cursor no baseline), A9 (riscos §4b viram entregas com
   dono no plano).
2. **Entrada dos documentos de decisão ausentes** — FastPark (fecha A15),
   AVALIACAO-DESIGN-R5 (fecha A22), e o conjunto de RH.
3. **Conciliação RH × geral**, com a regra de precedência acima.

As três decisões de produto que a auditoria confirma abertas continuam sendo do
Rodrigo: saldo de horas, mapa código de evento → categoria de folha, formato de
exportação. E a A4 acrescentou uma quarta: **a cadência oficial de batidas**.
