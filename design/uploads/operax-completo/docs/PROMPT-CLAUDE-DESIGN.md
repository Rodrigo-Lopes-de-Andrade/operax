# Prompts para o Claude Design — OperaX

O Claude Design trabalha em duas colunas: conversa à esquerda, canvas ao vivo à
direita. Ele aceita texto, imagem, DOCX/PPTX/XLSX, repositório de código e
captura de site. A saída é arquivo comum, handoff para o Canva e — o que
interessa aqui — **pacote de handoff para o Claude Code**. Ele não exporta Figma
nem gera React direto.

A limitação que mais importa: **sem design system publicado, a saída fica
funcional e genérica**. Por isso o passo 0 não é opcional.

---

## Passo 0 — antes de escrever qualquer prompt

Suba no projeto, nesta ordem:

1. **Os assets da EURECA** — `styles.css`, a pasta `components/`, os specimens de
   `guidelines/`. É o que separa "bonito e genérico" de "parece nosso".
2. **`docs/PRD-OPERAX.md`** — dá o vocabulário e as regras de produto.
3. **`docs/DICIONARIO-DE-DADOS.md`** — os nomes reais de campo, para os rótulos
   não serem inventados.
4. **O repositório**, se der para conectar. Ele lê a marca do código.

Se os assets não subirem, cole os tokens abaixo no prompt de contexto — mas
sabendo que é o plano B.

---

## Prompt 1 — contexto do projeto

> Cole uma vez, ao criar o projeto. Os prompts de tela herdam este contexto.

---

Você vai desenhar o **OperaX**: uma plataforma de gestão de ponto, pessoas e
custo de pessoal. Ela lê o sistema de ponto de uma rede de estacionamentos,
detecta desvio de jornada, avisa o gestor no mesmo dia e consolida custo de
folha. Cliente âncora: Kastro Park. Fornecedor: EURECA.

**Público.** Não é um produto de consumo. Quem usa passa o dia dentro dele:
departamento pessoal fechando o mês, gestor de unidade agindo sobre ocorrência,
diretoria olhando custo. Densidade de informação é qualidade, não defeito. A
comparação certa é Linear ou Datadog, não uma landing page.

**Idioma.** Toda a interface em português do Brasil. Voz técnica e direta.

### Marca — EURECA

- Base roxo profundo `#0E0918`. Acento rosa `#EA4B71`. Secundárias em lilás e cinza.
- Display: **Orbitron** (substituto de Korataki/Nulshock). Corpo: **Inter**.
- Título display em **CAIXA ALTA com tracking**, mesclando tipografia cheia
  (solid) e vazada (outline) na mesma linha — é a assinatura da marca, use.
- Ícones: **Lucide**, line-art.
- **Sem emoji**, em nenhuma superfície.
- Tema escuro é o padrão. Desenhe claro só se eu pedir.

### Sete regras de produto que mudam o desenho

Não são preferências. Cada uma nasceu de uma decisão de risco.

1. **O dado tem até 30 minutos de atraso.** A sincronização roda a cada meia
   hora. Toda tela que mostra o dia corrente exibe a idade do dado de forma
   permanente e legível — não escondida num tooltip. Sem isso, o gestor olha às
   09:05 um retrato das 08:40 e conclui que ninguém atrasou.

2. **Nunca escreva "hora extra".** O vocabulário é **desvio** e **indício**. O
   registro oficial é o outro sistema; o OperaX aponta, não apura. Todo
   detalhamento termina num caminho de "conferir no Secullum".

3. **Alerta mostra horário observado, nunca "agora".** "Entrada registrada às
   08:12, prevista 08:00" — não "Fulano está atrasado". A mensagem pode chegar
   40 minutos depois do fato.

4. **Minutos de desvio têm sinal.** Positivo é excedente (trabalhou além),
   negativo é faltante. Cor codifica **direção**, não magnitude. Não use
   vermelho para tudo que é desvio: faltante e excedente são coisas diferentes e
   nem todo excedente é problema.

5. **Papel muda o que existe na tela, não só o que está desabilitado.**
   Supervisor de unidade não vê salário, RG nem exame ocupacional — esses blocos
   **não aparecem**, não aparecem cinzas. Desenhe a variante por papel.

