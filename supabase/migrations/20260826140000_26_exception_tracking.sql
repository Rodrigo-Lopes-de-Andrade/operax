-- ============================================================================
-- OperaX — 26. QUEM ESTÁ FORA DO MOTOR DE PROPÓSITO, E DIZ ISSO
-- ----------------------------------------------------------------------------
-- Seis pessoas da administração do cliente âncora têm horário em branco POR
-- DESENHO: os horários irmãos se chamam literalmente "Ponto por exceção" e
-- "Marcação Supervisor". Elas não têm jornada a cumprir, e medi-las contra uma
-- jornada que não existe é medir contra nada.
--
-- Hoje elas caem em `unrostered` no monitor — "ativo sem jornada prevista" —, no
-- mesmo balde de quem o motor deixou de cobrir por falha. As duas situações têm
-- exatamente a mesma aparência na tela e significam o oposto: uma é decisão, a
-- outra é bug. `operax/motor/jornada.py` já dizia, em comentário, que separá-las
-- é decisão de produto e que codificar um regex sobre nome de horário a tomaria
-- em silêncio. A decisão foi tomada em 26/08/2026; esta coluna é ela, escrita.
--
-- POR QUE NA PESSOA, E NÃO NO HORÁRIO
-- A migration 25 pôs a rotação no horário porque a rotação É do horário: todo
-- mundo em "P01 - Ímpar" gira junto. Estar fora do motor não é do horário, é do
-- papel: um supervisor movido para um horário declarado continua sendo medido
-- por exceção. Mudar o horário de alguém não pode ligar nem desligar a medição.
--
-- NASCE `false` PARA TODO MUNDO, e pelo mesmo motivo que `triggers_alert` e
-- `requires_justification` nascem: uma pessoa que aparece fora da medição sem
-- alguém a ter tirado é uma pessoa que ninguém decidiu não medir. Ligar isso é
-- ato humano, com trilha, e o default não pode antecipá-lo.
--
-- ⚠️ A PROMOÇÃO NÃO PODE APAGAR ISTO. `cadastro.py` roda a cada sincronização e
--    faz `on conflict do update set` sobre `app.employee`. Ele lista as colunas
--    uma a uma, então uma coluna nova sobrevive sozinha — mas isso é
--    propriedade do SQL de hoje, não garantia do schema. `scripts/92_teste_
--    cadastro.py` passa a afirmar que a marca sobrevive a uma promoção.
--
-- Nenhuma policy nova: a coluna entra numa tabela que já tem RLS e cujas
-- policies de leitura e escrita já valem para ela.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

alter table app.employee
  add column if not exists exception_tracking boolean not null default false;

comment on column app.employee.exception_tracking is
  'Fora do motor de detecção POR DECISÃO — "ponto por exceção", supervisão. Nasce false: '
  'quem aparece fora da medição sem alguém ter tirado é quem ninguém decidiu não medir. '
  'Quem está aqui não materializa jornada esperada e é contado à parte no monitor, '
  'separado de `unrostered`, que é falha de cobertura e tem a mesma aparência.';

do $$
declare
  v text;
begin
  select column_default into v
    from information_schema.columns
   where table_schema = 'app' and table_name = 'employee'
     and column_name = 'exception_tracking';
  if v is distinct from 'false' then
    raise exception 'exception_tracking com default %, e não false: gente sairia da medição sem ninguém ter tirado', v;
  end if;

  select is_nullable into v
    from information_schema.columns
   where table_schema = 'app' and table_name = 'employee'
     and column_name = 'exception_tracking';
  if v <> 'NO' then
    raise exception 'exception_tracking anulável: nulo não é "sim" nem "não", e a conta do monitor não fecha com três estados';
  end if;

  raise notice 'OK: estar fora do motor virou fato declarado, e nasce desligado.';
end $$;
