# OperaX — PRD v1

**Produto:** camada de gestão, automação e inteligência sobre sistemas de ponto.
**Cliente âncora:** Kastro Park (primeiro tenant).
**Fornecedor:** EURECA — Processos · IA · Analytics.
**Status:** v1 em construção. Documento vivo.

---

## 1. O que é o OperaX

Empresas com operação distribuída em várias unidades já têm um sistema de ponto
que registra corretamente as marcações. O problema não é o registro — é que o
dado fica preso lá dentro. Para saber quem atrasou, qual unidade estourou hora
extra ou quanto isso custou, alguém precisa abrir o sistema, exportar, cruzar em
planilha e interpretar. Isso acontece uma vez por mês, no fechamento, quando já
é tarde para agir.

O OperaX lê o sistema de ponto, detecta desvio, consolida por unidade e gestor,
avisa o responsável no dia em que acontece e mantém o histórico. **Não substitui
o sistema de ponto e não é folha de pagamento** — o registro oficial continua
onde está. O OperaX é a camada que transforma esse registro em ação.

### Posicionamento em uma frase

> Seu sistema de ponto registra. O OperaX faz alguém agir.

### Por que isso é um produto e não um projeto

O problema é idêntico em qualquer operação com múltiplas unidades e mão de obra
em escala: rede de estacionamento, franquia, portaria, limpeza, varejo, logística.
O sistema de ponto varia; a dor não. Por isso o produto nasce multi-tenant, com
a integração desenhada como **conector plugável** — Secullum é o primeiro, não o
único.

---

## 2. Problema

Levantado na Kastro Park, mas genérico o suficiente para servir de teste em
qualquer prospect:

- Conferência e fechamento do ponto levam cerca de uma semana por mês.
- Alto volume de ajustes e justificativas, todos tratados manualmente.
- Esquecimento de marcação, atraso e divergência de jornada só aparecem no
  fechamento — quando não dá mais para corrigir o comportamento.
- Não há visão consolidada de hora extra, hora faltante e o custo disso.
- Informação de RH espalhada entre sistema de ponto, sistema contábil e planilhas.
- Sem histórico centralizado de salário, documento, exame ocupacional e ocorrência.
- Gerar qualquer relatório depende de uma pessoa específica.
- Nenhum controle de quem enxerga o quê por unidade, gestor ou nível de acesso.

### Quem sente

| Papel | Dor principal | O que o OperaX entrega |
|---|---|---|
| Departamento pessoal | Semana perdida na conferência mensal | Pendências visíveis todo dia, fechamento sem surpresa |
| Gestor de unidade | Descobre o problema tarde demais | Alerta no dia, com nome, horário e divergência |
| Diretoria | Não enxerga custo por unidade | Comparativo entre unidades e evolução no tempo |
| Contabilidade | Recebe dado inconsistente | Divergência entre ponto e folha sinalizada antes do fechamento |
| RH | Documento e exame vencem sem aviso | Alerta de vencimento com antecedência configurável |

---

## 3. Princípios de produto

Decisões já tomadas que não se renegociam por conveniência de implementação.
São o que separa o OperaX de um dashboard bonito com risco jurídico embutido.

**1. O sistema de ponto é a verdade.**
O OperaX detecta indício, não apura obrigação trabalhista. No banco e na tela o
vocabulário é *desvio* e *indício* — nunca "hora extra" como figura legal. Todo
drill-down termina em "conferir no sistema de ponto". Se o número do OperaX
divergir do oficial e um gestor agir em cima, a exposição é do fornecedor.

**2. Exposição individual não vai para grupo.**
Alerta nominal de atraso em grupo de WhatsApp expõe o colaborador e abre espaço
para dano moral. Grupo recebe agregado; o nominal vai para o responsável direto.
Isso é imposto por trigger no banco, não por disciplina de quem configura.

**3. Ver a unidade não dá direito a ver o salário.**
Escopo organizacional e sensibilidade do dado são eixos independentes. Supervisor
de unidade vê ocorrência de ponto da sua unidade e não vê RG, remuneração nem ASO.

