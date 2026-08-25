import { Badge, Chip } from "@/components/ui/badge";
import { daysUntil, dueLabel, dueTone } from "@/lib/rh/labels";
import type { HrDueDate } from "@/lib/rh/queries";

/**
 * O prazo mais urgente da pessoa, com quantos dias faltam — ou faltaram.
 *
 * A data sozinha não serve: ninguém compara "10/09/2026" com hoje de cabeça no
 * meio de uma lista de 172 linhas. O que decide a cor é o sinal, não o tipo:
 * vencido é falha, vencendo em 30 dias é alerta, o resto é informação.
 *
 * Ausência aqui não quer dizer "em dia". Quer dizer que **nada foi encontrado**
 * dentro da janela e do que este usuário alcança: quem não tem o domínio de
 * saúde não vê ASO nenhum, e a célula não menciona que existe um.
 */
export function DueCell({
  due,
  today,
}: {
  due: HrDueDate | null;
  today: Date;
}) {
  if (!due) {
    return <Chip>nada na janela</Chip>;
  }

  const days = daysUntil(due.due_on, today);

  return (
    <span className="flex flex-col gap-1">
      <Badge tone={dueTone(days)} dot>
        {due.label}
      </Badge>
      <span className="text-ink-muted text-xs">{dueLabel(days)}</span>
    </span>
  );
}
