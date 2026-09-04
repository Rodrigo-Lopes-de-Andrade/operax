import { ArrowLeft, UserX } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { EmployeePhoto } from "@/components/rh/employee-photo";
import { CadastroForm } from "@/components/rh/cadastro-form";
import { ProvenanceBlock } from "@/components/rh/provenance";
import { Timeline, type Band } from "@/components/rh/timeline";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { pageTitle } from "@/lib/brand";
import { loadFreshness } from "@/lib/freshness";
import { loadIdentity, reachesHr } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";
import { formatDayShort } from "@/lib/ponto/format";
import {
  AGREEMENT_STATUS_LABEL,
  AGREEMENT_TYPE_LABEL,
  DOCUMENT_STATUS_LABEL,
  EMPLOYMENT_LABEL,
  EXAM_RESULT_LABEL,
  EXAM_TYPE_LABEL,
  LEAVE_LABEL,
  MOVEMENT_LABEL,
  SOURCE_LABEL,
  STATUS_LABEL,
  TAB_LABEL,
  label,
} from "@/lib/rh/labels";
import { loadHrEmployee, type HrEmployeeDetail } from "@/lib/rh/queries";
import { availableTabs } from "@/lib/rh/tabs";
import {
  COLABORADORES_PATH,
  employeeHref,
  parseTab,
  type Tab,
} from "@/lib/rh/url";

export const metadata: Metadata = {
  title: pageTitle("Colaborador"),
};

const CURRENCY = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

/**
 * O detalhe em abas por domínio.
 *
 * A aba de um domínio que este papel não alcança **não existe no DOM**. Não é
 * uma aba desabilitada, não é um cadeado, não é um texto explicando que falta
 * permissão: o backend não manda o bloco, e o que não veio não vira aba. Um
 * cadeado com o rótulo "Remuneração" informa que existe remuneração — o que é
 * exatamente o que o domínio sensível existe para não informar.
 *
 * Editar segue o mesmo princípio, um grau abaixo: `can_write` vem do banco, e
 * sem ele o formulário não é montado. Aqui esconder é cortesia, não segurança —
 * a API recusa a escrita de qualquer jeito.
 */
