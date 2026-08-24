# OperaX — upload de tabelas de RH e telas de visualização/edição

Decisões tomadas em discussão sobre a planilha real de gestão de funcionários do
cliente (17 abas, analisada **só em estrutura** — nenhuma linha de dado pessoal
foi lida). Este documento registra o modelo; a implementação vem depois do
template oficial e das três pendências do fim.

---

## 1. O princípio: template-first, uma tabela por vez

Confirmado pelo próprio arquivo: cabeçalho ora na linha 1, ora na 2, 6 e 8,
abas ocultas, fórmulas quebradas (`#REF!`), abas duplicadas e dashboards
misturados com dado. Planilha viva não se importa; **template gerado pelo
sistema** se importa:

- O template é **baixado do próprio sistema, já preenchido** com o dado atual —
  upload é diff, não recadastro. A chave (matrícula) vem impressa; o usuário
  nunca a digita.
- Cabeçalho travado + metadados ocultos (`layout_version`, tenant, domínio,
  gerado em) + dropdowns para enums (unidade, tipo, status) + **uma tabela por
  arquivo**.
- O pipeline é o que já existe para a folha: `file_import` com `layout_version`,
  `rows_ok`/`rows_error` e `report` por linha; a tela de Importação (4 passos,
  erro por linha, duplicidade antes de confirmar) é reaproveitada por tipo.

## 2. Upload e formulário são o MESMO caminho de escrita

O formulário que edita 1 colaborador e o template que sobe 80 passam pelos
mesmos validadores, no mesmo backend (caminho 2 — escrita nunca vai do navegador
direto ao banco). Upload é o formulário em lote. Toda escrita registra em
`audit_log`. Nenhuma RLS nova: escrita já é território do FastAPI com
revalidação de papel e domínio.

## 3. Onde vivem as telas — decisão: dentro da Administração

A edição de RH entra como aba **"Colaboradores"** da Administração (junto de
Mapeamento, Unidades, Usuários, Integrações, Auditoria): lista com filtros e
coluna de **próximos vencimentos** (ASO, CNH, experiência 30/60d) + detalhe
editável em abas por domínio.

Duas consequências desenhadas de propósito:

- **Visibilidade de aba por papel** (regra 5 aplicada à navegação): DP/RH vê
  "Colaboradores" sem ver Integrações ou Usuários. Estar na Administração não
  exige ser admin de tudo.
- A **Consulta individual continua read-only** (análise de jornada) e ganha o
  atalho "abrir cadastro" para quem tem permissão — são dois trabalhos
  distintos: conversa de gestão vs. manutenção de registro.

## 4. Propriedade do campo aparece na tela