6. **Escala não confirmada é um estado de primeira classe.** Quando a jornada
   esperada foi inferida com baixa confiança, o número aparece com marcação de
   "escala não confirmada" e não dispara alerta. Precisa de um selo discreto e
   legível, repetível em tabela e em card.

7. **Estado vazio, de erro e de dado velho são o caminho principal.** O produto
   inteiro existe para responder "algo deu errado hoje?". Um dia sem ocorrência
   é sucesso e merece um estado desenhado, não uma tabela vazia.

### Dados de exemplo

Use nomes de unidade plausíveis (Centro, Shopping Norte, Aeroporto, Rodoviária,
Hospital) e nomes de pessoa **obviamente fictícios**. **Nunca gere CPF, RG ou PIS
com aparência real**, nem em mock. Ordens de grandeza: 6 unidades, ~180
colaboradores, 20 a 60 ocorrências por dia, desvios entre 5 e 90 minutos.

Comece pela tela que eu pedir a seguir. Antes de desenhar, me diga em três linhas
qual hierarquia visual você vai usar e por quê.

---

## Prompt 2 — Dashboard de gestão de ponto

**Objetivo.** Em cinco segundos o gestor responde: o dia está normal? Se não,
onde? Carrega em menos de 3 segundos.

**Público.** DP e gestor regional, várias vezes por dia, em monitor amplo.

**Conteúdo.**

- Barra de filtro persistente: empresa → unidade → departamento → gestor →
  período (atalhos: hoje, 7 dias, 30 dias, mês atual, intervalo livre). Filtros
  ativos viram chips removíveis. **O estado vive na URL** — o link chega por
  WhatsApp já filtrado, então a barra tem que comunicar "você está vendo um
  recorte" logo de cara.
- Indicador de atualização do dado, permanente.
- Linha de KPI: colaboradores ativos · presentes hoje · ausentes · em férias ·
  afastados · com ocorrência pendente de justificativa · saldo consolidado.
- Total de desvios e minutos acumulados, com proporção excedente × faltante.
- Tendência diária no período.
- Três rankings lado a lado: por unidade, por colaborador, por gestor.
- Recorrência: quem teve desvio em 3 ou mais dias na janela.
- Tabela de ocorrências com drill-down.

**Peça atenção especial a:** como a linha de KPI não vira uma parede de doze
números iguais. Hierarquize — nem todo indicador tem o mesmo peso num dia normal.

---

## Prompt 3 — Monitor diário da jornada

**Objetivo.** Tela de plantão. O gestor deixa aberta e age no momento em que a
ocorrência aparece.

**Público.** Supervisor de unidade, no desktop, ao lado de outras tarefas.

**Conteúdo.** Uma linha por colaborador previsto para hoje: entrada registrada ·
situação atual da jornada · início e fim do intervalo · tempo de atraso · tempo
excedente de intervalo · marcação incompleta. Agrupado por unidade, com resumo de
presença por grupo.

Estados por linha: dentro do previsto · atrasado · em intervalo · intervalo
estourado · não retornou · sem marcação · escala não confirmada.

**Peça atenção especial a:** o indicador de idade do dado é o elemento mais
importante desta tela. E como a lista se comporta quando 90% está normal — o
olho tem que cair no que não está, sem varrer.

---

## Prompt 4 — Consulta individual do colaborador

**Objetivo.** Reunir num lugar tudo que se sabe sobre a jornada de uma pessoa,
para conversa de gestão ou fechamento do mês.

**Público.** DP e RH. **Desenhe duas variantes:** com e sem permissão para dado
sensível.

**Conteúdo.** Cabeçalho com nome, cargo, unidade, departamento, gestor, jornada
contratada, data de admissão. Seletor de período. Indicadores consolidados.
Histórico de marcações. Histórico por tipo de desvio. Justificativas
apresentadas. Saldo de horas.

Na variante com permissão, e **só nela**: histórico de remuneração, documentos e
vencimentos, exames ocupacionais.

**Peça atenção especial a:** a variante restrita não pode parecer quebrada nem
mostrar cadeados. Ela é uma tela completa que simplesmente tem menos seções.

---

## Prompt 5 — Assistente de IA

