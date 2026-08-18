# OperaX — avaliação do design, rodada 3 (final)

Terceira e última rodada. Mesmo método das anteriores: dependências vendorizadas,
protótipo aberto em navegador, cada cenário alternado por clique e o texto
renderizado extraído e contado. Nenhuma afirmação aqui vem só de leitura de
código.

**Veredito: pronto para o handoff.** Os três blocos foram executados, os dois
defeitos da rodada 2 estão fechados, e não houve regressão em nada estabelecido
nas rodadas anteriores. Sobram dois itens pequenos, nenhum bloqueante.

---

## 1. Os três blocos

### Bloco 1 — coerência do cenário "Dado atrasado" · **fechado**

Medido no navegador, alternando o cenário e contando as linhas visíveis que ainda
citavam o horário da leitura normal:

| Onde | Rodada 2 | Rodada 3 |
|---|---|---|
| Monitor, cenário "Dado atrasado" | 1 linha com 08:40 | **0** |
| Idem, com o detalhe da ocorrência aberto | 2 linhas | **0** |

O cenário "Dia sem ocorrência" mostra 08:40 em cinco lugares — e está **correto**:
naquele cenário a leitura é mesmo às 08:40, o que falta são ocorrências, não
dado. A distinção foi respeitada.

### Bloco 2 — nomes reais de tabela no handoff · **fechado**

Extraí todos os identificadores de banco citados nos três documentos do handoff e
validei contra o schema real:

| | Rodada 2 | Rodada 3 |
|---|---|---|
| Identificadores citados | 27 | **37** |
| Existem no schema | 22 | **37** |
| Inventados | 5 | **0** |

Os cinco nomes inventados sumiram e foram substituídos pelos corretos. E a
cobertura cresceu: dez identificadores a mais, todos verdadeiros.

Um detalhe que vale registrar: o handoff cita `app.message_template` — tabela que
**não estava no pacote enviado** (subiram de novo a versão de 13 migrations, sem
a migration de WhatsApp). O nome foi deduzido da descrição no prompt e bateu
exatamente com o que existe. Sorte, mas sorte informada.

### Bloco 3 — os três provedores de WhatsApp · **feito, e bem**

A tela de Regras de alerta cresceu de 2.725 para 3.969 caracteres, e o que
entrou é o que mais importava: **o estado de falha silenciosa ganhou desenho
próprio, em três camadas.**

1. **Banner no topo da lista:** *"1 regra ligada sem template válido — os alertas
   estão sendo descartados"*, com a explicação de por quê: *"Com provedor
   oficial, mensagem sem template aprovado é recusada pela Meta sem erro de
   retorno. A regra parece ligada e nada chega."*
2. **Na regra afetada:** *"Ligada, mas o template resumo_diario_v2 está em
   análise: a Meta descarta a mensagem sem devolver erro. **3 alertas perdidos
   desde 16/08**."* Quantificar a perda foi ideia dele, e é o que transforma o
   aviso em urgência.
3. **Regra com template inválido não liga:** o interruptor vira um cadeado
   "bloqueada · sem template válido", com o motivo escrito abaixo.

O cadeado aqui **não** viola a regra 5. Aquela regra trata de papel — o que uma
pessoa pode ver. Esta é uma trava de estado do sistema: a regra não pode ser
ligada porque não funcionaria. Distinção correta, e feita sem eu ter pedido.

A prévia mostra o template com as variáveis numeradas e uma legenda mapeando cada
número — `{{1}} unidade`, `{{2}} colaborador`, `{{3}} horário registrado`,
`{{4}} horário previsto`, `{{5}} minutos`, `{{6}} horário da leitura`. Os cinco
estados de aprovação estão todos representados: aprovado, em análise, reprovado,
rascunho, pausado.

Na aba **Integrações**, a escolha de provedor virou uma comparação honesta:

| | Meta Cloud API | Z-API / Uazapi |
|---|---|---|
| | oficial | não oficial |
| Conexão | número verificado na conta Meta | ponte sobre o WhatsApp Web, por QR Code |
| Mensagem | template aprovado, variáveis numeradas | texto livre, sem aprovação prévia |
| Risco | sem risco de banimento | **o número do cliente pode ser banido, sem recurso** |
| Prazo para subir | 2 a 5 dias | 15 minutos |

