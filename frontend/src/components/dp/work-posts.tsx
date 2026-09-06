"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MapPinned, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Badge, Chip } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import { TextField } from "@/components/ui/text-field";
import { ApiError, requestApiAsUser } from "@/lib/api";
import type { WorkPostList, WorkPostRow } from "@/lib/dp/queries";

export type UnitChoice = { id: string; name: string };

const COLUMNS: Column[] = [
  { key: "codigo", label: "Código", mono: true, width: "16%" },
  { key: "nome", label: "Posto" },
  { key: "escala", label: "Escala vinculada", width: "24%" },
  { key: "situacao", label: "Situação", width: "14%" },
  { key: "acao", label: "", align: "right", width: "18%" },
];

/**
 * Quadro de Postos — unidade + código, que é a identidade inteira do posto.
 *
 * ⚠️ A COLUNA "ESCALA VINCULADA" NÃO TEM DADO, E A TELA DIZ ISSO
 * O elo posto → escala é um `secullum_schedule_id` e ficou **de fora** da
 * migration do S1 de propósito (SPEC-DP §1c): ele entra em migration própria,
 * depois que alguém ler o grão de `app.schedule_rotation_map`. Enquanto isso a
 * coluna mostra um chip tracejado, que é o vocabulário do produto para "ainda
 * não é fato", e a nota ao lado diz por quê. Um traço mudo aqui seria lido como
 * "este posto ficou sem escala"; um nome inventado seria pior.
 *
 * ⛔ NÃO EXISTE APAGAR
 * Posto sai de operação com `active = false`, porque o ciclo de vale transporte
 * do mês passado aponta para ele. É a regra 6 do projeto estendida ao cadastro,
 * e é por isso que a ação da linha é "Tirar de operação" e não uma lixeira.
 */
export function WorkPosts({
  screen,
  units,
}: {
  screen: WorkPostList;
  units: UnitChoice[];
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const porUnidade = groupByUnit(screen.rows);

  async function toggle(post: WorkPostRow) {
    setBusy(post.id);
    setError(null);

    try {
      await requestApiAsUser(`/dp/postos/${post.id}`, {
        method: "PATCH",
        body: { active: !post.active },
      });
      router.refresh();
    } catch (caught) {
      setError(mensagem(caught, "Não consegui alterar o posto. Nada mudou."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink-muted max-w-3xl text-sm text-pretty">
        O posto é <strong className="text-ink">unidade + código</strong> — é
        assim que a rotina de vale transporte encontra a escala de quem trabalha
        nele. A coluna <strong className="text-ink">Escala vinculada</strong>{" "}
        está vazia para todos: o elo entre posto e escala ainda não existe no
        banco e entra em uma migração própria, mais adiante. Nenhum posto tem
        escala vinculada hoje.
      </p>

      {error ? <Alert>{error}</Alert> : null}

      {screen.can_write ? (
        <Card>
          <CardHeader
            title="Novo posto"
            note="O código é único dentro da unidade. Repetir um código existente é recusado — e a recusa vem do banco, não daqui."
            action={
              <Button onClick={() => setCreating((open) => !open)}>
                <Plus size={15} aria-hidden />
                {creating ? "Fechar" : "Novo posto"}
              </Button>
            }
          />
          {creating ? (
            <NewPostForm
              units={units}
              onDone={() => {
                setCreating(false);
                router.refresh();
              }}
            />
          ) : null}
        </Card>
      ) : null}

      {porUnidade.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={MapPinned}
            tone="neutral"
            title="Nenhum posto cadastrado"
            description={
              screen.can_write
                ? "O Quadro de Postos começa vazio. Cadastre o primeiro posto da unidade acima."
                : "As unidades que você acompanha ainda não têm posto no Quadro."
            }
          />
        </Card>
      ) : null}

      {porUnidade.map(([unitName, posts]) => (
        <Card key={unitName}>
          <CardHeader
            eyebrow="Unidade"
            title={unitName}
            note={`${posts.length} posto(s) no Quadro`}
          />
          <Table
            columns={COLUMNS}
            caption={`Postos da unidade ${unitName}`}
            rows={posts.map((post) => ({
              id: post.id,
              cells: {
                codigo: post.code,
                nome: post.name ?? (
                  <span className="text-ink-faint">sem nome</span>
                ),
                escala: <Chip>não vinculada</Chip>,
                situacao: (
                  <Badge tone={post.active ? "good" : "neutral"} dot>
                    {post.active ? "Em operação" : "Fora de operação"}
                  </Badge>
                ),
                acao: screen.can_write ? (
                  <button
                    type="button"
                    onClick={() => toggle(post)}
                    disabled={busy === post.id}
                    className="text-brand-strong text-xs font-bold underline disabled:opacity-60"
                  >
                    {busy === post.id
                      ? "Gravando…"
                      : post.active
                        ? "Tirar de operação"
                        : "Voltar à operação"}
                  </button>
                ) : null,
              },
            }))}
          />
        </Card>
      ))}
    </div>
  );
}

const schema = z.object({
  unit_id: z.string().min(1, "Escolha a unidade do posto."),
  code: z
    .string()
    .trim()
    .min(1, "Informe o código do posto.")
    .max(40, "O código cabe em 40 caracteres."),
  name: z.string().max(120, "O nome cabe em 120 caracteres.").optional(),
});

/** Unidade + código: o formulário é a constraint do banco, com as mesmas peças. */
function NewPostForm({
  units,
  onDone,
}: {
  units: UnitChoice[];
  onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, reset, formState } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { unit_id: units[0]?.id ?? "", code: "", name: "" },
  });

  const onSubmit = handleSubmit(async (valores) => {
    setError(null);

    try {
      await requestApiAsUser("/dp/postos", {
        method: "POST",
        body: {
          unit_id: valores.unit_id,
          code: valores.code.trim(),
          name: valores.name?.trim() || null,
        },
      });
      reset({ unit_id: valores.unit_id, code: "", name: "" });
      onDone();
    } catch (caught) {
      setError(mensagem(caught, "Não consegui cadastrar o posto."));
    }
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4 px-5 py-5"
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
            Unidade
          </span>
          <select
            aria-label="Unidade do posto"
            className="border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm"
            {...register("unit_id")}
          >
            {units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.name}
              </option>
            ))}
          </select>
        </label>
        <TextField
          id="posto-codigo"
          label="Código"
          placeholder="7703"
          error={formState.errors.code?.message}
          {...register("code")}
        />
        <TextField
          id="posto-nome"
          label="Nome (opcional)"
          placeholder="Portaria — turno A"
          error={formState.errors.name?.message}
          {...register("name")}
        />
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <Button type="submit" disabled={formState.isSubmitting}>
        {formState.isSubmitting ? "Cadastrando…" : "Cadastrar posto"}
      </Button>
    </form>
  );
}

/** Agrupa por unidade preservando a ordem que a API entregou. */
function groupByUnit(rows: WorkPostRow[]): [string, WorkPostRow[]][] {
  const grupos = new Map<string, WorkPostRow[]>();

  for (const row of rows) {
    const atual = grupos.get(row.unit_name);

    if (atual) {
      atual.push(row);
    } else {
      grupos.set(row.unit_name, [row]);
    }
  }

  return [...grupos.entries()];
}

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}
