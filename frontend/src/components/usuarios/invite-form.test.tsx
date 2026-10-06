import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InviteForm } from "@/components/usuarios/invite-form";
import { ApiError } from "@/lib/api";
import type { UnitOption } from "@/lib/ponto/queries";
import { INVITE_ERROR_MESSAGE } from "@/lib/usuarios/contract";

const request = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

const ALFA = "c0000000-0000-4000-8000-00000000000a";
const BETA = "c0000000-0000-4000-8000-00000000000b";
const NORTE = "d0000000-0000-4000-8000-000000000001";
const SUL = "d0000000-0000-4000-8000-000000000002";
const CENTRO = "d0000000-0000-4000-8000-000000000003";

function unidade(
  unitId: string,
  name: string,
  companyId: string,
  companyName: string,
): UnitOption {
  return {
    unitId,
    code: name.toUpperCase(),
    slug: name.toLowerCase(),
    name,
    companyId,
    companyName,
    companySlug: companyName.toLowerCase(),
  };
}

// A ordem é a de `vw_unit` (por nome), não por empresa: o agrupamento é da tela.
const UNIDADES: UnitOption[] = [
  unidade(CENTRO, "Centro", BETA, "Beta Garagens"),
  unidade(NORTE, "Norte", ALFA, "Alfa Estacionamentos"),
  unidade(SUL, "Sul", ALFA, "Alfa Estacionamentos"),
];

async function preencher(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Nome"), "Nina Nova");
  await user.type(screen.getByLabelText("E-mail"), "nina@fastpark.dev");
}

function enviar() {
  return screen.getByRole("button", { name: "Enviar convite" });
}

function corpo() {
  return (request.mock.calls[0][1] as { body: unknown }).body;
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("o formulário de convite", () => {
  it("não tem campo de papel nem de senha, e diz que a pessoa nasce viewer", () => {
    render(<InviteForm units={UNIDADES} />);

    expect(screen.queryByLabelText(/papel/i)).toBeNull();
    expect(screen.queryByLabelText(/senha/i)).toBeNull();
    expect(screen.getByText(/Papel só o owner concede/)).toBeInTheDocument();
    expect(screen.getByText(/\(viewer\)/)).toBeInTheDocument();
  });

  it("avisa que empresa nova não entra sozinha no escopo", () => {
    render(<InviteForm units={UNIDADES} />);

    expect(
      screen.getByText(/Empresa nova não entra sozinha no escopo/),
    ).toBeInTheDocument();
  });

  it("⛔ não submete sem escopo", async () => {
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(enviar());

    expect(
      await screen.findByText("Escolha pelo menos uma empresa ou unidade."),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ não submete sem nome", async () => {
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await user.type(screen.getByLabelText("E-mail"), "nina@fastpark.dev");
    await user.click(screen.getByLabelText("Norte"));
    await user.click(enviar());

    expect(await screen.findByText("Informe o nome.")).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ desmarcar a última escolha volta ao estado que não submete", async () => {
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Norte"));
    await user.click(screen.getByLabelText("Norte"));
    await user.click(enviar());

    expect(
      await screen.findByText("Escolha pelo menos uma empresa ou unidade."),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ a unidade carrega a empresa DELA", async () => {
    request.mockResolvedValue({
      user_id: "x",
      email: "nina@fastpark.dev",
      role: "viewer",
      invitation_sent: true,
    });
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Centro"));
    await user.click(screen.getByLabelText("Sul"));
    await user.click(enviar());

    expect(request).toHaveBeenCalledWith("/usuarios/convites", {
      method: "POST",
      body: {
        name: "Nina Nova",
        email: "nina@fastpark.dev",
        scope: [
          { company_id: BETA, unit_id: CENTRO },
          { company_id: ALFA, unit_id: SUL },
        ],
      },
    });
  });

  it("⛔ empresa inteira vai SEM a chave `unit_id` — e absorve as unidades dela", async () => {
    request.mockResolvedValue({
      user_id: "x",
      email: "nina@fastpark.dev",
      role: "viewer",
      invitation_sent: true,
    });
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Norte"));
    await user.click(
      screen.getByLabelText("Alfa Estacionamentos · todas as unidades"),
    );
    await user.click(enviar());

    const { scope } = corpo() as { scope: Record<string, unknown>[] };
    expect(scope).toEqual([{ company_id: ALFA }]);
    expect(Object.hasOwn(scope[0], "unit_id")).toBe(false);
  });

  it("201 com `invitation_sent: true` diz para quem foi o convite", async () => {
    request.mockResolvedValue({
      user_id: "x",
      email: "nina@fastpark.dev",
      role: "viewer",
      invitation_sent: true,
    });
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Norte"));
    await user.click(enviar());

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Convite enviado para nina@fastpark.dev.",
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("201 com `invitation_sent: false` diz que o acesso foi liberado sem e-mail", async () => {
    request.mockResolvedValue({
      user_id: "x",
      email: "nina@fastpark.dev",
      role: "viewer",
      invitation_sent: false,
    });
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Norte"));
    await user.click(enviar());

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Essa pessoa já tem conta; o acesso foi liberado sem novo e-mail.",
    );
  });

  it.each(Object.entries(INVITE_ERROR_MESSAGE))(
    "a recusa `%s` vira a frase dela",
    async (code, message) => {
      request.mockRejectedValue(new ApiError(422, code));
      const user = userEvent.setup();
      render(<InviteForm units={UNIDADES} />);

      await preencher(user);
      await user.click(screen.getByLabelText("Norte"));
      await user.click(enviar());

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
    },
  );

  it("409 `conta_em_outro_cliente` diz para usar outro e-mail, e não oferece reenvio", async () => {
    request.mockRejectedValue(new ApiError(409, "conta_em_outro_cliente"));
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Norte"));
    await user.click(enviar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Esse e-mail já é usado em outro cliente do painel. Use outro e-mail para esta pessoa.",
    );
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("button", { name: /Reenviar/ })).toBeNull();
  });

  it("o 422 de validação (detail em lista) cai na frase padrão", async () => {
    request.mockRejectedValue(new ApiError(422, null));
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Norte"));
    await user.click(enviar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui enviar o convite agora",
    );
  });

  it("sessão expirada (401) diz para entrar de novo", async () => {
    request.mockRejectedValue(new ApiError(401, null));
    const user = userEvent.setup();
    render(<InviteForm units={UNIDADES} />);

    await preencher(user);
    await user.click(screen.getByLabelText("Norte"));
    await user.click(enviar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sua sessão expirou",
    );
  });

  it("sem unidade nenhuma, não há como enviar", () => {
    render(<InviteForm units={[]} />);

    expect(enviar()).toBeDisabled();
  });
});