É exatamente o enquadramento que eu tinha pedido: informa o risco no momento da
escolha, sem dramatizar e sem esconder — e coloca ao lado o custo real do
caminho seguro, que são os dias de espera. Quem escolher o não oficial vai
escolher sabendo.

---

## 2. Alinhamento com a migration 15, sem tê-la visto

Vale anotar porque facilita a implementação: o desenho chegou sozinho ao mesmo
modelo que a migration 15 já implementa.

| No desenho | No banco |
|---|---|
| rascunho · em análise · aprovado · reprovado · pausado | `meta_status` com os mesmos cinco valores |
| variáveis numeradas com legenda | `variables text[]`, a ordem define `{{n}}` |
| "Um provedor ativo por tenant" | índice único `integration_whatsapp_unico_ativo` |
| "2 de 5 templates aprovados" | `fn_whatsapp_readiness().templates_approved` / `templates_total` |
| "1 regra ligada sem template válido" | `fn_whatsapp_readiness().rules_blocked` |
| "categoria Utility" | `message_template.category` |
| "3 alertas perdidos" | contável em `alert_queue` com `status = 'discarded'` |

Nenhuma tradução é necessária no handoff. A tela pede o que a função devolve.

---

## 3. O que sobrou

### A. Código de template em português — pequeno, decidir agora

Os templates do desenho são `desvio_individual_v3`, `sem_marcacao_v1`,
`resumo_diario_v2`, `falha_sync_v1`, `documento_vencendo_v1`.

`message_template.code` é dado, não identificador de schema — então nada quebra.
Mas o catálogo vizinho, `deviation_type.code`, já é inglês: `late_entry`,
`break_exceeded`, `no_punches`. Duas tabelas de catálogo na mesma base com
convenções opostas é o tipo de inconsistência que ninguém corrige depois que há
dado em produção.

Sugestão: `deviation_individual_v3`, `no_punches_v1`, `daily_summary_v2`,
`sync_failure_v1`, `document_expiring_v1`. É achar e substituir, agora.

### B. Dívida de catálogo no design system — não bloqueia

O `_ds_manifest.json` continua com 16 componentes e o starting point ainda é a
tela `visao-executiva` do Aegis. Os componentes novos (Table, Chart, Drawer,
Tabs, EmptyState, Toast, Skeleton, Pagination) seguem vivendo em `_ds_extras.js`,
fora do registro.

Não bloqueia o handoff — o `COMPONENTES.md` documenta a API de cada um, e o
Claude Code lê de lá. O custo aparece depois: uma sessão futura do Claude Design,
partindo do design system, não saberá que eles existem e vai reinventá-los. Se
houver rodada 4 para outra coisa, aproveite e peça o registro.

---

## 4. Estado final, três rodadas

| | R1 | R2 | R3 |
|---|---|---|---|
| Telas entregues | 7 de 9 | 9 | 9 |
| Identificadores de banco corretos no handoff | — | 22/27 | **37/37** |
| Métricas do assistente que existem | 0 de 10 | 9+4 | 9+4 |
| Tabelas HTML cruas | 5 | 0 | 0 |
| Instâncias de componente | 78 | 108 | **126** |
| Pares reprovando em contraste (tema claro) | 5 | 0 | 0 |
| Regras de produto cumpridas | 7 de 7 | 7 de 7 | 7 de 7 |

Verificado de novo nesta rodada, para descartar regressão: zero "hora extra",
zero CPF/RG/PIS, zero frases relativas do tipo "está atrasado", tokens de
contraste intactos, zero tabela crua. A única ocorrência de "agora" é o botão
"Executar agora" da aba de integrações — rótulo de ação, não frase de alerta.

---

## 5. Próximo passo

O handoff está pronto para entrar no repositório. Antes de acionar o Claude Code:

1. **Trocar os cinco códigos de template para inglês** (item A) — dois minutos,
   e evita conviver com duas convenções.
2. **Rodar o handoff contra o repo atualizado**, com as 15 migrations. O
   `TELAS.md` cita `app.message_template` corretamente, mas o pacote que o Claude
   Design leu não a continha; conferir se as colunas citadas batem com as reais é
   barato e o `verificar_docs.py` faz isso sozinho.
3. Seguem abertas, e são suas, as três decisões que travam gaps em
   `COBERTURA-ESCOPO.md`: **saldo de horas** (espelhar do Secullum ou calcular),
   **mapa código de evento → categoria de folha** (segura duas métricas
   previstas), e **formato de exportação de relatório**.
