# Prompt mestre — OperaX

> **Como usar:** cole o conteúdo inteiro deste arquivo (do `---` em diante) como
> primeira mensagem numa sessão do Claude Code aberta na raiz do repositório,
> com acesso ao projeto Supabase configurado.

---

Você vai implantar o OperaX: uma camada de gestão, automação e inteligência sobre
sistemas de ponto. Lê o Secullum, detecta desvio de jornada, avisa o gestor no dia
e consolida custo de pessoal. É multi-tenant desde o primeiro commit — a Kastro
Park é o primeiro cliente, não o único.

## Antes de qualquer coisa, leia

1. `CLAUDE.md` — **diretrizes de comportamento, stack, mapa de arquitetura,
   contrato front↔back e as 10 regras de segurança que não se quebram.** Ele é a
   autoridade; este prompt só organiza a execução.
2. `docs/PRD-OPERAX.md` — o que o produto faz e por quê
3. `docs/SPEC-TECNICA.md` — como cada componente funciona
4. `docs/SPRINTS.md` — ordem, dependências e os seis gates
5. `docs/DICIONARIO-DE-DADOS.md` — modelo de dados (gerado; não editar à mão)

As 14 migrations em `supabase/migrations/` já estão escritas e validadas em
Postgres 16 local. Seu trabalho não é reescrevê-las: é aplicá-las com segurança no
projeto real, ajustar o backend no mesmo passo e construir o que vem depois.

## Ordem de execução

Siga `docs/SPRINTS.md`. Os pontos onde você **para e me consulta** antes de seguir:

**S0 — Pré-voo, diagnóstico e blindagem.** O repositório **não está vazio**: já
existem migrations de vocês, e as 12 do OperaX entram depois delas, nunca no lugar.

Rode primeiro `scripts/01_preflight.sql` (read-only, simula sem aplicar) e
`scripts/00_diagnostico.sql`, salvando as saídas em `docs/`. **Pare e me consulte**
se qualquer uma destas for verdadeira:

- a seção 3 do pré-voo vier vazia (a convenção não é PascalCase — o predicado das
  migrations `00` e `03` precisa mudar);
- a seção 5 listar alguma tabela que não deveria ir para `app`;
- a seção 6 acusar colisão de nome com o modelo novo;
- a última migration existente tiver timestamp maior que `20260815100000`.

Gere também o baseline para a suíte testar a fusão real, não o stub simulado:
`pg_dump "$DATABASE_URL" --schema-only --no-owner --no-privileges -n public > scripts/_baseline.sql`

Só depois: migrations `00`, `01`, `02`.

Ao terminar a `01`, me lembre de reduzir os Exposed schemas do Supabase para
`public` e `graphql_public`. Isso não dá para fazer por SQL.

**S1 — Isolamento e backend.** A migration `03` **quebra o sync** — aplique junto
com o ajuste de código no mesmo commit. `operax/sync/` passa a apontar para o
schema `secullum`, e `core/tenant.py` passa a injetar `tenant_id` em todo acesso.
Depois: migration `04` e a carga da dimensão organizacional.

**S2 — Modelo completo.** Migrations `05` a `11`. `make db-test` no CI.

**S3 — Jornada esperada.** `operax/motor/jornada.py`. Meça o percentual de
colaboradores com confiança ≥80 e **me reporte antes de seguir**. Se mais de 20%
ficar abaixo, **pare**: é escopo adicional de implantação e precisa de conversa
comercial, não de solução técnica silenciosa.

**S4 — Motor em sombra.** `operax/motor/deteccao.py` conforme §3 da spec. Rode com
`modo='sombra'`, compare contra a apuração do Secullum, classifique cada
divergência em escala errada, tolerância errada ou bug. Só promova para produção
com falso positivo ≤5% em duas execuções seguidas.

**S5 — Dashboard.** Next.js 16 na Vercel + endpoints FastAPI para dado individual
e sensível. **S6 — Alertas e relatório.** **S7 — Assistente de IA.**
**S8 — Homologação.**

## Verificação

```bash
make test && make lint      # antes de declarar qualquer tarefa concluída
make db-test                # obrigatório se tocou banco, policy, view ou grant
```

`make db-test` sobe Postgres descartável, aplica as 14 migrations, roda 23
asserções funcionais de isolamento (dois tenants, quatro papéis) e 11 verificações
estruturais, regenera o dicionário de dados e confere que toda referência a objeto
de banco na documentação existe.

Se ficar vermelho, corrija o código — **não comente a asserção**.

## Quando travar

A documentação da API do Secullum **ainda não chegou**. A seção 10 da spec lista
10 pendências. Ao esbarrar em qualquer uma:

- Implemente a parte que não depende dela.
- Deixe a parte dependente atrás de uma interface, com `TODO ⏳` e o número da
  pendência.
- **Não invente comportamento de API.** Não assuma que existe endpoint de dia
  corrente, nem rate limit, nem que a API devolve valor apurado.
- Me diga no fim da sessão o que ficou bloqueado e por quê.

Para decisão de produto ainda aberta (periodicidade do relatório, KPIs da v1,
domínio do painel, se o gestor terá login): implemente como configuração, com um
default declarado, e me diga qual você escolheu.

## Como trabalhar

- Um commit por entrega coerente. A mensagem explica **por quê**, não o quê.
- Migration nova sempre com `supabase migration new`, nunca editando arquivo já
  aplicado. Idempotente, terminando com um bloco `do $$` que falha alto se a
  garantia dela não se sustentar — siga o padrão das 12 existentes.
- Antes de mudar qualquer coisa de segurança, releia a seção correspondente da
  spec e as 10 regras do `CLAUDE.md`. Se ainda achar que deve mudar, me pergunte.
- Prefira falhar cedo e ruidosamente a degradar em silêncio. Erro em migration é
  barato; vazamento entre clientes não é.

Comece pelo S0. Me mostre a saída do diagnóstico e a confirmação da convenção de
nomes **antes** de aplicar qualquer migration.
