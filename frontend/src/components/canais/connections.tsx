import { BotOff, MessageSquareOff } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { TelegramConnection } from "@/components/canais/telegram-connection";
import { Badge, type Tone } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import {
  CHANNEL_LABEL,
  label,
  META_STATUS_LABEL,
  PROVIDER_LABEL,
} from "@/lib/canais/labels";
import type {
  BlockedAlertRule,
  ChannelCapabilities,
  ConnectionsScreen,
  TelegramChannel,
  WhatsAppChannel,
} from "@/lib/canais/queries";
import { TEMPLATES_PATH } from "@/lib/canais/url";
import { formatDayInTenantZone } from "@/lib/dp/format";
import { formatClock, formatNumber } from "@/lib/ponto/format";

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
 * As três famílias de restrição (SPEC-CANAIS §1.1) são dados que o backend
 * calculou da matriz: `requires_templates` é a Meta proibindo, `ban_risk` é o
 * WhatsApp banindo, `requires_recipient_opt_in` é o canal que não alcança
 * quem não abriu o bot. Cada uma é lida por si; se um dia duas chegarem
 * juntas a tela mostra as duas em vez de esconder uma. E um canal sem
 * nenhuma das três diz isso — silêncio aqui seria a leitura "canal sem
 * regra", que a SPEC chama de perigosa.
 */
export function Requirements({
  capabilities,
}: {
  capabilities: ChannelCapabilities;
}) {
  const none =
    !capabilities.requires_templates &&
    !capabilities.ban_risk &&
    !capabilities.requires_recipient_opt_in;

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
      {capabilities.requires_recipient_opt_in ? (
        <li>
          Só alcança quem aderiu pelo convite — quem não aderiu continua
          recebendo por WhatsApp.
        </li>
      ) : null}
      {none ? <li>Sem restrição declarada para este canal.</li> : null}
    </ul>
  );
}

