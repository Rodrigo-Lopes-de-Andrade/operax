import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { JustificationVerdict } from "@/components/ponto/justification-verdict";

const post = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, requestApiAsUser: (...args: unknown[]) => post(...args) };
});

const EVENT = "77777777-7777-4777-8777-777777777771";

function paint() {
  return render(
    <JustificationVerdict
      deviationEventId={EVENT}
      employeeName="Ana Ribeiro"
    />,
  );
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({
    justification_id: "x",
    deviation_event_id: EVENT,
    employee_name: "Ana Ribeiro",
    reference_date: "2026-09-28",
    status: "pending",
  });
});

it("não deixa enviar sem motivo", async () => {
  const user = userEvent.setup();
  paint();

  const send = screen.getByRole("button", { name: "Enviar justificativa" });
  expect(send).toBeDisabled();

  await user.type(screen.getByRole("textbox"), "ok");
  expect(send).toBeDisabled();
  expect(post).not.toHaveBeenCalled();
});

it("não oferece escolha de veredito — quem decide é o RH", () => {
  // Desde a P1.2 o supervisor só explica. Um "Aceitar" aqui seria o contorno
  // que a alçada fecha.
  paint();

  expect(screen.queryByRole("radiogroup")).toBeNull();
  expect(screen.queryByRole("radio")).toBeNull();
  expect(screen.queryByText(/Aceitar|Rejeitar/)).toBeNull();
});

it("manda só o texto, sem status", async () => {
  const user = userEvent.setup();
  paint();

  await user.type(screen.getByRole("textbox"), "  Atendimento externo.  ");
  await user.click(
    screen.getByRole("button", { name: "Enviar justificativa" }),
  );

  expect(post).toHaveBeenCalledWith(`/ocorrencias/${EVENT}/justificativa`, {
    method: "POST",
    body: { text: "Atendimento externo." },
  });
});

it("confirma que foi enviada para aprovação do RH", async () => {
  const user = userEvent.setup();
  paint();

  await user.type(screen.getByRole("textbox"), "Atendimento externo.");
  await user.click(
    screen.getByRole("button", { name: "Enviar justificativa" }),
  );

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Justificativa enviada para aprovação do RH.",
  );
  expect(screen.getByRole("textbox")).toHaveValue("");
});

it("nomeia a pessoa afetada antes do envio", () => {
  // Ação irreversível sobre uma pessoa tem de dizer o nome dela antes, não
  // depois — o drawer pode ter sido aberto de uma lista longa.
  paint();

  expect(screen.getByText(/na ocorrência de Ana Ribeiro/)).toBeInTheDocument();
  expect(screen.getByText(/Não é possível editar depois/)).toBeInTheDocument();
});

it("o erro do backend chega à tela em vez de virar sucesso silencioso", async () => {
  const user = userEvent.setup();
  post.mockRejectedValue(new Error("boom"));
  paint();

  await user.type(screen.getByRole("textbox"), "Atendimento externo.");
  await user.click(
    screen.getByRole("button", { name: "Enviar justificativa" }),
  );

  expect(
    await screen.findByText(/Não foi possível enviar/),
  ).toBeInTheDocument();
  expect(screen.queryByRole("status")).toBeNull();
});
