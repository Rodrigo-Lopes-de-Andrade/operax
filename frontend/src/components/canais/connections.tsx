import { MessageSquareOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { label, META_STATUS_LABEL, PROVIDER_LABEL } from "@/lib/canais/labels";
import type {
  BlockedAlertRule,
  ChannelCapabilities,
  ConnectionsScreen,
} from "@/lib/canais/queries";
import { formatNumber } from "@/lib/ponto/format";

/**
 * A frase de cada regra presa — os três casos de `BlockedAlertRule`, e nenhum
 * nulo é "está tudo bem".
 *
 * O caso 2 diz "não existe ou está inativo" porque a resposta não distingue os
 * dois: o `left join` filtra por `m.active` e ambos caem no mesmo `m.id is
 * null`. Fingir que distingue mandaria a pessoa procurar um template que está
 * lá, desligado.
 */
function BlockedRule({ rule }: { rule: BlockedAlertRule }) {
  const name = <strong className="text-ink">{rule.rule_name}</strong>;

  if (rule.template_code === null) {
    return <>a regra {name} é de WhatsApp e não aponta para template nenhum.</>;
  }

  const code = (
    <code className="text-ink font-mono text-xs">{rule.template_code}</code>
  );

  if (rule.meta_status === null) {
    return (
      <>
        a regra {name} aponta para o template {code}, que não existe ou está
        inativo neste cliente.
      </>
    );
  }

  return (
    <>
      a regra {name} aponta para o template {code}, que está{" "}
      <strong className="text-ink">
        {label(META_STATUS_LABEL, rule.meta_status)}
      </strong>{" "}
      na Meta.
    </>
  );
}

/**
 * O que o canal exige, dito pelas flags e nunca pelo nome.
 *
 * As duas famílias de restrição são dados que o backend calculou da matriz:
 * `requires_templates` é a Meta proibindo, `ban_risk` é o WhatsApp banindo. A
 * matriz garante que nunca coexistem; aqui cada uma é lida por si, e se um dia
 * as duas chegarem juntas a tela mostra as duas em vez de esconder uma.
 */
export function Requirements({
  capabilities,
}: {
  capabilities: ChannelCapabilities;
}) {
  return (
    <ul className="text-ink-muted flex flex-col gap-1 text-sm text-pretty">
      {capabilities.requires_templates ? (
        <li>
          Exige template aprovado pela Meta: uma regra ligada só entrega se o
          template dela estiver aprovado.
        </li>
      ) : null}
      {capabilities.ban_risk ? (
        <li>
          Aceita texto livre; volume alto pode levar a banimento do número, e o
          banimento não tem recurso.
        </li>
      ) : null}
    </ul>
  );
}

function rulesPhrase(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? "regra bloqueada" : "regras bloqueadas"}`;
}

/**
 * A tela de Conexões — o canal ativo, a saúde dele e o que está preso.
 *
 * Tudo aqui já era calculado por `fn_whatsapp_readiness` e invisível; a tela
 * lê e mostra, e não decide nada. Os três blocos:
 *
 * 1. **Canal** — o rótulo do provedor e o que ele exige, derivado de
 *    `capabilities`. Sem provedor, a tela inteira é o estado vazio: produção
 *    não tem canal nenhum, e é isso que ela tem a dizer no primeiro dia. Quem
 *    grava a credencial é o `<CredentialForm>`, logo abaixo na mesma página —
 *    este componente só lê, e o `<Requirements>` é compartilhado com ele para
 *    que o que cada canal exige seja dito de um jeito só.
 * 2. **Saúde** — `ready` como badge; quando não está pronto, os templates
 *    aprovados e a contagem de regras bloqueadas **como a API a deu**. Pronto
 *    é pronto e nada mais: `fn_whatsapp_readiness` define `ready` como zero
 *    regra bloqueada e ao menos um template aprovado, então a tela confia e
 *    não reconfere a contagem.
 * 3. **O que está preso** — uma linha por item de `blocked`, com a frase do
 *    caso certo. Ausente do DOM quando `ready`.
 *
 * ⚠️ `rules_blocked` E `blocked.length` SÃO DUAS LEITURAS DO MESMO FATO
 * A contagem é a que o gate de prontidão usa; a lista é o que há para mostrar.
 * A tela mostra a contagem da API e a lista que veio, e quando discordam diz
 * isso em vez de somar a lista e fingir que a API disse outro número.
 */
export function Connections({ screen }: { screen: ConnectionsScreen }) {
  if (screen.provider === null || screen.capabilities === null) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={MessageSquareOff}
          tone="neutral"
          title="Nenhum canal de WhatsApp configurado"
          description="Alertas por WhatsApp não têm por onde sair até haver um canal ativo neste cliente. O painel segue lendo os desvios; só o envio fica parado."
        />
      </Card>
    );
  }

  const { capabilities, blocked } = screen;
  const diverges = screen.rules_blocked !== blocked.length;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          eyebrow="Canal"
          title={label(PROVIDER_LABEL, screen.provider)}
          action={
            <Badge tone={capabilities.official ? "brand" : "neutral"}>
              {capabilities.official ? "Canal oficial" : "Canal não oficial"}
            </Badge>
          }
        />
        <div className="px-5 py-4">
          <Requirements capabilities={capabilities} />
        </div>
      </Card>

      <Card>
        <CardHeader
          eyebrow="Saúde"
          title={screen.ready ? "Canal pronto" : "Canal bloqueado"}
          action={
            <Badge tone={screen.ready ? "good" : "bad"} dot>
              {screen.ready ? "Pronto" : "Bloqueado"}
            </Badge>
          }
        />
        {screen.ready ? null : (
          <dl className="grid grid-cols-2 gap-4 px-5 py-4 text-sm">
            <div>
              <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
                Templates aprovados
              </dt>
              <dd className="text-ink mt-1 text-lg font-extrabold tabular-nums">
                {formatNumber(screen.templates_approved)} de{" "}
                {formatNumber(screen.templates_total)}
              </dd>
            </div>
            <div>
              <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
                Regras bloqueadas
              </dt>
              <dd className="text-ink mt-1 text-lg font-extrabold tabular-nums">
                {formatNumber(screen.rules_blocked)}
              </dd>
            </div>
          </dl>
        )}
      </Card>

      {screen.ready ? null : (
        <Card>
          <CardHeader
            eyebrow="Envio"
            title="O que está preso"
            note={rulesPhrase(screen.rules_blocked)}
          />
          <div className="flex flex-col gap-3 px-5 py-4">
            {blocked.length > 0 ? (
              <ul className="text-ink-muted flex flex-col gap-2 text-sm text-pretty">
                {blocked.map((rule, index) => (
                  <li
                    key={`${rule.rule_name}:${rule.template_code ?? ""}:${index}`}
                  >
                    <BlockedRule rule={rule} />
                  </li>
                ))}
              </ul>
            ) : capabilities.requires_templates &&
              screen.templates_approved === 0 ? (
              <p className="text-ink-muted text-sm text-pretty">
                Este canal exige template aprovado pela Meta, e nenhum está
                aprovado ({formatNumber(screen.templates_approved)} de{" "}
                {formatNumber(screen.templates_total)}). Nenhum alerta por
                WhatsApp sai até um template ser aprovado.
              </p>
            ) : (
              <p className="text-ink-muted text-sm text-pretty">
                A API marcou o canal como bloqueado e a lista de regras veio
                vazia.
              </p>
            )}
            {diverges ? (
              <p className="text-alert text-xs text-pretty">
                A contagem da API diz {rulesPhrase(screen.rules_blocked)} e a
                lista traz {formatNumber(blocked.length)}. As duas leituras
                estão aqui como vieram; a diferença é registrada no servidor.
              </p>
            ) : null}
          </div>
        </Card>
      )}
    </div>
  );
}
