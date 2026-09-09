-- ============================================================================
-- OperaX — 37. A VERDADE DE REFERÊNCIA DO MODO SOMBRA PASSA A SER HUMANA
-- ----------------------------------------------------------------------------
-- A `docs/SPEC-TECNICA.md` §3.5 mandava medir falso positivo comparando o
-- indício do OperaX com "o que o Secullum registrou". O espelho nunca traz
-- veredito — só entrada — e buscar o veredito na origem foi medido e descartado
-- em 09/09/2026. Ver `docs/DECISAO-VERDADE-DE-REFERENCIA-G4.md`.
--
-- O QUE A MEDIÇÃO MOSTROU, E É ELA QUE JUSTIFICA ESTA TABELA EXISTIR
-- Produção (nklobmlxyidqxarzisph), sobre 2.121 linhas de secullum."Batida":
--
--   | coluna de adjudicação da origem      | preenchida |
--   |--------------------------------------|------------|
--   | "Ajuste"                             | 1          |
--   | "Abono2" / "Abono3" / "Abono4"       | 0          |
--   | "Observacoes"                        | 0          |
--   | status_dia_rotulo (derivado por nós) | 80 (4%)    |
--
-- Dos 326 dias-colaborador que carregam os 820 indícios ativos em sombra, 6 têm
-- rótulo. O cliente não justifica dia no Secullum — então o "veredito" que a
-- origem devolveria é função determinística das MESMAS batidas, escalas e
-- tolerâncias que o motor já lê (`backend/operax/motor/jornada.py` lê
-- `HorarioDia."ToleranciaExtra"/"ToleranciaFalta"`). Ele concordaria com o
-- OperaX quase sempre — inclusive nos seis supervisores que não batem ponto,
-- onde a concordância É o falso positivo que o G4 existe para achar.
--
-- GRÃO: UM VEREDITO POR INDÍCIO, NUNCA POR DIA
-- A taxa do G4 é por evento, e um dia comporta um indício verdadeiro e um falso
-- ao mesmo tempo (o atraso real e a pausa mal lida). Julgar o dia obrigaria a
-- ratear, e ratear é inventar. Por isso `deviation_event_id` é UNIQUE: rever um
-- veredito é `update`, nunca linha nova.
--
-- ⛔ ESTA TABELA NÃO ALTERA O GRÃO DE `app.deviation_event`
-- Ela aponta para ele. Nenhuma coluna nova lá, nenhum tipo novo, nenhuma regra
-- de detecção tocada — a parada declarada no `CLAUDE.md` não é acionada. O que
-- muda é a §3.5, que é documento.
--
-- A CAUSA É OBRIGATÓRIA QUANDO O VEREDITO É FALSO, E PROIBIDA QUANDO NÃO É
-- Falso positivo sem causa não conserta nada: o passo 3 da §3.5 é justamente
-- classificar a divergência. E causa em cima de verdadeiro positivo é ruído que
-- entraria na contagem por tipo de defeito. As duas metades são a mesma
-- constraint, porque as duas metades são o mesmo erro.
--
-- O vocabulário são as três causas que a §3.5 já pedia (escala errada,
-- tolerância errada, bug) mais duas que a medição de 09/09 tornou inevitáveis:
--
--   exempt_from_punching     — a pessoa não bate ponto por função. É a classe
--                              dos seis supervisores, e ela precisa de NÚMERO
--                              antes de virar decisão de produto sobre o grão.
--   justified_outside_system — houve justificativa real, combinada fora do
--                              Secullum, e por isso invisível ao espelho. É a
--                              causa que o `Ajuste` = 1 em 2.121 linhas prevê.
--
-- POLICY: QUEM JÁ VÊ O INDÍCIO EM SOMBRA É QUEM O JULGA
-- `deviation_read` (migration 28) só entrega evento em sombra a
-- `util.is_admin` — owner, hr e personnel. Uma policy mais frouxa aqui daria a
-- alguém veredito sobre evento que ele não pode ler; uma mais apertada criaria
-- um predicado que nenhuma outra policy do schema usa, e que a suíte teria de
-- sustentar sozinha. Autorizada pelo dono em 09/09/2026.
--
-- ⚠️ E O GRANT É O QUE DÁ DENTES À POLICY. Sem `grant ... to authenticated` a
-- policy autorizada seria decoração: todo `select` responderia `permission
-- denied` antes de a policy ser avaliada, os dois lados ficariam verdes pelo
-- mesmo motivo, e a asserção do `98` teria de ler texto de policy em vez de
-- contar linha. Os verbos concedidos são os de `app.deviation_event`
-- (`select`, `update`) mais `insert` — e `delete` fica de fora de propósito:
-- veredito revisto é `update`; veredito apagado é medição que ninguém audita.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create table if not exists app.deviation_adjudication (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references app.tenant(id) on delete cascade,
  --: UNIQUE é o grão: um indício tem no máximo um veredito vigente. `cascade`
  --: acompanha `app.justification`, que é a outra tabela que fala sobre um
  --: evento — desvio não se deleta (regra 6), então o caminho real desta
  --: cascata é a remoção do tenant inteiro.
  deviation_event_id uuid not null unique references app.deviation_event(id) on delete cascade,
  verdict            text not null,
  --: Nulo quando o veredito é verdadeiro positivo — e obrigatório quando não é.
  --: A trava está em `deviation_adjudication_cause_required`, abaixo.
  cause              text,
  --: O que o julgador viu. Livre de propósito: é daqui que sai a causa que o
  --: vocabulário ainda não tem nome para.
  note               text,
  --: O par de `app.justification`: `author_user_id` quando houver tela, e
  --: `author_name` para a planilha, que não tem sessão autenticada. Um dos dois
  --: sempre existe, e nenhum dos dois é a identidade do outro.
  author_user_id     uuid references auth.users(id),
  author_name        text,
  --: Uma marca de tempo só. Rever um veredito reescreve a linha e esta data —
  --: o "quando julgou a primeira vez" não sustenta nenhuma decisão, e guardá-lo
  --: sugeriria um histórico que esta tabela não mantém.
  adjudicated_at     timestamptz not null default now(),
  constraint deviation_adjudication_verdict_vocab
    check (verdict in ('true_positive','false_positive')),
  constraint deviation_adjudication_cause_vocab
    check (cause is null or cause in (
      'wrong_schedule','wrong_tolerance','engine_bug',
      'exempt_from_punching','justified_outside_system')),
  constraint deviation_adjudication_cause_required
    check ((verdict = 'false_positive') = (cause is not null))
);