**4. A IA não inventa e não improvisa consulta.**
O assistente escolhe de um catálogo fechado de métricas e preenche parâmetros.
Nada de SQL livre. A consulta roda como o usuário que perguntou, herdando a
mesma permissão. Pergunta fora do catálogo recebe "não tenho esse dado".

**5. Nenhum alerta é enviado antes de a taxa de erro ser conhecida.**
O motor roda em modo sombra antes de produção. Primeiro relatório cheio de falso
positivo mata a credibilidade do produto no cliente — e é irrecuperável.

**6. Regra de alerta nasce desligada.**
Só liga depois de homologada com o cliente e validada pelo jurídico e RH.

**7. Dado sensível é isolado por construção, não por convenção.**
"Não fazer `select *`" é regra de código, não controle de segurança. PII vive em
tabela apartada, em schema não exposto, atrás de policy que exige escopo e domínio.

---

## 4. Escopo da v1

### Entra

| # | Capacidade | Observação |
|---|---|---|
| F1 | Sincronização com o sistema de ponto | Secullum primeiro; conector plugável |
| F2 | Dimensão organizacional curada | Empresa → unidade → colaborador, com mapeamento validado |
| F3 | Motor de detecção de desvio | Modo sombra obrigatório antes de produção |
| F4 | Dashboard de gestão | Filtros por empresa, unidade e período |
| F5 | Consulta individual do colaborador | Histórico e indicadores por período |
| F6 | Monitor diário da jornada | Situação do dia corrente por unidade |
| F7 | Alertas por WhatsApp e e-mail | Regras configuráveis, outbox com retry |
| F8 | Relatório consolidado periódico | Por unidade, com link para o dashboard filtrado |
| F9 | Assistente de IA sobre o catálogo de métricas | Sem SQL livre |
| F10 | Controle de acesso por papel e escopo | Nove papéis, quatro domínios sensíveis |
| F11 | Auditoria | Acesso, alteração, importação, envio, consulta de IA |
| F12 | Base de pessoas, documentos e vencimentos | Modelo pronto; carga conforme diagnóstico |
| F13 | Indicadores de folha e custo | Via upload de Excel na v1; exige mapa de código de evento |
| F14 | Controle de acordos e descontos | Exige autorização documentada |
| F15 | Visualização para monitor e TV | Sem dado pessoal em tela coletiva |

### Não entra

Substituir o sistema de ponto ou o contábil. Calcular obrigação trabalhista.
Executar pagamento. Enviar informação a órgão do governo. Emitir advertência sem
validação humana. App móvel próprio. Portal completo do colaborador. Recrutamento
e seleção. Medicina e segurança do trabalho completa. Assinatura eletrônica
própria. Sistema operacional ou financeiro de estacionamento. Migração irrestrita
de histórico.

---

## 5. Requisitos funcionais

### F1 — Sincronização

- Coleta incremental por cursor, com registro de execução, contagem e erro.
- Credencial por tenant, guardada em cofre; nunca em coluna de texto.
- Falha de sincronização é visível na tela de administração e não silenciosa.
- Reprocessar um período não duplica evento.
- ⏳ **Frequência e janela dependem do rate limit da API** — ver spec técnica.

### F2 — Dimensão organizacional

- Unidade é entidade do OperaX, não do sistema de origem.
- Mapeamento origem → unidade é curado e validado, com data e responsável.
- Mapeamento não validado aparece sinalizado na interface.
- Agregação por empresa vai sempre por colaborador → empresa.
  *Na Kastro Park, ~26% dos colaboradores têm departamento e empresa divergentes
  no Secullum; usar o caminho errado quebra filtro e relatório.*

### F3 — Motor de detecção

Tipos cobertos: entrada atrasada, entrada adiantada, saída antecipada, saída
postergada, intervalo excedido, intervalo insuficiente, intervalo sem retorno,
marcação incompleta, dia sem marcação, marcação em dia sem jornada prevista,
jornada acima do limite, marcação fora do perímetro.

- Cada tipo é ligado ou desligado por tenant, e cada um decide se conta como
  desvio nos KPIs. **A pergunta "conta só hora extra ou também atraso?" é
  configuração, não desenvolvimento.**
