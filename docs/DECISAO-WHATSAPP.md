# OperaX — três provedores de WhatsApp

Decisão do cliente: **API oficial da Meta, Z-API e uazapi**, os três suportados.
Este documento registra como isso foi encaixado no schema, o que a pesquisa
encontrou sobre risco, e a conta de custo — porque a razão usual para escolher
não oficial é preço, e no nosso volume ela não se sustenta.

---

## 1. O achado que muda a recomendação

Z-API e uazapi são **não oficiais**: conectam por QR Code, imitando o WhatsApp
Web. A Meta apertou o cerco ao longo de 2026, e a mudança relevante não é de
volume, é de método — a detecção passou a olhar **fingerprint de conexão**
(padrão de pacote, comportamento do cliente) em vez de volume de disparo. Isso
tira a proteção que operações pequenas achavam ter. As duas plataformas aparecem
nominalmente nas listas de ferramentas afetadas, junto de Baileys, Evolution API,
WPPConnect, Venom-Bot e outras. O banimento é **do número**, permanente, e sem
processo de recurso.

**Ressalva honesta de fonte.** Boa parte do material que documenta essa onda vem
de empresas que vendem a solução oficial, e portanto tem incentivo para
dramatizar. Duas coisas seguem valendo mesmo descontando o viés: o mecanismo
descrito é tecnicamente plausível, e o risco é **assimétrico**. Se o alarme for
exagerado, perdemos algum esforço de integração. Se estiver certo e o número
banido for o da Kastro Park, quem explica é a EURECA.

Por isso `meta_cloud` é o **padrão** no schema. Os outros dois existem, funcionam,
e exigem escolha deliberada.

---

## 2. Por que os três não cabem atrás de `enviar(texto)`

Esta é a parte de engenharia que importa, e é contraintuitiva.

- **Meta Cloud API.** Mensagem iniciada pelo negócio fora da janela de 24h
  **precisa ser um template aprovado com antecedência**, enviado como
  `(nome_do_template, idioma, variáveis em ordem)`. Texto livre é recusado.
- **Z-API e uazapi.** Recebem texto livre e não têm conceito de template.

Uma interface desenhada em torno de texto livre **nunca** atende o provedor
oficial — não é questão de adaptador, é que a informação estruturada já se
perdeu quando a string foi montada. Uma interface desenhada em torno de
`(template, variáveis)` atende os três: os não oficiais renderizam o template
localmente e mandam o texto pronto.

**O contrato é template-first.** O render é problema do provedor.

### O acaso feliz

A migration 13 já obrigava `alert_queue.payload` a ser **objeto estruturado**, não
string montada. Aquela decisão foi tomada por outro motivo — garantir que o
alerta carregasse o horário observado, nunca "agora". Acontece que é exatamente
o formato que um template da Meta exige: as chaves do payload **são** as
variáveis do template.

Se o payload tivesse sido uma string, adotar a API oficial hoje seria refazer o
motor de alertas.

---

## 3. O que a migration 15 acrescenta

| Objeto | Papel |
|---|---|
| `app.message_template` | Catálogo por tenant: `code` interno estável, `variables` na ordem dos `{{n}}`, `body` para render local, `meta_template_name` e `meta_status` |
| `util.validate_template_body()` | O corpo usa exatamente os placeholders declarados — nem a mais, nem a menos |
| `app.alert_rule.template_code` | Qual template a regra usa |
| `app.alert_queue.template_code` / `.provider` | Amarra a mensagem enfileirada ao contrato |
| `util.validate_alert_template()` | O payload cobre todas as variáveis; e `meta_cloud` só aceita template `approved` |
| `integration_whatsapp_unico_ativo` | No máximo um provedor de WhatsApp ativo por tenant |
| `public.fn_whatsapp_readiness()` | `ready = false` quando há regra ligada apontando para template não aprovado |

Três falhas silenciosas viraram erro alto:

1. **Placeholder órfão.** Template que declara três variáveis e usa `{{4}}` no
   corpo mandaria `{{4}}` literal para o gestor. Agora é recusado na escrita.
2. **Payload incompleto.** Variável declarada e ausente no payload: o oficial
   recusa a mensagem, o não oficial envia com buraco. Agora é recusado.
3. **Template não aprovado com provedor oficial.** É o pior dos três, porque
   falha **calado**: a regra está ligada, a fila enche, a Meta recusa, e ninguém
   descobre até o gestor reclamar que não recebeu. `fn_whatsapp_readiness()`
   torna isso visível antes de ligar a regra — mesma ideia de
   `fn_data_freshness` e `fn_detection_health`.