comment on table app.deviation_adjudication is
  'Veredito humano sobre um indício do modo sombra — a verdade de referência do '
  'G4 desde 09/09/2026, quando a medição mostrou que a origem não tem veredito a '
  'dar (ver docs/DECISAO-VERDADE-DE-REFERENCIA-G4.md). Um veredito por indício, '
  'nunca por dia: a taxa do gate é por evento e um dia comporta os dois. Falso '
  'positivo exige causa; verdadeiro positivo a proíbe. Rever é update.';

comment on column app.deviation_adjudication.cause is
  'Só quando verdict = false_positive. wrong_schedule / wrong_tolerance / '
  'engine_bug são as três da SPEC-TECNICA §3.5; exempt_from_punching (não bate '
  'ponto por função) e justified_outside_system (combinado fora do Secullum) '
  'foram acrescentadas pela medição de 09/09/2026 e são as que o espelho jamais '
  'poderia informar.';

alter table app.deviation_adjudication enable row level security;

revoke all on table app.deviation_adjudication from anon, authenticated;
grant select, insert, update on table app.deviation_adjudication to authenticated;
grant select, insert, update on table app.deviation_adjudication to service_role;

drop policy if exists deviation_adjudication_admin on app.deviation_adjudication;
create policy deviation_adjudication_admin on app.deviation_adjudication
  for all to authenticated
  using      (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- Prova viva
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant     uuid;
  v_company    uuid;
  v_employee   uuid;
  v_event      uuid;
  v_barrou     boolean;
  v_sintetico  boolean := false;
begin
  -- 1. A RLS está ligada. Sem isto o resto da prova mediria uma tabela aberta.
  if not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app' and c.relname = 'deviation_adjudication'
       and c.relrowsecurity
  ) then
    raise exception 'app.deviation_adjudication sem RLS';
  end if;

  -- 2. A policy existe e é `for all` — as duas expressões, porque num insert
  --    quem decide é o `with check` e afrouxar só ele passaria despercebido.
  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'deviation_adjudication'
       and policyname = 'deviation_adjudication_admin'
       and cmd = 'ALL' and qual is not null and with_check is not null
  ) then
    raise exception 'deviation_adjudication_admin não existe, ou não tem using e with check';
  end if;

  -- 3. `delete` NÃO foi concedido. Este é o verbo cuja ausência é a decisão.
  if has_table_privilege('authenticated', 'app.deviation_adjudication', 'delete') then
    raise exception 'authenticated recebeu delete — veredito apagado é medição que ninguém audita';
  end if;

  -- 4. O positivo: os verbos que a policy precisa para não ser decoração.
  if not (has_table_privilege('authenticated', 'app.deviation_adjudication', 'select')
      and has_table_privilege('authenticated', 'app.deviation_adjudication', 'insert')
      and has_table_privilege('authenticated', 'app.deviation_adjudication', 'update')) then
    raise exception 'authenticated não tem select/insert/update — a policy autorizada ficaria inerte';
  end if;

  -- ⛔ A CADEIA SINTÉTICA EXISTE PORQUE A ALTERNATIVA ERA FALSO VERDE
  -- A primeira versão desta prova dizia "sem deviation_event: pulada" e seguia
  -- verde. Medido em 09/09/2026 no banco descartável do `db-test`: é EXATAMENTE
  -- esse o estado na hora em que a migration roda — as migrations vêm antes do
  -- seed, então os itens 5 a 8, que são a garantia inteira desta tabela, nunca
  -- corriam. Um `raise notice` não é uma prova; é uma prova que não aconteceu.
  --
  -- Então, quando não há evento, a prova constrói o mínimo para existir um e o
  -- desfaz. Nada persiste em nenhum dos dois caminhos: se algo aqui levantar,
  -- o bloco inteiro reverte; se nada levantar, os deletes do fim limpam.
  select id into v_event from app.deviation_event order by detected_at limit 1;
  if v_event is not null then
    select tenant_id into v_tenant from app.deviation_event where id = v_event;
  else
    -- O slug obedece `tenant_slug_check` (^[a-z0-9-]{2,40}$) — medido em
    -- 09/09/2026, quando `__migration_37__` foi recusado por ele.
    insert into app.tenant (slug, name)
    values ('migration-37-prova', 'Prova da migration 37')
    returning id into v_tenant;

    insert into app.company (tenant_id, legal_name)
    values (v_tenant, '__migration_37__')
    returning id into v_company;

    insert into app.employee (tenant_id, company_id, name)
    values (v_tenant, v_company, '__migration_37__')
    returning id into v_employee;

    -- `type` é FK para app.deviation_type: o código tem de existir de verdade,
    -- e é a migration 05 que o semeia.
    insert into app.deviation_event
      (tenant_id, employee_id, company_id, reference_date, type, minutes, mode)
    values (v_tenant, v_employee, v_company, current_date,
            (select code from app.deviation_type order by code limit 1), 10, 'shadow')
    returning id into v_event;

    v_sintetico := true;
  end if;

  -- 5. Falso positivo SEM causa é recusado.
  v_barrou := false;
  begin
    insert into app.deviation_adjudication (tenant_id, deviation_event_id, verdict)
    values (v_tenant, v_event, 'false_positive');
  exception when check_violation then
    v_barrou := true;
  end;
  if not v_barrou then
    raise exception 'falso positivo sem causa foi aceito — o passo 3 da §3.5 fica sem insumo';
  end if;

  -- 6. Verdadeiro positivo COM causa é recusado. A outra metade da mesma
  --    constraint: sem ela, causa viraria ruído na contagem por defeito.
  v_barrou := false;
  begin
    insert into app.deviation_adjudication (tenant_id, deviation_event_id, verdict, cause)
    values (v_tenant, v_event, 'true_positive', 'engine_bug');
  exception when check_violation then
    v_barrou := true;
  end;
  if not v_barrou then
    raise exception 'verdadeiro positivo com causa foi aceito';
  end if;

  -- 7. E o legítimo passa — sem este, os dois de cima ficariam verdes numa
  --    tabela que recusa tudo.
  insert into app.deviation_adjudication (tenant_id, deviation_event_id, verdict, cause, author_name)
  values (v_tenant, v_event, 'false_positive', 'exempt_from_punching', '__migration_37__');

  -- 8. Um segundo veredito para o MESMO indício é recusado: o grão é o evento.
  v_barrou := false;
  begin
    insert into app.deviation_adjudication (tenant_id, deviation_event_id, verdict)
    values (v_tenant, v_event, 'true_positive');
  exception when unique_violation then
    v_barrou := true;
  end;
  if not v_barrou then
    raise exception 'dois vereditos para o mesmo indício foram aceitos — a taxa passaria a contar duas vezes';
  end if;

  delete from app.deviation_adjudication where author_name = '__migration_37__';

  -- Na ordem inversa da criação: o `cascade` do tenant resolveria, mas apagar
  -- tenant para limpar prova é gesto largo demais para viver numa migration que
  -- roda em banco de cliente.
  if v_sintetico then
    delete from app.deviation_event where id = v_event;
    delete from app.employee        where id = v_employee;
    delete from app.company         where id = v_company;
    delete from app.tenant          where id = v_tenant;
  end if;

  raise notice 'OK: um veredito por indício, causa amarrada ao veredito, e delete fora do alcance.';
end $$;
