# OperaX — PRD da etapa DP (rotinas, conformidade e painel)

**Etapa:** o que o sistema legado FastPark faz e a documentação atual não cobre.
**Contexto:** complementa `PRD-OPERAX.md` e `PRD-RH.md`. O levantamento está em
`ANEXO-COBERTURA-LEGADO-FASTPARK.md`; as duas decisões de escopo que abriram esta
etapa foram tomadas pelo owner em 28/08/2026 e estão em §2.

---

## 1. O problema

A etapa de RH parte de uma premissa que as telas do cliente desmentiram: o que
vai ser aposentado não é uma planilha, é um **aplicativo em operação**. Ele tem
cadastro — e o cadastro a etapa de RH cobre — mas tem também três coisas que
nenhum documento do projeto previa:

1. **Rotinas mensais que geram dinheiro.** Cesta básica e vale transporte não são
   telas de consulta: apuram direito, contam faltas, agrupam por unidade e
   produzem o pedido ao fornecedor e o arquivo de remessa ao banco.
2. **Conformidade por unidade.** PCMSO, PGR e LTCAT+LTIP com vencimento,
   situação e renovação com histórico. Não é dado de pessoa; é do local.
3. **Um painel com fórmula própria.** "Folha salarial base" tem uma definição
   escrita na tela — `salário + ajuda de custo + cargo de confiança +
   periculosidade`, só ativos — e o cliente confere por ela todo mês.

Enquanto essas três faltarem, a substituição não acontece: o cliente mantém o
legado aberto para fechar a competência, e o OperaX vira uma segunda tela.

E há um custo silencioso: **o modelo atual não consegue calcular a folha base.**
`app.employee_compensation` guarda `salary` e nada mais — ajuda de custo, VR,
cesta, VT, cargo de confiança e periculosidade não têm onde morar. O número que
o cliente usa para reconhecer o próprio custo de pessoal é, hoje, incalculável.

## 2. Duas decisões de escopo (owner, 28/08/2026)

**Conta bancária entra, como domínio sensível novo.** `PRD-RH.md` §4 e
`DECISAO-RH-UPLOAD-TELAS.md` §8 a deixaram fora da v1. A rotina de VT depende
dela — o relatório tem coluna `CONTA` e o botão é *Exportar arquivo banco*. A
decisão é **A** das três alternativas registradas no anexo: conta entra como o
quarto eixo de sensibilidade (`banking`), com permissão própria, campo mascarado
na tela e o arquivo de remessa montado no backend, sem que o número da conta
passe pelo navegador. As outras duas alternativas (VT sem conta; VT adiado)
ficam registradas como recusadas, não como esquecidas.

**Laudos por unidade entram nesta etapa.** É entidade pequena e o padrão já
existe no projeto: vencimento, alerta e renovação com histórico são os mesmos do
ASO, e `app.document` já tem `replaces_id` para substituição versionada. Vive no
módulo de Unidades, não na aba Colaboradores.

## 3. O que esta etapa entrega

| # | Entrega | Por que existe |
|---|---|---|
| 1 | **Domínio `banking`** | destrava a remessa do VT sem afrouxar o modelo |
| 2 | **Quadro de Postos** | fonte de escala que o VT já usa em produção — e que o motor de detecção hoje infere |
| 3 | **Catálogo de benefícios com vigência** | um reajuste de tarifa muda 69 pessoas de uma vez; hoje seriam 69 edições |
| 4 | **Pacote de remuneração por vigência** | sem ele a folha base não fecha |
| 5 | **Ciclo mensal de benefício** (cesta + VT) | a rotina que mantém o legado vivo |
| 6 | **Laudos por unidade** | conformidade com vencimento e renovação |
| 7 | **Painel de DP** | os 9 KPIs, os 8 alertas e o consolidado por empresa |
| 8 | **Mapa de rubrica → categoria** | semeado do legado, não de reunião |
| 9 | **Movimentação como período** | a unidade de atuação passa a ser derivada, como no legado |

## 4. Quem usa

- **DP (`personnel`)** — roda as rotinas mensais, fecha o pedido de cesta e a
  remessa do VT, mantém o cadastro. É quem ganha o domínio `banking`.
- **RH (`hr`)** — documentos, ASO, afastamentos. **Não** ganha `banking`: quem
  cuida de saúde não precisa de conta bancária, e o inverso também vale.
- **Contabilidade (`accounting`)** — confere folha e consolidado; ganha
  `banking` porque a conciliação da remessa é dela.
