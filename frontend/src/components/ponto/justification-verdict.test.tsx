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
  post.mockResolvedValue({ justification_id: "x" });
});

it("não deixa registrar sem motivo, nem para aceitar nem para rejeitar", async () => {
  // Uma rejeição vazia é a decisão sem a parte que a pessoa afetada precisa ler.
  const user = userEvent.setup();
  paint();

  expect(screen.getByRole("button", { name: /Registrar/ })).toBeDisabled();

  await user.click(screen.getByRole("radio", { name: "Rejeitar" }));

  expect(screen.getByRole("button", { name: /Registrar/ })).toBeDisabled();
  expect(post).not.toHaveBeenCalled();
});

it("o botão diz qual dos dois vereditos vai acontecer", async () => {
  // A gravação não volta atrás: o rótulo é a última chance de ler o que se
  // está prestes a fazer, e por isso ele não pode ser genérico.
  const user = userEvent.setup();
  paint();

  await user.type(screen.getByRole("textbox"), "Atendimento externo.");
  expect(
    screen.getByRole("button", { name: "Registrar aceite" }),
  ).toBeEnabled();

  await user.click(screen.getByRole("radio", { name: "Rejeitar" }));
  expect(
    screen.getByRole("button", { name: "Registrar rejeição" }),
  ).toBeEnabled();
});

it("manda o veredito escolhido, não o default", async () => {
  const user = userEvent.setup();
  paint();

  await user.click(screen.getByRole("radio", { name: "Rejeitar" }));
  await user.type(screen.getByRole("textbox"), "Sem autorização registrada.");
  await user.click(screen.getByRole("button", { name: "Registrar rejeição" }));

  expect(post).toHaveBeenCalledWith(`/ocorrencias/${EVENT}/justificativa`, {
    method: "POST",
    body: { text: "Sem autorização registrada.", status: "rejected" },
  });
});

it("nomeia quem recebe o veredito antes de ele ser dado", () => {
  // Ação irreversível sobre uma pessoa tem de dizer o nome dela antes, não
  // depois — o drawer pode ter sido aberto de uma lista longa.
  paint();

  expect(screen.getByText(/na ocorrência de Ana Ribeiro/)).toBeInTheDocument();
});

it("o erro do backend chega à tela em vez de virar sucesso silencioso", async () => {
  const user = userEvent.setup();
  post.mockRejectedValue(new Error("boom"));
  paint();

  await user.type(screen.getByRole("textbox"), "Atendimento externo.");
  await user.click(screen.getByRole("button", { name: "Registrar aceite" }));

  expect(
    await screen.findByText(/Não foi possível registrar/),
  ).toBeInTheDocument();
});
