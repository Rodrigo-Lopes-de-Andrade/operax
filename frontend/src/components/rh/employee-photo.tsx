"use client";

import { useEffect, useState } from "react";

import { downloadApiAsUser } from "@/lib/api";

/**
 * A foto do colaborador na ficha — Caminho 2, domínio `pii`.
 *
 * Decidida em 04/09/2026 pelo dono, a pedido do cliente:
 * `docs/DECISAO-FOTO-DO-COLABORADOR.md`. O sistema que o cliente usa hoje já
 * exibe a foto na mesma ficha, para o mesmo DP — isto reproduz uma exposição
 * que já existe, não cria uma nova.
 *
 * ⛔ **Uma pessoa por vez, e só na ficha aberta.** Este componente busca a
 * imagem por requisição individual. Não existe versão de lista, e o metadado da
 * ficha não carrega bytes: 176 rostos numa listagem é exportação de biometria
 * com outro nome (§5 da decisão).
 *
 * ⛔ **A URL do objeto é revogada ao desmontar.** Sem isso o `blob:` sobrevive
 * à navegação e vira link que atravessa a sessão, que é justamente o que a §5
 * proíbe.
 */
export function EmployeePhoto({
  employeeId,
  name,
  photo,
}: {
  employeeId: string;
  name: string;
  /** `null` quando o papel não alcança `pii` — aí nada é renderizado. */
  photo: {
    state: "ausente" | "pendente" | "disponivel";
    synced_at: string | null;
  } | null;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [falhou, setFalhou] = useState(false);
  const disponivel = photo?.state === "disponivel";

  useEffect(() => {
    if (!disponivel) return;
    let url: string | null = null;
    let vivo = true;

    (async () => {
      try {
        const { blob } = await downloadApiAsUser(
          `/rh/employees/${employeeId}/foto`,
          "foto",
        );
        url = URL.createObjectURL(blob);
        if (vivo) setSrc(url);
        else URL.revokeObjectURL(url);
      } catch {
        if (vivo) setFalhou(true);
      }
    })();

    return () => {
      vivo = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [employeeId, disponivel]);

  if (!photo) return null;

  return (
    <div className="flex items-center gap-3">
      <span className="bg-brand-soft/50 text-brand-strong relative flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-full text-lg font-extrabold">
        {src && !falhou ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob: de sessão, não asset
          <img
            src={src}
            alt={`Foto de ${name}`}
            className="size-full object-cover"
          />
        ) : (
          <span aria-hidden>{iniciais(name)}</span>
        )}
      </span>
      <p className="text-ink-muted text-xs">{legenda(photo, falhou)}</p>
    </div>
  );
}

/**
 * Os três estados do §6, e o motivo de serem três.
 *
 * Vazio sem explicação numa tela de identificação parece defeito. "Sem foto" e
 * "ainda não sincronizada" são situações diferentes, e quem olha a ficha precisa
 * saber qual das duas está vendo.
 *
 * E a idade do rosto é dado de tela, pela mesma disciplina de idade do dado que
 * vale no resto do produto: rosto de dois anos numa ficha de identificação é
 * pior que rosto nenhum, e só a data revela isso.
 */
function legenda(
  photo: { state: string; synced_at: string | null },
  falhou: boolean,
): string {
  if (falhou) return "não foi possível carregar a foto";
  if (photo.state === "ausente") return "sem foto no sistema de ponto";
  if (photo.state === "pendente") return "foto ainda não sincronizada";
  if (!photo.synced_at) return "foto sincronizada";
  return `foto de ${new Date(photo.synced_at).toLocaleDateString("pt-BR")}`;
}

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/);
  const primeira = partes[0]?.[0] ?? "";
  const ultima =
    partes.length > 1 ? (partes[partes.length - 1]?.[0] ?? "") : "";
  return (primeira + ultima).toUpperCase();
}
