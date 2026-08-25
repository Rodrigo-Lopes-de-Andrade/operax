# OperaX — PRD da etapa RH

**Etapa:** upload de tabelas de RH por template + telas de visualização e edição
+ carga inicial.
**Contexto:** complementa `PRD-OPERAX.md`. O produto está em desenvolvimento no
Claude Code; esta etapa entra sobre o que já existe. Decisões de origem em
`DECISAO-RH-UPLOAD-TELAS.md`.

---

## 1. O problema

O RH do cliente vive numa planilha de 17 abas — cadastro, vencimentos,
afastamentos, movimentações, acordos e dashboards misturados, com fórmulas
quebradas e abas duplicadas. O OperaX hoje lê o ponto (Secullum) e importa a
folha, mas **não guarda o que só o RH sabe**: supervisor, benefícios,
documentos e seus vencimentos, afastamentos, acordos financeiros.

Sem esse dado dentro do sistema, três coisas ficam mancas: a Consulta individual
mostra menos do que o DP precisa no fechamento; os vencimentos (ASO, CNH,
experiência) continuam sendo perseguidos à mão; e a promessa de substituir a
planilha não se cumpre — o cliente mantém as duas coisas.

## 2. O que esta etapa entrega

Com esta etapa, o OperaX passa a ser **fonte da verdade da camada de RH** que o
Secullum não cobre — mantida por dois caminhos que são o mesmo funil:

1. **Upload por template**: arquivo baixado do próprio sistema, já preenchido
   com o dado atual, uma tabela por vez. Editar e subir; o preview mostra erro
   por linha antes de gravar.
2. **Telas de edição**: aba **Colaboradores** dentro da Administração — lista
   com filtros e coluna de próximos vencimentos + detalhe editável em abas por
   domínio.
3. **Carga inicial**: a planilha atual do cliente entra na implantação, via
   conversor que gera os templates preenchidos — mesma esteira, mesmo preview,
   com relatório do que foi descartado e por quê.

## 3. Quem usa

- **DP/RH** — mantém o cadastro no dia a dia (formulário) e nas rotinas mensais
  (template). Persegue vencimentos pela lista, não por planilha paralela.
- **Supervisor/gestor** — não edita; vê o que o papel dele permite (na Consulta
  individual, como hoje).
- **Implantação (EURECA)** — roda a carga inicial e entrega o relatório de
  descarte.

## 4. Escopo

### Entra (v1 desta etapa — os quatro domínios)

| # | Domínio | Conteúdo |
|---|---|---|
| 1 | Cadastro + posição | dados básicos, supervisor, cargo, nível, unidade |
| 2 | Documentos + ASO | tipos, vencimentos; **só aptidão e validade** |
| 3 | Afastamentos + movimentações | períodos com rótulo neutro; transferências entre unidades |
| 4 | Remuneração + acordos | vigências de salário/benefícios; acordos com parcelas |

Ordem de implementação: 1 → 2 → 3 → 4 (cadastro destrava os demais).
Desligados entram com status próprio — histórico e acordos os referenciam.

### Não entra (decidido, não esquecido)

- **CID e qualquer diagnóstico** — regra 10 do projeto; o template de
  afastamento nem tem a coluna.
- **Conta, agência e banco** — folha é do Domínio; se entrar um dia, é domínio
  sensível novo e decisão à parte.
- **Abas de dashboard da planilha** (GERAL, QUADRO GERAL, FACE GERAL,
  QUADRO_POSTOS, CESTAS) — o sistema as substitui, não as importa.
- **CÓD POSTOS como fonte de escala esperada** — candidata forte, avaliada
  depois desta etapa.
- Registro ou edição de ponto — nunca, em etapa nenhuma.

## 5. Regras de produto desta etapa

Herdam a numeração do projeto e valem como as demais:

1. **Um funil só.** Formulário e template passam pelos mesmos validadores no
   mesmo backend. Upload é o formulário em lote. Carga inicial idem.
2. **O template é o contrato.** O que não tem coluna, não sobe. Baixado do
   sistema, pré-preenchido, com chaves impressas — ninguém digita chave.
3. **Dono do campo visível.** Campo do sync aparece somente-leitura com origem
   e horário da leitura; campo do RH é editável. Nunca os dois editáveis.
4. **Vigência, não edição.** Salário e cargo ganham nova vigência com motivo;
   corrigir é revogar e recriar. Histórico é dado de primeira classe.
5. **Permissão por domínio, na navegação.** A aba Colaboradores aparece para
   quem tem o papel; dentro dela, cada aba de domínio aparece só para quem tem
   o domínio — sem cadeado, sem cinza (regra 5 do projeto aplicada duas vezes).
6. **Chaves divergentes são erro, nunca escolha.** Linha em que matrícula e ID
   RH apontam para pessoas diferentes falha no preview com a explicação.

## 6. Critérios de sucesso

- **Carga inicial fecha em 100%**: toda linha da planilha original tem destino
  no sistema **ou** entrada no relatório de descarte com motivo. Nada some em
  silêncio.
- O DP faz a atualização mensal (template) sem apoio da EURECA a partir do
  segundo mês.
- Zero campo de domínio sensível alcançável por papel sem o domínio — coberto
  por teste, não por revisão.
- A lista de Colaboradores responde "o que vence nos próximos 30 dias?" sem
  planilha auxiliar.
- Depois da carga, a planilha de 17 abas é **aposentada** — critério de
  aceite combinado com o cliente, não consequência esperada.

## 7. Fora de risco (o que esta etapa não pode quebrar)

O motor de detecção, os alertas e a folha não são tocados. A superfície pública
do banco não ganha tabela (regra 1). As três paradas obrigatórias do projeto
continuam: policy de RLS, coluna nova em view pública e grão de
`app.deviation_event`.
