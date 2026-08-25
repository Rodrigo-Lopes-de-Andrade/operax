import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column, type Row } from "@/components/ui/table";
import type {
  CompensationBand,
  EmployeeDocument,
  OccupationalExamRow,
} from "@/lib/colaborador/queries";
import { formatDayLong, formatDayShort } from "@/lib/ponto/format";

/**
 * The blocks that only some roles reach.
 *
 * Each one renders only when the backend sent it. A role that does not reach the
 * domain gets `null` and nothing appears — no padlock, no greyed card, and the
 * rest of the screen does not change layout. Someone who may not see salaries
 * should not learn from the interface that salaries are recorded.
 */

const EXAM_TYPE_LABEL: Record<string, string> = {
  pre_employment: "Admissional",
  periodic: "Periódico",
  exit: "Demissional",
  return_to_work_exam: "Retorno ao trabalho",
  job_change: "Mudança de função",
};

const EXAM_RESULT: Record<string, { label: string; tone: Tone }> = {
  fit: { label: "Apto", tone: "good" },
  unfit: { label: "Inapto", tone: "bad" },
  fit_with_restriction: { label: "Apto com restrição", tone: "alert" },
};

const COMPENSATION_COLUMNS: Column[] = [
  { key: "desde", label: "Desde", width: "140px", noWrap: true },
  { key: "motivo", label: "Motivo" },
  {
    key: "valor",
    label: "Valor",
    align: "right",
    numeric: true,
    width: "140px",
  },
];

const DOCUMENT_COLUMNS: Column[] = [
  { key: "tipo", label: "Documento" },
  {
    key: "vencimento",
    label: "Vencimento",
    align: "right",
    numeric: true,
    width: "160px",
  },
];

const EXAM_COLUMNS: Column[] = [
  { key: "tipo", label: "Exame" },
  { key: "realizado", label: "Realizado", numeric: true, width: "120px" },
  {
    key: "validade",
    label: "Validade",
    align: "right",
    numeric: true,
    width: "160px",
  },
];

const CURRENCY = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

export function CompensationCard({ bands }: { bands: CompensationBand[] }) {
  const rows: Row[] = bands.map((band) => ({
    id: band.effective_from,
    cells: {
      desde: formatDayLong(band.effective_from),
      motivo: band.reason,
      valor: (
        <span className="text-ink font-bold">
          {CURRENCY.format(Number(band.salary))}
        </span>
      ),
    },
  }));

  return (
    <Card>
      <CardHeader eyebrow="Domínio sensível" title="Histórico de remuneração" />
      <Table
        columns={COMPENSATION_COLUMNS}
        rows={rows}
        density="compact"
        caption="Remuneração"
      />
    </Card>
  );
}

export function DocumentsCard({
  documents,
  exams,
}: {
  documents: EmployeeDocument[] | null;
  exams: OccupationalExamRow[] | null;
}) {
  return (
    <Card>
      {/* O titulo nomeia so o que a funcao recebeu: prometer "e exames" a quem
          nao alcanca o dominio de saude ja conta que exames existem. */}
      <CardHeader
        eyebrow="Domínio sensível"
        title={
          exams
            ? documents
              ? "Documentos e exames"
              : "Exames ocupacionais"
            : "Documentos"
        }
      />

      {documents ? (
        <Table
          columns={DOCUMENT_COLUMNS}
          rows={documents.map((document, index) => ({
            id: `${document.type_name}-${index}`,
            cells: {
              tipo: document.type_name,
              vencimento: <Expiry date={document.valid_until} />,
            },
          }))}
          density="compact"
          caption="Documentos"
        />
      ) : null}

      {exams ? (
        <Table
          columns={EXAM_COLUMNS}
          rows={exams.map((exam) => ({
            id: exam.performed_on,
            cells: {
              tipo: (
                <span className="flex flex-wrap items-center gap-2">
                  {EXAM_TYPE_LABEL[exam.type] ?? exam.type}
                  {exam.result ? (
                    <Badge tone={EXAM_RESULT[exam.result]?.tone ?? "neutral"}>
                      {EXAM_RESULT[exam.result]?.label ?? exam.result}
                    </Badge>
                  ) : null}
                </span>
              ),
              realizado: formatDayShort(exam.performed_on),
              validade: <Expiry date={exam.valid_until} />,
            },
          }))}
          density="compact"
          caption="Exames ocupacionais"
        />
      ) : null}

      {/* O que o produto guarda de saúde, dito na tela: aptidão e validade. */}
      {exams ? (
        <p className="text-ink-faint border-line-subtle border-t px-5 py-3 text-xs">
          Exame ocupacional guarda apenas aptidão e validade. O FastPark não
          registra diagnóstico, CID nem descrição de restrição.
        </p>
      ) : null}
    </Card>
  );
}

function Expiry({ date }: { date: string | null }) {
  if (!date) {
    return <span className="text-ink-faint">sem vencimento</span>;
  }

  const days = Math.round(
    (Date.parse(date) - Date.parse(today())) / 86_400_000,
  );
  const tone: Tone = days < 0 ? "bad" : days <= 30 ? "alert" : "neutral";

  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-ink-body">{formatDayShort(date)}</span>
      {tone === "neutral" ? null : (
        <Badge tone={tone} dot>
          {days < 0 ? "vencido" : `${days} dias`}
        </Badge>
      )}
    </span>
  );
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}
