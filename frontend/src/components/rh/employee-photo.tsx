"use client";

import { useEffect, useState } from "react";

import { useRouter } from "next/navigation";

import { ApiError, downloadApiAsUser, uploadApiAsUser } from "@/lib/api";
import type { HrPhoto } from "@/lib/rh/queries";

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
  photo: HrPhoto | null;
}) {
  const router = useRouter();
  const [src, setSrc] = useState<string | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erroEnvio, setErroEnvio] = useState<string | null>(null);
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

  async function enviar(arquivo: File) {
    setEnviando(true);
    setErroEnvio(null);
    try {
      const form = new FormData();
      form.append("file", arquivo);
      await uploadApiAsUser(`/rh/employees/${employeeId}/foto`, form);
      // A ficha inteira recarrega: o estado da foto vem do servidor, e manter
      // uma segunda cópia aqui seria mais uma verdade para envelhecer.
      router.refresh();
    } catch (erro) {
      setErroEnvio(
        erro instanceof ApiError && erro.detail
          ? erro.detail
          : "Não foi possível enviar a foto.",
      );
    } finally {
      setEnviando(false);
    }
  }

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
      <div className="flex flex-col gap-0.5">
        <p className="text-ink-muted text-xs">{legenda(photo, falhou)}</p>
        {/* ⛔ A substituição pela origem é VISÍVEL, nunca silenciosa (§4-ter):
            trocar em silêncio o rosto que o DP escolheu é o erro que a revisão
            apontou. */}
        {photo.superseded ? (
          <p className="text-ink-muted text-xs">
            substituiu a foto enviada em{" "}
            {new Date(photo.superseded.uploaded_at).toLocaleDateString("pt-BR")}
            {photo.superseded.uploaded_by_name
              ? ` por ${photo.superseded.uploaded_by_name}`
              : ""}
          </p>
        ) : null}
        {/* O envio só aparece onde a origem declara não ter. Onde ela tem, ou
            vai ter, o botão não existe — não fica desabilitado. */}
        {photo.can_upload ? (
          <label className="text-brand-strong w-fit cursor-pointer text-xs font-bold hover:underline">
            {enviando ? "enviando…" : "enviar foto"}
            <input
              type="file"
              accept="image/jpeg,image/png"
              className="sr-only"
              disabled={enviando}
              onChange={(e) => {
                const arquivo = e.target.files?.[0];
                e.target.value = "";
                if (arquivo) void enviar(arquivo);
              }}
            />
          </label>
        ) : null}
        {erroEnvio ? <p className="text-xs text-red-700">{erroEnvio}</p> : null}
      </div>
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
function legenda(photo: HrPhoto, falhou: boolean): string {
  if (falhou) return "não foi possível carregar a foto";
  if (photo.state === "ausente") return "sem foto no sistema de ponto";
  if (photo.state === "pendente") return "foto ainda não sincronizada";

  const quando =
    photo.origin === "manual" ? photo.uploaded_at : photo.synced_at;
  const fonte =
    photo.origin === "manual"
      ? `enviada${photo.uploaded_by_name ? ` por ${photo.uploaded_by_name}` : ""}`
      : "origem: Secullum";
  return quando
    ? `${fonte} · ${new Date(quando).toLocaleDateString("pt-BR")}`
    : fonte;
}

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/);
  const primeira = partes[0]?.[0] ?? "";
  const ultima =
    partes.length > 1 ? (partes[partes.length - 1]?.[0] ?? "") : "";
  return (primeira + ultima).toUpperCase();
}