Campo do sync: **somente-leitura com origem declarada** ("Secullum · leitura de
08:40" — a disciplina de idade do dado estendida ao campo). Campo do RH:
editável. Sem isso, alguém edita campo do sync e a leitura seguinte desfaz.

## 5. Remuneração e cargo: vigência imutável

`employee_compensation` e `employee_position` já são históricas. A tela é linha
do tempo + **"nova vigência"** (desde, valor/cargo, motivo). Corrigir erro =
revogar vigência e criar outra, com trilha. Nunca campo de salário com lápis.

## 6. Escopo v1 das telas de edição — decisão: os quatro domínios

1. **Cadastro + posição** — dados básicos, supervisor, cargo, unidade.
2. **Documentos + ASO** — vencimentos; só aptidão e validade, nunca diagnóstico.
3. **Afastamentos + movimentações** — período com rótulo neutro; transferências.
4. **Remuneração + acordos** — vigências e acordos com parcelas
   (`financial_agreement` + `agreement_installment`, que já esperam os
   "sinistros" da planilha). Domínio sensível: variante de permissão desde o
   dia 1.

Ordem de implementação dentro da v1: 1 → 2 → 3 → 4 (cadastro destrava o resto).

## 7. Mapa: aba da planilha → destino

| Aba | Destino | Nota |
|---|---|---|
| DADOS FUNCIONÁRIOS (84 col.) | `employee` + `employee_pii` + `employee_position` + `employee_compensation` | vira **4 templates**, um por domínio de permissão |
| DESLIGADOS | `employee` (status) | coluna CID **não entra** (regra 10) |
| FALTAS_ATESTADOS | `leave_period` | rótulo neutro; template **sem coluna CID** |
| MOVIMENTAÇÕES | `workforce_movement` | direto |
| FÉRIAS (matriz por ano) | `leave_period` | template converte para formato longo |
| CNH / VENCIMENTO ASO | `document` / `occupational_exam` | só validade/aptidão |
| SINISTROS + CONTROLE PARC. | `financial_agreement` + `agreement_installment` | coluna a coluna |
| UNIDADES | `unit` / curadoria | já coberto pela Administração |
| CÓD POSTOS (entrada/intervalo/saída) | candidata a fonte de escala esperada | **pendência 3** |
| QUADRO GERAL · **GERAL** · FACE GERAL · QUADRO_POSTOS · CESTAS · Planilha1 | **fora — não se importam** | dashboards/derivados; o sistema os substitui. GERAL desconsiderada por decisão explícita |

## 8. LGPD no desenho

- O template é o contrato físico: **o que não tem coluna, não sobe** — CID e
  diagnóstico nunca têm coluna.
- Conta/agência/banco existem na planilha e **ficam fora do escopo v1** (folha é
  do Domínio; se entrar um dia, é domínio sensível novo — decisão à parte).
- Arquivo real do cliente circula por área de upload com storage restrito, não
  por chat/e-mail. Para discussão de estrutura, cabeçalhos bastam; análise de
  conteúdo só com dado anonimizado.

## 9. Carga inicial — decisão: a planilha entra, pelo mesmo funil

Os dados da planilha atual **são imputados na implantação** — mas nunca por
INSERT direto. A carga inicial usa a mesma esteira do upload recorrente:

1. **Sync do Secullum primeiro** — o espelho cria o esqueleto (matrícula, nome,
   unidade).
2. **Template de vínculo** — preenche `hr_code`.
3. **Conversor de implantação**: script que lê a planilha do cliente e gera os
   templates de domínio já preenchidos, na ordem das referências (cadastro/
   posição → documentos/ASO → afastamentos/movimentações → remuneração/
   acordos). O DP não transpõe 84 colunas à mão — revisa o preview de cada
   template gerado e confirma.
4. Cada confirmação é um `file_import` normal: erro por linha com motivo,
   relatório de volta para o RH. A carga inicial é também o mutirão de limpeza
   do dado.

O conversor emite um **relatório de descarte** — o que não subiu e por quê:
coluna CID (regra 10), conta/agência/banco (fora do escopo v1), abas de
dashboard (GERAL, QUADRO GERAL, FACE GERAL, QUADRO_POSTOS, CESTAS, Planilha1).
É a prova LGPD de que diagnóstico nunca entrou no sistema.

Padrões da carga: **DESLIGADOS entram** com status desligado (acordos e
histórico referenciam essas pessoas), sem CID. A conversão roda na implantação,
em ambiente controlado — planilha real não circula por chat/e-mail.

## 10. Pendências e decisões de vínculo

1. **Chave de vínculo — RESOLVIDA.** `app.employee` ganha a coluna `hr_code`
   (o "ID RH" da planilha), anulável e única por tenant quando preenchida. O
   vínculo inicial é feito por um **template de vínculo, de uma vez só**: o
   sistema exporta matrícula + nome (do espelho) com a coluna ID RH em branco;
   o RH preenche e sobe — a curadoria de unidades em versão pessoa, sem score,
   porque quem confirma é humano. Depois disso, todo template sai com as duas
   chaves impressas e o upsert casa por qualquer uma; ninguém digita chave.
   `CÓD E-SOCIAL`, se vier a ser útil, segue o mesmo padrão (mais uma coluna,
   mesma unicidade). A migration entra no pacote do sprint de upload de RH.

   **Sobre chave composta:** composta com o tenant, sim — a unicidade é
   `(tenant_id, matricula)` e `(tenant_id, hr_code)`, como toda chave natural
   em multi-tenant. Composta entre si, não: são **duas chaves alternativas
   independentes** do mesmo registro (identidade real = UUID interno), cada uma
   suficiente sozinha — exigir as duas juntas quebraria a fase inicial do
   vínculo, quando `hr_code` ainda é nulo. Validação obrigatória no preview do
   import: linha em que matrícula e ID RH apontam para pessoas **diferentes** é
   erro daquela linha ("chaves divergem"), nunca escolha silenciosa.
2. **Matriz dono-do-campo**: lista fechada do que o sync governa vs. o que o RH
   governa — é a decisão central; sem ela, nem template nem tela.
3. **CÓD POSTOS como fonte de escala esperada** — potencial de reduzir os
   "escala não confirmada" do monitor. Avaliar depois da v1 do upload.

Próximo passo quando o template de referência chegar: rodada 7 do Claude Design
(aba Colaboradores + detalhe por domínio + estados de proveniência de campo) e
extensão do `file_import` por tipo.