**Objetivo.** Perguntar em português e receber número confiável.

**Conteúdo.** Conversa com streaming token a token. Perguntas de exemplo como
ponto de partida. **Cada resposta declara qual métrica foi usada e quais filtros
e período foram aplicados** — o usuário confere de onde veio o número.

Desenhe também o estado de **recusa**: pergunta fora do catálogo recebe "não
tenho esse dado", com sugestão do que dá para perguntar. Recusa é resposta
válida, não erro — não desenhe como falha.

**Peça atenção especial a:** como a resposta em texto convive com um número ou
gráfico, sem virar dois produtos empilhados.

---

## Prompt 6 — Importação do relatório de folha

**Objetivo.** A contabilidade manda uma planilha por mês e a pessoa do DP sobe
sem medo de estragar o histórico.

**Conteúdo.** Quatro passos: escolher competência · subir arquivo · **preview com
validação** · confirmar. O preview mostra quantas linhas foram lidas, quantas
passaram e **o erro por linha, com o número da linha e o motivo**. Duplicidade
detectada aparece antes de confirmar, não depois. Histórico de importações com
quem enviou e quando. Link para baixar o modelo padronizado.

**Peça atenção especial a:** o estado de erro parcial — 340 linhas boas e 12 com
problema. O que a pessoa faz? Essa é a tela.

---

## Prompt 7 — Configuração de regras de alerta

**Objetivo.** Configurar quem recebe o quê, sem criar risco trabalhista.

**Conteúdo.** Lista de regras com estado ligado/desligado. **Toda regra nasce
desligada** e o desenho tem que deixar isso óbvio. Editor: tipo de ocorrência ·
limiar · janela · canal · conteúdo (individual ou agregado) · destinatários.

**A regra de ouro:** alerta de conteúdo **individual** não pode ter grupo como
destino — expor nome de colaborador em grupo é risco trabalhista. O banco
recusa; a interface tem que explicar **antes**, não depois do erro.

**Peça atenção especial a:** como comunicar essa restrição no momento da escolha,
sem parecer punição.

---

## Prompt 8 — Dashboard de folha e custo

**Objetivo.** Diretoria enxerga custo de pessoal por período e por unidade.

**Conteúdo.** Valor total da folha · evolução mensal · custo por empresa, unidade
e departamento · custo médio por colaborador · encargos · admissões e
desligamentos · comparação entre períodos · variação percentual · desvio contra a
média histórica.

**Peça atenção especial a:** é a tela mais sensível do produto. Deve parecer
sóbria, não vistosa. E desenhe o estado "competência ainda não importada".

---

## Prompt 9 — Painel de TV

**Objetivo.** Monitor na parede do escritório, lido a 4 metros de distância.

**Conteúdo.** **Somente agregado. Nenhum nome de colaborador, em hipótese
alguma** — é tela de acesso coletivo. Situação por unidade, ocorrências do dia,
evolução, alertas prioritários, hora da última atualização em destaque.

**Peça atenção especial a:** tamanho mínimo de fonte para 4 metros, contraste em
sala clara, e rotação automática se não couber tudo.

---

## Prompt 10 — Administração

**Objetivo.** Onde a implantação acontece.

**Conteúdo.** Cadastro de unidades · **mapeamento origem → unidade, com marcação
de "não validado"** · usuários, papéis e escopo · integrações e estado de
sincronização · trilha de auditoria.

**Peça atenção especial a:** a tela de mapeamento. É onde ~26% dos colaboradores
começam com vínculo ambíguo, e a curadoria é feita aqui uma vez. Desenhe para
resolver 200 itens em uma sessão, não 5.

---

## O que NÃO desenhar

Portal do colaborador · app móvel · recrutamento e seleção · assinatura
eletrônica · folha de pagamento · qualquer tela que registre ou edite ponto. O
OperaX **lê** o ponto; quem registra é o Secullum.

---

## Ao terminar

Use o **handoff para o Claude Code** e me devolva o pacote. Do lado de cá já
existem o design system implementado, o schema com as views e RPCs que alimentam
cada tela, e o `CLAUDE.md` com as regras de arquitetura — o handoff entra nesse
repositório, não num projeto novo.