export default async function ColaboradorRhPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!reachesHr(identity?.role)) {
    notFound();
  }

  const { id } = await params;
  const tab = parseTab(await searchParams);
  const [detail, freshness] = await Promise.all([
    loadHrEmployee(id),
    loadFreshness(),
  ]);

  if (!detail) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={UserX}
          tone="neutral"
          title="Colaborador não encontrado"
          description="Ou a pessoa não existe, ou está fora do seu acompanhamento. As duas respostas são a mesma de propósito."
        >
          <Link
            href={COLABORADORES_PATH}
            className="text-brand-strong text-sm font-bold underline"
          >
            Voltar para a lista
          </Link>
        </EmptyState>
      </Card>
    );
  }

  const tabs = availableTabs(detail);
  const active = tabs.some((item) => item.value === tab) ? tab : tabs[0].value;
  const { employee } = detail;

  return (
    <div className="flex flex-col gap-4">
      <Link
        href={COLABORADORES_PATH}
        className="text-ink-muted hover:text-ink flex w-fit items-center gap-1.5 text-xs font-bold"
      >
        <ArrowLeft size={14} aria-hidden />
        Colaboradores
      </Link>

      <Card className="flex flex-wrap items-start justify-between gap-4 px-5 py-4">
        <div className="flex items-start gap-4">
          <EmployeePhoto
            employeeId={employee.employee_id}
            name={employee.name}
            photo={detail.photo}
          />
        </div>
        <div className="flex flex-col gap-1">
          <h1 className="text-ink text-xl font-extrabold">{employee.name}</h1>
          <p className="text-ink-muted text-sm">
            {employee.registration_number ?? "sem matrícula"}
            {employee.hr_code ? ` · ID RH ${employee.hr_code}` : ""}
            {employee.unit_name ? ` · ${employee.unit_name}` : ""}
            {employee.cargo ? ` · ${employee.cargo}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={employee.status === "active" ? "good" : "neutral"} dot>
            {label(STATUS_LABEL, employee.status)}
          </Badge>
          {employee.employment_type ? (
            <Badge tone="neutral">
              {label(EMPLOYMENT_LABEL, employee.employment_type)}
            </Badge>
          ) : null}
        </div>
      </Card>

      <Card>
        <Tabs
          items={tabs.map((item) => ({
            ...item,
            href: employeeHref(id, item.value),
          }))}
          value={active}
          label="Domínios do colaborador"
        />
        <div className="px-5 py-5">
          {renderTab(active, detail, freshness?.lastSyncAt ?? null)}
        </div>
      </Card>
    </div>
  );
}

function renderTab(
  tab: Tab,
  detail: HrEmployeeDetail,
  syncedAt: string | null,
) {
  const { employee } = detail;

  if (tab === "cadastro") {
    return (
      <div className="flex flex-col gap-6">
        <ProvenanceBlock fields={detail.sync_fields} syncedAt={syncedAt} />
        <section className="flex flex-col gap-3">
          <h3 className="text-ink text-sm font-extrabold">É do RH</h3>
          {detail.can_write && detail.editable_fields.length > 0 ? (
            <CadastroForm
              employeeId={employee.employee_id}
              editable={detail.editable_fields}
              enums={detail.enums}
              initial={{
                hr_code: employee.hr_code ?? "",
                employment_type: employee.employment_type ?? "",
                ctps: detail.pii?.ctps ?? "",
              }}
            />
          ) : (
            <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
              <Field name="ID RH" value={employee.hr_code} />
              <Field
                name="Regime"
                value={label(EMPLOYMENT_LABEL, employee.employment_type)}
              />
              {detail.pii ? (
                <Field name="CTPS" value={detail.pii.ctps} />
              ) : null}
            </dl>
          )}
        </section>
      </div>
    );
  }

  if (tab === "posicao") {
    return (
      <Timeline
        employeeId={employee.employee_id}
        kind="position"
        canWrite={detail.can_write}
        emptyText="Nenhuma vigência de cargo registrada."
        bands={detail.positions.map<Band>((band) => ({
          effective_from: band.effective_from,
          effective_to: band.effective_to,
          headline: band.cargo,
          note: band.unit_name,
        }))}
      />
    );
  }

  if (tab === "pessoais" && detail.pii) {
    return (
      <div className="flex flex-col gap-6">
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field name="CPF" value={detail.pii.cpf} />
          <Field name="RG" value={detail.pii.rg} />
          <Field name="PIS" value={detail.pii.pis} />
          <Field name="CTPS" value={detail.pii.ctps} />
          <Field
            name="Nascimento"
            value={
              detail.pii.birth_date
                ? formatDayShort(detail.pii.birth_date)
                : null
            }
          />
          <Field name="Telefone" value={detail.pii.phone} />
          <Field name="E-mail pessoal" value={detail.pii.personal_email} />
          <Field name="Mãe" value={detail.pii.mother_name} />
          <Field name="Pai" value={detail.pii.father_name} />
        </dl>
        <section className="flex flex-col gap-3">
          <h3 className="text-ink text-sm font-extrabold">Documentos</h3>
          <Table
            columns={DOCUMENT_COLUMNS}
            density="compact"
            caption="Documentos do colaborador"
            rows={(detail.documents ?? []).map((doc, index) => ({
              id: `${doc.type_name}-${index}`,
              cells: {
                tipo: doc.type_name,
                emissao: doc.issued_on ? formatDayShort(doc.issued_on) : "—",
                validade: doc.valid_until
                  ? formatDayShort(doc.valid_until)
                  : "—",
                situacao: label(DOCUMENT_STATUS_LABEL, doc.status),
              },
            }))}
            empty={<Vazio texto="Nenhum documento vigente registrado." />}
          />
        </section>
      </div>
    );
  }

  if (tab === "saude" && detail.exams) {
    return (
      <div className="flex flex-col gap-3">
        {/* Regra 10: aptidão e validade, nunca diagnóstico. Não há coluna para
            CID em lugar nenhum — nem aqui, nem na tabela, nem no template. */}
        <p className="text-ink-muted text-xs text-pretty">
          O ASO guarda aptidão e validade. Diagnóstico, CID e descrição de
          restrição não são capturados em lugar nenhum do sistema.
        </p>
        <Table
          columns={EXAM_COLUMNS}
          density="compact"
          caption="Exames ocupacionais"
          rows={detail.exams.map((exam, index) => ({
            id: `${exam.performed_on}-${index}`,
            cells: {
              tipo: label(EXAM_TYPE_LABEL, exam.type),
              realizado: formatDayShort(exam.performed_on),
              validade: exam.valid_until
                ? formatDayShort(exam.valid_until)
                : "—",
              resultado: label(EXAM_RESULT_LABEL, exam.result),
            },
          }))}
          empty={<Vazio texto="Nenhum exame registrado." />}
        />
      </div>
    );
  }

  if (tab === "remuneracao" && detail.compensation) {
    return (
      <Timeline
        employeeId={employee.employee_id}
        kind="compensation"
        canWrite={detail.can_write}
        emptyText="Nenhuma vigência de salário registrada."
        bands={detail.compensation.map<Band>((band) => ({
          effective_from: band.effective_from,
          effective_to: band.effective_to,
          headline: CURRENCY.format(Number(band.salary)),
          note: band.reason,
        }))}
      />
    );
  }

  if (tab === "afastamentos") {
    return (
      <Table
        columns={LEAVE_COLUMNS}
        density="compact"
        caption="Afastamentos"
        rows={detail.leaves.map((leave, index) => ({
          id: `${leave.start_date}-${index}`,
          cells: {
            categoria: label(LEAVE_LABEL, leave.category),
            inicio: formatDayShort(leave.start_date),
            fim: leave.end_date ? formatDayShort(leave.end_date) : "em aberto",
            origem: label(SOURCE_LABEL, leave.source),
          },
        }))}
        empty={<Vazio texto="Nenhum afastamento registrado." />}
      />
    );
  }

  if (tab === "movimentacoes") {
    return (
      <Table
        columns={MOVEMENT_COLUMNS}
        density="compact"
        caption="Movimentações"
        rows={detail.movements.map((movement, index) => ({
          id: `${movement.event_date}-${index}`,
          cells: {
            tipo: label(MOVEMENT_LABEL, movement.type),
            data: formatDayShort(movement.event_date),
            unidade: movement.unit_name ?? "—",
            nota: movement.notes ?? "—",
          },
        }))}
        empty={<Vazio texto="Nenhuma movimentação registrada." />}
      />
    );
  }

  if (tab === "acordos" && detail.agreements) {
    return (
      <Table
        columns={AGREEMENT_COLUMNS}
        density="compact"
        caption="Acordos financeiros"
        rows={detail.agreements.map((agreement) => ({
          id: agreement.id,
          cells: {
            tipo: label(AGREEMENT_TYPE_LABEL, agreement.type),
            descricao: agreement.description ?? "—",
            total: CURRENCY.format(Number(agreement.total_amount)),
            parcelas: `${agreement.pending_installments} de ${agreement.installment_count} pendente(s)`,
            situacao: label(AGREEMENT_STATUS_LABEL, agreement.status),
          },
        }))}
        empty={<Vazio texto="Nenhum acordo registrado." />}
      />
    );
  }

  return null;
}

function Field({ name, value }: { name: string; value: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        {name}
      </dt>
      <dd className="text-ink text-sm font-semibold">{value ?? "—"}</dd>
    </div>
  );
}

function Vazio({ texto }: { texto: string }) {
  return <p className="text-ink-faint py-4 text-sm">{texto}</p>;
}

const DOCUMENT_COLUMNS: Column[] = [
  { key: "tipo", label: "Documento" },
  { key: "emissao", label: "Emissão" },
  { key: "validade", label: "Validade" },
  { key: "situacao", label: "Situação" },
];

const EXAM_COLUMNS: Column[] = [
  { key: "tipo", label: "Exame" },
  { key: "realizado", label: "Realizado" },
  { key: "validade", label: "Validade" },
  { key: "resultado", label: "Resultado" },
];

const LEAVE_COLUMNS: Column[] = [
  { key: "categoria", label: "Categoria" },
  { key: "inicio", label: "Início" },
  { key: "fim", label: "Fim" },
  { key: "origem", label: "Origem" },
];

const MOVEMENT_COLUMNS: Column[] = [
  { key: "tipo", label: "Movimentação" },
  { key: "data", label: "Data" },
  { key: "unidade", label: "Unidade" },
  { key: "nota", label: "Nota" },
];

const AGREEMENT_COLUMNS: Column[] = [
  { key: "tipo", label: "Tipo" },
  { key: "descricao", label: "Descrição" },
  { key: "total", label: "Total", align: "right" },
  { key: "parcelas", label: "Parcelas" },
  { key: "situacao", label: "Situação" },
];