- **Segurança do trabalho / gestor de unidade** — consulta laudos da sua
  unidade. Sem domínio sensível nenhum.
- **Gestores de unidade e regional** — o painel, no recorte que o escopo permite.

## 5. Escopo

### Entra

Os nove itens da tabela em §3, mais os campos cadastrais que o legado tem e o
modelo não: cód. de posto, escala, carga horária, jornada, nível, estado civil,
raça/cor, grau de instrução, PCD, triênios, dependentes (quantidade e nomes),
tipo e valor de VT, data limite de férias e período aquisitivo.

Mais dois templates de mensagem, sob a regra 11: **parabéns de aniversário** e
**solicitação de renovação de CNH** — os dois botões que o painel do legado
dispara hoje.

### Não entra (decidido, não esquecido)

- ~~**Foto do colaborador.**~~ **DESTRAVADO em 04/09/2026.** Este item saiu por
  padrão com a condição escrita "fica de fora até o cliente pedir". O cliente
  pediu. A foto **entra**, pelo Caminho 2 e sob o domínio `pii` — nunca em view
  de `public`, nunca em lista, nunca em exportação, nunca em log. Ver
  `DECISAO-FOTO-DO-COLABORADOR.md`.
- **Nome de colaborador com parcela em aberto no painel inicial.** O legado
  nomeia na home; o OperaX mostra contagem por unidade, e o nome exige o domínio
  `compensation`. Decisão registrada em §7.
- **Módulos Comercial, Financeiro e Unidades do legado** — não foram vistos.
  `Unidades` é a próxima leitura, porque é onde deve estar o Quadro de Postos
  como o cliente o mantém hoje.
- **Delete físico.** Excluir cadastro, excluir movimentação e limpar histórico
  existem no legado e não existirão aqui. Regra 6 estendida.
- **Diagnóstico, CID, restrição.** Regra 10, sem exceção. As 16 telas do legado
  não mostram nenhum — a regra segue compatível com a operação real.
- **Registro ou edição de ponto** — nunca, em etapa nenhuma.

## 6. Regras de produto desta etapa

Continuam a numeração do projeto e valem como as demais:

7. **A rotina é a entrega, não a tela.** Cesta e VT só substituem o legado se
   produzirem o pedido e a remessa. Tela que mostra o número sem gerar o arquivo
   não fecha a competência.
8. **O que compõe a folha base é dado, não código.** Cada tipo de benefício
   declara se entra na base (`composes_base`). A fórmula do painel é uma soma
   filtrada por esse campo — auditável e conferível, nunca constante no backend.
9. **Ciclo fechado não muda.** Gerado o ciclo do mês, ele vira registro
   histórico: correção é novo ciclo, com motivo. O pedido que foi ao fornecedor
   precisa continuar reproduzível seis meses depois.
10. **Conta bancária nunca chega ao navegador.** A tela mostra máscara; o
    arquivo de remessa é montado e assinado no backend. O front nunca recebe o
    número completo, nem para exibir.
11. **Renovação é registro novo.** Laudo, ASO e documento renovam criando linha
    que aponta para a anterior. Nunca `update` na data de vencimento.

## 7. Critérios de sucesso

- **A folha base bate na vírgula.** No dia da virada, o consolidado do OperaX e o
  card do legado dão o mesmo número para a mesma base. É asserção automatizada,
  não conferência visual — e é o critério que o cliente vai usar, tenha ele sido
  combinado ou não.
- **A competência fecha dentro do OperaX**: o DP gera o pedido de cesta e a
  remessa de VT sem abrir o legado, por dois meses seguidos.
- **Zero conta bancária no payload do frontend** — verificado por teste, não por
  revisão de código.
- **Nenhum papel sem `banking` alcança conta**, e nenhum papel sem
  `compensation` alcança valor de acordo — as duas cobertas por asserção na
  suíte de isolamento.
- Todo laudo vencido aparece no alerta da unidade no dia seguinte ao vencimento,
  sem ninguém consultar nada.

## 8. Fora de risco (o que esta etapa não pode quebrar)

O motor de detecção, os alertas de jornada e a sincronização não são tocados. A
superfície pública do banco não ganha tabela (regra 1). As três paradas
obrigatórias continuam valendo — e esta etapa **encosta em duas delas de
propósito**: cria policy de RLS nova (domínio `banking`, laudos, ciclos) e expõe
coluna nova em view pública (os KPIs do painel). Ambas param e perguntam antes
de aplicar, mesmo estando previstas aqui. Previsto não é autorizado.