Onze asserções novas em `scripts/97_teste_regras_alerta.sql`, seções D e E.

---

## 4. A conta de custo

O argumento comum a favor do não oficial é preço: cobra-se por instância
(mensalidade fixa), não por mensagem. Vale conferir contra o nosso volume real.

Tabela da Meta para o **Brasil**, categoria *utility* — que é a nossa, alerta
operacional: **≈ US$ 0,0068 por mensagem**. Desde 1º de julho de 2025 a cobrança
é **por mensagem**, não mais por conversa de 24h.

Kastro Park, dimensionada pelo que já está no protótipo — 6 unidades, ~182
colaboradores, 20 a 60 ocorrências por dia:

| Cenário | Mensagens/mês | Custo/mês |
|---|---|---|
| 60 alertas individuais + 6 resumos por dia | ~2.000 | **≈ US$ 14** |
| Pico sustentado de 200 alertas por dia | ~6.000 | **≈ US$ 41** |

Ou seja: **o custo da API oficial, no nosso volume, é ruído** — bem abaixo de
qualquer mensalidade de instância. O motivo real para escolher não oficial não é
preço; é não precisar de verificação de negócio na Meta nem esperar aprovação de
template. São dois atritos de implantação, não uma economia.

Detalhe que ajuda: mensagem *utility* dentro de janela de atendimento aberta é
**gratuita**. Como nossos alertas são iniciados por nós, quase nunca cairemos
nessa faixa — mas se o gestor responder, a conversa seguinte não custa.

**Cuidado de categoria:** template classificado como *marketing* custa cerca de
9x um *utility* no Brasil. Um alerta operacional redigido com jeito de aviso
comercial pode ser reclassificado pela Meta na revisão. O campo `category` em
`app.message_template` existe para deixar isso explícito.

---

## 5. Consequências de implantação

**Se o tenant usar `meta_cloud`:**

1. Verificação de negócio no Meta Business Manager — feita pelo cliente, com o
   CNPJ dele. Não é algo que a EURECA faz no lugar dele.
2. Cada template aprovado na WABA **do cliente** (por isso `message_template` é
   por tenant). Aprovação leva de horas a dias.
3. Só depois disso a regra pode ser ligada. `fn_whatsapp_readiness()` é o
   semáforo, e a tela de Administração deveria mostrá-lo.

**Se usar `z_api` ou `uazapi`:**

1. Sobe rápido — conectar QR Code e pronto, sem verificação e sem template.
2. O número precisa de um celular pareado e estável.
3. **Registrar em contrato que o risco de banimento é do cliente**, com o
   caminho de migração para o oficial já previsto. Como o contrato é
   template-first, essa migração é trocar o valor de `provider` e aprovar os
   templates — não é reescrever o sender.

O `body` do template continua existindo mesmo no provedor oficial: é o que
permite pré-visualizar a mensagem na tela de regras de alerta, que o protótipo
já desenhou.

---

## 6. Endpoints, para quem for implementar

**uazapi** — `POST https://api.uazapi.com/instances/{id}/messages/send/text`,
header `Authorization: Bearer <token>`, corpo `{"phone": "...", "message": "..."}`.

**Meta Cloud API** — `POST /{phone-number-id}/messages` com
`type: "template"`, nome do template, idioma e `components[].parameters` na ordem
declarada em `variables`.

**Z-API** — modelo por instância e token, com endpoint de envio de texto
equivalente ao do uazapi.

Os três ficam atrás de uma interface em `backend/operax/alertas/provedores/`,
cada um implementando `enviar(template, variaveis, destino)`. Nenhum recebe
string pronta.

---

## Fontes

- [Pricing on the WhatsApp Business Platform — Meta for Developers](https://developers.facebook.com/docs/whatsapp/pricing/)
- [WhatsApp Business API Pricing Brazil 2026 (BRL)](https://whautomate.com/whatsapp-business-api-pricing-brazil)
- [Meta banindo WhatsApp não oficial em 2026 — Cubo Suite](https://blog.cubosuite.com.br/meta-banindo-whatsapp-nao-oficial-em-2026-o-que-mudou-e-o-que-fazer/)
- [WhatsApp API Oficial vs Não Oficial 2026 — SocialHub](https://www.socialhub.pro/blog/whatsapp-api-oficial-vs-nao-oficial-riscos-diferenca/)
- [uazapi — API Premium para WhatsApp](https://uazapi.dev/)
- [uazapi — documentação de envio de mensagem](https://docs.uazapi.com/tag/Enviar%20Mensagem)