function rulesPhrase(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? "regra bloqueada" : "regras bloqueadas"}`;
}

/** Dia e hora no fuso do tenant — a mesma forma da credencial e dos templates. */
function at(timestamp: string): string {
  return `${formatDayInTenantZone(timestamp)} às ${formatClock(timestamp)}`;
}

/** Um canal da tela: o título, e os cartões dele — ou o vazio dele. */
function ChannelRegion({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <h2 id={id} className="text-ink text-lg font-extrabold">
        {title}
      </h2>
      {children}
    </section>
  );
}

/**
 * Os cartões do canal de WhatsApp — o provedor ativo, a saúde dele e o que
 * está preso. Tudo aqui já era calculado por `fn_channel_readiness` e
 * invisível; a tela lê e mostra, e não decide nada.
 *
 * 1. **Canal** — o rótulo do provedor e o que ele exige, derivado de
 *    `capabilities`.
 * 2. **Saúde** — `ready` como badge; quando não está pronto, os templates
 *    aprovados e a contagem de regras bloqueadas **como a API a deu**. Pronto
 *    é pronto e nada mais: a função define `ready` como zero regra bloqueada
 *    e ao menos um template aprovado, então a tela confia e não reconfere.
 * 3. **O que está preso** — uma linha por item de `blocked`, com a frase do
 *    caso certo. Ausente do DOM quando `ready`.
 *
 * ⚠️ `rules_blocked` E `blocked.length` SÃO DUAS LEITURAS DO MESMO FATO
 * A contagem é a que o gate de prontidão usa; a lista é o que há para mostrar.
 * A tela mostra a contagem da API e a lista que veio, e quando discordam diz
 * isso em vez de somar a lista e fingir que a API disse outro número.
 */
function WhatsAppCards({ channel }: { channel: WhatsAppChannel }) {
  const { capabilities, blocked } = channel;
  const diverges = channel.rules_blocked !== blocked.length;

  return (
    <>
      <Card>
        <CardHeader
          eyebrow="Canal"
          title={label(PROVIDER_LABEL, channel.provider)}
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
          title={channel.ready ? "Canal pronto" : "Canal bloqueado"}
          action={
            <Badge tone={channel.ready ? "good" : "bad"} dot>
              {channel.ready ? "Pronto" : "Bloqueado"}
            </Badge>
          }
        />
        {channel.ready ? null : (
          <dl className="grid grid-cols-2 gap-4 px-5 py-4 text-sm">
            <div>
              <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
                Templates aprovados
              </dt>
              <dd className="text-ink mt-1 text-lg font-extrabold tabular-nums">
                {formatNumber(channel.templates_approved)} de{" "}
                {formatNumber(channel.templates_total)}
              </dd>
            </div>
            <div>
              <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
                Regras bloqueadas
              </dt>
              <dd className="text-ink mt-1 text-lg font-extrabold tabular-nums">
                {formatNumber(channel.rules_blocked)}
              </dd>
            </div>
          </dl>
        )}
      </Card>

      {channel.ready ? null : (
        <Card>
          <CardHeader
            eyebrow="Envio"
            title="O que está preso"
            note={rulesPhrase(channel.rules_blocked)}
          />
          <div className="flex flex-col gap-3 px-5 py-4">
            {blocked.length > 0 ? (
              <ul className="text-ink-muted flex flex-col gap-2 text-sm text-pretty">
                {blocked.map((rule, index) => (
                  <li
                    key={`${rule.rule_name}:${rule.template_code ?? ""}:${index}`}
                  >
                    <BlockedRule rule={rule} />{" "}
                    <Link
                      href={TEMPLATES_PATH}
                      className="text-brand-strong font-bold underline"
                    >
                      ver templates
                    </Link>
                  </li>
                ))}
              </ul>
            ) : capabilities.requires_templates &&
              channel.templates_approved === 0 ? (
              <p className="text-ink-muted text-sm text-pretty">
                Este canal exige template aprovado pela Meta, e nenhum está
                aprovado ({formatNumber(channel.templates_approved)} de{" "}
                {formatNumber(channel.templates_total)}). Nenhum alerta por
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
                A contagem da API diz {rulesPhrase(channel.rules_blocked)} e a
                lista traz {formatNumber(blocked.length)}. As duas leituras
                estão aqui como vieram; a diferença é registrada no servidor.
              </p>
            ) : null}
          </div>
        </Card>
      )}
    </>
  );
}

type Health = { tone: Tone; label: string };

/**
 * Os três estados que o vigia grava (SPEC §7), e o quarto que é a ausência
 * dele. `unknown` é "mediu e o Telegram não respondeu"; `null` é "nunca
 * mediu" — e os dois são neutros porque nenhum é um fato sobre o bot.
 */
const HEALTH: Record<NonNullable<TelegramChannel["health_status"]>, Health> = {
  connected: { tone: "good", label: "Conectado" },
  disconnected: { tone: "bad", label: "Desconectado" },
  unknown: { tone: "neutral", label: "Sem resposta" },
};

const NEVER_MEASURED: Health = { tone: "neutral", label: "Nunca medido" };

/**
 * Os cartões do bot de Telegram — o bot, a saúde com idade e o registro.
 *
 * 1. **Canal** — o `bot_username` como título (é o que identifica este bot;
 *    o rótulo do provedor é o fallback quando o Telegram não o informou) e
 *    o que o canal exige, derivado de `capabilities` (a terceira família da
 *    §1.1).
 * 2. **Saúde** — `ready` como badge; o estado que o vigia mediu, desde
 *    quando está nele e quando foi a última conferência (§7: conexão sem
 *    idade não é conexão); o `detail` que veio; e o registro no Telegram,
 *    com a ação que o cria ou remove — e nenhuma que o religue sozinha.
 */
function TelegramCards({
  channel,
  canWrite,
}: {
  channel: TelegramChannel;
  canWrite: boolean;
}) {
  const { capabilities } = channel;
  const health =
    channel.health_status === null
      ? NEVER_MEASURED
      : HEALTH[channel.health_status];

  return (
    <>
      <Card>
        <CardHeader
          eyebrow="Canal"
          title={
            channel.bot_username ?? label(PROVIDER_LABEL, channel.provider)
          }
          action={
            <Badge tone={capabilities.official ? "brand" : "neutral"}>
              {capabilities.official ? "Canal oficial" : "Canal não oficial"}
            </Badge>
          }
        />
        <div className="flex flex-col gap-3 px-5 py-4">
          {channel.bot_username ? null : (
            <p className="text-ink-muted text-sm">
              O Telegram não informou o nome de usuário do bot.
            </p>
          )}
          <Requirements capabilities={capabilities} />
        </div>
      </Card>

      <Card>
        <CardHeader
          eyebrow="Saúde"
          title={channel.ready ? "Bot pronto" : "Bot não pronto"}
          action={
            <Badge tone={channel.ready ? "good" : "bad"} dot>
              {channel.ready ? "Pronto" : "Não pronto"}
            </Badge>
          }
        />
        <div className="flex flex-col gap-4 px-5 py-4">
          <div className="flex flex-col gap-1.5">
            <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
              Conexão
            </p>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone={health.tone} dot>
                {health.label}
              </Badge>
              {channel.health_changed_at ? (
                <span className="text-ink-muted">
                  desde {at(channel.health_changed_at)}
                </span>
              ) : null}
            </div>
            {channel.health_checked_at ? (
              <p className="text-ink-faint text-xs">
                conferido em {at(channel.health_checked_at)}
              </p>
            ) : null}
            {channel.health_detail ? (
              <p className="text-ink-muted text-sm text-pretty">
                {channel.health_detail}
              </p>
            ) : null}
          </div>

          <TelegramConnection channel={channel} canWrite={canWrite} />
        </div>
      </Card>
    </>
  );
}

/**
 * A tela de Conexões — os dois canais, sempre os dois.
 *
 * WhatsApp e Telegram coexistem por desenho (SPEC-CANAIS §2.1 e §8: Telegram
 * para quem aderiu, WhatsApp para o resto), e a tela não pode sugerir que um
 * substitui o outro. Por isso cada canal tem a sua região, com o seu título
 * e o seu vazio, mesmo quando o outro está preenchido — e os dois nulos, que
 * é a produção hoje, são dois vazios e nenhum erro.
 *
 * Quem grava a credencial de cada canal é o `<CredentialForm>`, logo abaixo
 * na mesma página, um por canal — este componente só lê, e o `<Requirements>`
 * é compartilhado com ele para que o que cada canal exige seja dito de um
 * jeito só. `canWrite` chega a uma coisa: o registro do bot no Telegram.
 */
export function Connections({
  screen,
  canWrite,
}: {
  screen: ConnectionsScreen;
  /** `util.is_admin` — o único clique desta tela é o registro do bot. */
  canWrite: boolean;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-2 xl:items-start">
      <ChannelRegion id="channel-whatsapp" title={CHANNEL_LABEL.whatsapp}>
        {screen.whatsapp ? (
          <WhatsAppCards channel={screen.whatsapp} />
        ) : (
          <Card className="p-6">
            <EmptyState
              icon={MessageSquareOff}
              tone="neutral"
              title="Nenhum provedor de WhatsApp ativo"
              description="Alertas por WhatsApp não têm por onde sair até haver um provedor ativo neste cliente. O painel segue lendo os desvios; só o envio por este canal fica parado."
            />
          </Card>
        )}
      </ChannelRegion>

      <ChannelRegion id="channel-telegram" title={CHANNEL_LABEL.telegram}>
        {screen.telegram ? (
          <TelegramCards channel={screen.telegram} canWrite={canWrite} />
        ) : (
          <Card className="p-6">
            <EmptyState
              icon={BotOff}
              tone="neutral"
              title="Nenhum bot de Telegram ativo"
              description="Sem bot, ninguém adere e todo alerta continua saindo por WhatsApp. O token do bot entra no formulário de credencial do Telegram, abaixo."
            />
          </Card>
        )}
      </ChannelRegion>
    </div>
  );
}