- Tolerância vem do sistema de origem e pode ser sobreposta por tenant.
- Período de férias ou afastamento nunca gera desvio — inclusive sobrepondo a
  regra de folga.
- Gestor não é excluído do próprio relatório.
- Um desvio aparece em exatamente um ciclo de relatório.
- Correção retroativa na origem revoga o desvio; nada é deletado.

### F4 — Dashboard

Filtros: empresa (nível 1), unidade (nível 2), período com atalhos (hoje, 7 dias,
30 dias, mês atual, intervalo livre). Filtros trafegam por query string, porque o
link do relatório abre o dashboard já filtrado.

Indicadores: total de desvios; minutos acumulados; proporção excedente × faltante;
tendência temporal; ranking por unidade; ranking por colaborador; recorrência
(desvio em 3+ dias na janela); colaboradores afetados; pendências sem ciclo.

Nenhum indicador conta dia de afastamento como desvio. Motivo de afastamento
nunca aparece — rótulo neutro sempre.

### F5 — Consulta individual

Dados cadastrais básicos, unidade, jornada, gestor, histórico de marcação e de
cada tipo de desvio, justificativas, indicadores consolidados por período livre.
Colunas sensíveis aparecem conforme o domínio permitido ao papel.

### F6 — Monitor diário

Entrada registrada, situação da jornada, intervalo, quem não retornou, quem não
registrou saída, tempo de atraso, marcação incompleta, presença por unidade.

**Cadência de 15 minutos** (`docs/DECISAO-CADENCIA-SYNC.md`; o cadastro segue em
30). A tela exibe a idade do dado de forma permanente — sem isso, um gestor olha
às 09:05 um retrato de 08:40 e conclui que ninguém atrasou. O alerta correspondente informa o horário observado, não "agora".

### F7 — Alertas

Tipos: atraso na entrada, ausência de marcação, não retorno do intervalo,
intervalo acima do limite, saída antecipada, jornada acima do limite, marcação
fora do perímetro, solicitação de justificativa, ocorrência recorrente, pendência
próxima ao fechamento, e os limiares financeiros.

Destino por unidade e função: gestor, supervisor regional, DP, RH, diretoria,
grupo. Conteúdo individual jamais para grupo. Envio com idempotência e retry.
Custo por mensagem registrado.

### F8 — Relatório consolidado

Por unidade, na periodicidade configurada, por WhatsApp e/ou e-mail, com link
para o dashboard já filtrado. Quando inclui ocorrência de dia anterior detectada
com atraso, o relatório declara isso explicitamente — senão os números parecem
divergir do dashboard e a confiança cai.

### F9 — Assistente de IA

Responde em linguagem natural sobre desvios, rankings, tendências, recorrência,
vencimento de documento e resumo de folha. Usa apenas o catálogo de métricas.
Toda consulta é registrada com pergunta, métrica usada, latência e tokens.

### F10 — Acesso

Nove papéis. Escopo aditivo por empresa e unidade. Quatro domínios sensíveis:
dado pessoal, remuneração, saúde, disciplinar. Quem vê o quê é configuração por
tenant, não código.

### F15 — Tela para TV

Indicadores agregados, situação por unidade, ocorrências do dia, alertas
prioritários, atualização automática. **Nenhum nome de colaborador em tela de
acesso coletivo** — só número por unidade.

---

## 6. Requisitos não funcionais

**Segurança.** Nenhuma tabela alcançável pela chave pública. Espelho da origem e
domínio em schemas não expostos. Toda view com privilégio do invocador. Nenhuma
função executável anonimamente. Credencial em cofre. Verificado por suíte
automatizada que roda a cada alteração de policy, view ou permissão.

**Proteção de dados.** Dado pessoal e sensível isolado em tabela própria com
política que exige escopo e domínio. Exame ocupacional guarda apenas aptidão e
validade — nunca diagnóstico, CID ou descrição de restrição. Afastamento usa
rótulo neutro. Auditoria de acesso, alteração e exportação. O cliente é
controlador; a EURECA é operadora.

**Desempenho.** Dashboard carrega em menos de 3 segundos no período padrão.
Agregação pesada é materializada e atualizada pelo worker, não recalculada no
navegador.

**Confiabilidade.** Sincronização e envio são idempotentes. Falha parcial não
duplica alerta nem perde evento. Reprocessar período produz o mesmo resultado.

**Isolamento entre clientes.** Provado por teste funcional com dois tenants e
quatro papéis, executado na suíte a cada alteração.

---

## 7. Métricas de sucesso

| Métrica | Linha de base | Alvo v1 |
|---|---|---|
| Tempo de conferência e fechamento | ~1 semana | ≤ 1 dia |
| Ocorrência tratada no dia | ~0% | ≥ 60% |
| Falso positivo do motor | — | ≤ 5% ao sair da sombra |
| Relatório gerado manualmente | 100% | 0% |
| Carga do dashboard | — | < 3 s |
| Divergência dashboard × relatório | — | zero |

A última é a mais importante. Se dashboard e relatório mostrarem números
diferentes uma única vez, o cliente para de confiar nos dois.

---

## 8. Multi-tenant: o que precisa existir para vender o segundo cliente

1. Onboarding de tenant sem migration: criar tenant, cadastrar integração,
   mapear unidades, convidar usuários. **Hoje: banco pronto, interface não.**
2. Cofre de credencial por tenant. **Pronto.**
3. Isolamento provado por teste. **Pronto.**
4. Conector para um segundo sistema de ponto. **Não iniciado** — é o que tira o
   produto da dependência de um fornecedor só.
5. Faturamento e limite de uso por tenant. **Não iniciado.**
6. Documentação de conformidade para responder due diligence. **Parcial.**

### Condição contratual

A comercialização depende de o contrato com o cliente âncora prever que a EURECA
mantém a titularidade da plataforma e o cliente recebe licença de uso, com os
dados permanecendo dele. Sem essa cláusula, não há produto — há um projeto sob
encomenda. **Pendente de redação.**

---

## 9. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Rate limit da origem não sustenta ~96 execuções/dia de batidas + o backfill diário | Cadência cai e o monitor diário perde utilidade | Pendência **reaberta** em 24/08 com o volume real — ver `docs/DECISAO-CADENCIA-SYNC.md` |
| Escala 12x36 mal representada | Falso positivo em massa, produto desacreditado | Jornada esperada materializada com grau de confiança; modo sombra |
| Plano de contas de eventos não mapeado | Metade do dashboard financeiro não sai | Curadoria com a contabilidade, dimensionada como atividade de implantação |
| Provedor de WhatsApp não oficial | Número banido, sem SLA | Camada de abstração; migrar para API oficial antes de escalar |
| Dependência de um único sistema de ponto | Produto refém do fornecedor | Conector plugável desde a v1 |
| Custo variável (mensagem e IA) acima da mensalidade | Sustentação com margem negativa | Custo por mensagem e tokens registrados desde o primeiro envio |

---

## 10. Depois da v1

Portal do colaborador, solicitação de férias e documentos, comunicação interna,
pesquisa de clima, avaliação e feedback, gestão de treinamento, recrutamento,
gestão de benefícios, planejamento de escala, previsão de custo com pessoal,
indicadores de rotatividade e absenteísmo, e conectores para outros sistemas de
ponto e folha.

Cada item entra em backlog e é priorizado com análise técnica e comercial
separada. Nada disso está incluído na mensalidade de sustentação.

---

## Pendências que travam partes deste PRD

- ⏳ **Documentação da API do sistema de ponto** — trava F1, F3 e F6.
- ⏳ **Diagnóstico do banco atual** — confirma nomes e volume reais.
- ⏳ **Decisões do cliente** — periodicidade do relatório, KPIs da v1, domínio do
  painel, e se o gestor terá acesso próprio.
- ⏳ **Estrutura real da Kastro Park** — número de CNPJs, unidades, colaboradores
  e principalmente quais escalas são praticadas.
- ⏳ **Cláusula de propriedade intelectual.**
