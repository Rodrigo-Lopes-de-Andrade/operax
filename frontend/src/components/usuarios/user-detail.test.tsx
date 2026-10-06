import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UserDetail } from "@/components/usuarios/user-detail";
import { ApiError } from "@/lib/api";
import type { UnitOption } from "@/lib/ponto/queries";
import {
  BY_ROLE_SCOPE_LABEL,
  DEACTIVATE_ERROR_MESSAGE,
  ROLE_ERROR_MESSAGE,
  type RoleDomainMatrix,
  SCOPE_ERROR_MESSAGE,
  type TenantUser,
  type UserRole,
} from "@/lib/usuarios/contract";

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

const ALVO = "a0000000-0000-4000-8000-000000000001";
const ALFA = "c0000000-0000-4000-8000-00000000000a";
const BETA = "c0000000-0000-4000-8000-00000000000b";
const NORTE = "d0000000-0000-4000-8000-000000000001";
const SUL = "d0000000-0000-4000-8000-000000000002";
const LESTE = "d0000000-0000-4000-8000-000000000003";
const INATIVA = "d0000000-0000-4000-8000-0000000000ff";

const UNIDADES: UnitOption[] = [
  {
    unitId: NORTE,
    code: "N01",
    slug: "n01",
    name: "Norte",
    companyId: ALFA,
    companyName: "Alfa Estacionamentos",
    companySlug: "alfa",
  },
  {
    unitId: SUL,
    code: "S01",
    slug: "s01",
    name: "Sul",
    companyId: ALFA,
    companyName: "Alfa Estacionamentos",
    companySlug: "alfa",
  },
  {
    unitId: LESTE,
    code: "L01",
    slug: "l01",
    name: "Leste",
    companyId: BETA,
    companyName: "Beta Garagens",
    companySlug: "beta",
  },
];

/** A matriz da semente (migrations 02 e `dp_banking_account`). */
const MATRIZ: RoleDomainMatrix = {
  roles: [
    {
      role: "owner",
      domains: ["pii", "compensation", "health", "disciplinary", "banking"],
    },
    { role: "executive", domains: ["compensation"] },
    { role: "hr", domains: ["pii", "health", "disciplinary"] },
    {
      role: "personnel",
      domains: ["pii", "compensation", "disciplinary", "banking"],
    },
    { role: "regional_manager", domains: [] },
    { role: "unit_supervisor", domains: [] },
    { role: "operations_manager", domains: [] },
    { role: "accounting", domains: ["compensation", "banking"] },
    { role: "viewer", domains: [] },
  ],
};

/** A mesma matriz com a linha virada no banco: viewer ganha pii, hr perde saúde. */
const MATRIZ_VIRADA: RoleDomainMatrix = {
  roles: MATRIZ.roles.map((entry) =>
    entry.role === "viewer"
      ? { role: "viewer", domains: ["pii"] }
      : entry.role === "hr"
        ? { role: "hr", domains: ["pii", "disciplinary"] }
        : entry,
  ),
};

function membro(overrides: Partial<TenantUser> = {}): TenantUser {
  return {
    user_id: ALVO,
    email: "ana@fastpark.dev",
    name: "Ana Prado",
    role: "viewer",
    active: true,
    deactivated_at: null,
    invitation_accepted: true,
    invited_by: {
      user_id: "a0000000-0000-4000-8000-0000000000ff",
      email: "rh@fastpark.dev",
      name: "Rita RH",
    },
    scope_mode: "by_scope",
    scope: [
      {
        company_id: ALFA,
        company_name: "Alfa Estacionamentos",
        unit_id: NORTE,
        unit_name: "Norte",
      },
    ],
    ...overrides,
  };
}

function abrir({
  user = membro(),
  matrix = MATRIZ as RoleDomainMatrix | null,
  units = UNIDADES as UnitOption[] | null,
  callerIsOwner = true,
} = {}) {
  return render(
    <UserDetail
      user={user}
      matrix={matrix}
      units={units}
      callerIsOwner={callerIsOwner}
    />,
  );
}

function seletorDePapel() {
  return screen.getByRole("combobox", { name: "Papel" });
}

function matriz() {
  return screen.getByRole("region", { name: /^Domínios sensíveis de / });
}

function recusa(detail: string, status = 409) {
  return new ApiError(status, detail);
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("o seletor de papel — só o owner concede", () => {
  it("⛔ para quem não é owner (hr, personnel) o seletor está desabilitado e diz por quê", () => {
    abrir({ callerIsOwner: false });

    expect(seletorDePapel()).toBeDisabled();
    expect(
      screen.getByText(/Só o owner muda o papel de alguém/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salvar papel" })).toBeNull();
  });

  it("para o owner o seletor está habilitado", () => {
    abrir({ callerIsOwner: true });

    expect(seletorDePapel()).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Salvar papel" }),
    ).toBeInTheDocument();
  });

  it("oferece os nove papéis", () => {
    abrir();

    expect(
      within(seletorDePapel())
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual([
      "Owner",
      "Diretoria",
      "RH",
      "Departamento pessoal",
      "Gerente regional",
      "Supervisor de unidade",
      "Gerente de operações",
      "Contabilidade",
      "Consulta",
    ]);
  });

  it("salvar manda só `{role}` e a tela passa a mostrar o que a API devolveu", async () => {
    request.mockResolvedValue(
      membro({ role: "hr", scope_mode: "by_role", scope: [] }),
    );
    const user = userEvent.setup();
    abrir();

    await user.selectOptions(seletorDePapel(), "hr");
    await user.click(screen.getByRole("button", { name: "Salvar papel" }));

    expect(request).toHaveBeenCalledWith(`/usuarios/${ALVO}/papel`, {
      method: "PUT",
      body: { role: "hr" },
    });
    expect(await screen.findByText("Papel salvo: RH.")).toBeInTheDocument();
    // O escopo seguiu a resposta: agora é pelo papel.
    expect(screen.getByText(BY_ROLE_SCOPE_LABEL)).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("o papel igual ao salvo não se salva de novo", () => {
    abrir();

    expect(screen.getByRole("button", { name: "Salvar papel" })).toBeDisabled();
  });

  it("sem a matriz, o owner não concede às cegas", async () => {
    const user = userEvent.setup();
    abrir({ matrix: null });

    await user.selectOptions(seletorDePapel(), "hr");

    expect(screen.getByRole("button", { name: "Salvar papel" })).toBeDisabled();
  });
});

describe("a matriz vem da API, não de constante", () => {
  it("muda com a seleção, antes de salvar", async () => {
    const user = userEvent.setup();
    abrir();

    expect(within(matriz()).getByText("nenhum domínio sensível")).toBeVisible();

    await user.selectOptions(seletorDePapel(), "hr");

    const hr = within(matriz());
    expect(hr.getByText("O que RH enxerga")).toBeInTheDocument();
    expect(hr.getByText("Dados pessoais")).toBeInTheDocument();
    expect(
      hr.getByText(/enxerga CPF, RG, endereço, filiação/),
    ).toBeInTheDocument();
    expect(hr.getByText("Saúde ocupacional")).toBeInTheDocument();
    expect(hr.getByText(/nunca diagnóstico/)).toBeInTheDocument();
    expect(hr.getByText("Disciplinar")).toBeInTheDocument();
    expect(hr.queryByText("Remuneração")).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ viewer: a matriz virada no banco muda a tela (par fixado viewer → hr)", async () => {
    const user = userEvent.setup();
    const { unmount } = abrir({ matrix: MATRIZ });
    expect(within(matriz()).getByText("nenhum domínio sensível")).toBeVisible();
    expect(within(matriz()).queryByText("Dados pessoais")).toBeNull();
    unmount();

    abrir({ matrix: MATRIZ_VIRADA });
    expect(within(matriz()).getByText("Dados pessoais")).toBeVisible();
    expect(within(matriz()).queryByText("nenhum domínio sensível")).toBeNull();

    // hr perdeu saúde no banco, e a tela acompanha.
    await user.selectOptions(seletorDePapel(), "hr");
    expect(within(matriz()).queryByText("Saúde ocupacional")).toBeNull();
    expect(within(matriz()).getByText("Disciplinar")).toBeVisible();
  });

  it("⛔ um papel que a matriz não trouxe NÃO vira 'nenhum domínio sensível'", () => {
    abrir({
      matrix: { roles: MATRIZ.roles.filter((r) => r.role !== "viewer") },
    });

    expect(within(matriz()).queryByText("nenhum domínio sensível")).toBeNull();
    expect(
      within(matriz()).getByText(/A matriz não trouxe este papel/),
    ).toBeInTheDocument();
  });

  it("⛔ a matriz que não respondeu NÃO vira 'nenhum domínio sensível'", () => {
    abrir({ matrix: null });

    expect(within(matriz()).queryByText("nenhum domínio sensível")).toBeNull();
    expect(
      within(matriz()).getByText(/A matriz de domínios não pôde ser lida/),
    ).toBeInTheDocument();
  });

  it.each<UserRole>([
    "regional_manager",
    "unit_supervisor",
    "operations_manager",
    "viewer",
  ])("papel com zero domínio (`%s`) diz 'nenhum domínio sensível'", (role) => {
    abrir({ user: membro({ role }) });

    expect(within(matriz()).getByText("nenhum domínio sensível")).toBeVisible();
    expect(within(matriz()).queryAllByRole("listitem")).toHaveLength(0);
  });

  it("um domínio que nasceu no banco depois da tela ainda aparece", () => {
    abrir({
      matrix: { roles: [{ role: "viewer", domains: ["biometria"] }] },
    });

    expect(
      within(matriz()).getByText('Domínio sensível "biometria"'),
    ).toBeInTheDocument();
  });

  it("para quem não é owner a matriz do papel atual também aparece", () => {
    abrir({ user: membro({ role: "accounting" }), callerIsOwner: false });

    expect(within(matriz()).getByText("Remuneração")).toBeInTheDocument();
    expect(within(matriz()).getByText("Dados bancários")).toBeInTheDocument();
  });
});

describe("⛔ escopo dos quatro papéis de atalho (§3.2)", () => {
  it.each<UserRole>(["owner", "executive", "hr", "personnel"])(
    "`%s` mostra 'todas as unidades (pelo papel)', nunca o conteúdo de scope, e sem editor",
    (role) => {
      abrir({
        user: membro({
          role,
          scope_mode: "by_role",
          // A API manda vazio; cheio aqui prova que a tela não o lê.
          scope: [
            {
              company_id: BETA,
              company_name: "Beta Garagens",
              unit_id: null,
              unit_name: null,
            },
          ],
        }),
      });

      expect(screen.getByText(BY_ROLE_SCOPE_LABEL)).toBeInTheDocument();
      expect(screen.queryByText(/Beta Garagens/)).toBeNull();
      expect(screen.queryByRole("form", { name: "Editar escopo" })).toBeNull();
      expect(
        screen.queryByRole("button", { name: "Salvar escopo" }),
      ).toBeNull();
    },
  );
});

describe("o editor de escopo", () => {
  it("começa no escopo salvo", () => {
    abrir();

    expect(screen.getByLabelText("Norte")).toBeChecked();
    expect(screen.getByLabelText("Sul")).not.toBeChecked();
  });

  it("⛔ não submete vazio", async () => {
    const user = userEvent.setup();
    abrir();

    await user.click(screen.getByLabelText("Norte"));
    await user.click(screen.getByRole("button", { name: "Salvar escopo" }));

    expect(
      await screen.findByText("Escolha pelo menos uma empresa ou unidade."),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("unidade grava a empresa junto; 'todas as unidades' é uma linha por empresa, sem unit_id", async () => {
    request.mockResolvedValue(membro());
    const user = userEvent.setup();
    abrir();

    await user.click(
      screen.getByLabelText("Beta Garagens · todas as unidades"),
    );
    await user.click(screen.getByRole("button", { name: "Salvar escopo" }));

    expect(request).toHaveBeenCalledWith(`/usuarios/${ALVO}/escopo`, {
      method: "PUT",
      body: {
        scope: [{ company_id: ALFA, unit_id: NORTE }, { company_id: BETA }],
      },
    });
    const [, { body }] = request.mock.calls[0] as [
      string,
      { body: { scope: object[] } },
    ];
    expect(body.scope[1]).not.toHaveProperty("unit_id");
    expect(await screen.findByText("Escopo salvo.")).toBeInTheDocument();
  });

  it("depois de salvar, o editor e a mensagem seguem a resposta da API", async () => {
    request.mockResolvedValue(
      membro({
        scope: [
          {
            company_id: BETA,
            company_name: "Beta Garagens",
            unit_id: LESTE,
            unit_name: "Leste",
          },
        ],
      }),
    );
    const user = userEvent.setup();
    abrir();

    await user.click(screen.getByLabelText("Norte"));
    await user.click(screen.getByLabelText("Leste"));
    await user.click(screen.getByRole("button", { name: "Salvar escopo" }));

    expect(await screen.findByText("Escopo salvo.")).toBeInTheDocument();
    expect(screen.getByLabelText("Leste")).toBeChecked();
    expect(screen.getByLabelText("Norte")).not.toBeChecked();
  });

  it("avisa que empresa nova não entra sozinha", () => {
    abrir();

    expect(
      screen.getByText(/Empresa nova não entra sozinha no escopo/),
    ).toBeInTheDocument();
  });

  it("uma linha salva que o seletor não oferece é nomeada antes de sair", () => {
    abrir({
      user: membro({
        scope: [
          {
            company_id: ALFA,
            company_name: "Alfa Estacionamentos",
            unit_id: INATIVA,
            unit_name: "Unidade Fechada",
          },
        ],
      }),
    });

    expect(screen.getByRole("note")).toHaveTextContent(
      "Alfa Estacionamentos · Unidade Fechada",
    );
  });

  it("sem as unidades, o editor não aparece com um seletor vazio", () => {
    abrir({ units: null });

    expect(screen.queryByRole("button", { name: "Salvar escopo" })).toBeNull();
    expect(
      screen.getByText(/As unidades não puderam ser lidas/),
    ).toBeInTheDocument();
    expect(screen.getByText("Alfa Estacionamentos · Norte")).toBeVisible();
  });
});

describe("desativar", () => {
  it("pede confirmação explícita e avisa que é definitivo", async () => {
    const user = userEvent.setup();
    abrir();

    expect(
      screen.getByText(/Desativar é definitivo pela tela/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/reativar é procedimento do operador/),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Desativar usuário" }));
    expect(request).not.toHaveBeenCalled();
    expect(
      screen.getByRole("group", { name: "Confirmar desativação de Ana Prado" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(request).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Desativar usuário" }),
    ).toBeInTheDocument();
  });

  it("confirmar manda `{}` e a tela passa a mostrar o inativo", async () => {
    request.mockResolvedValue(
      membro({ active: false, deactivated_at: "2026-10-05T15:00:00Z" }),
    );
    const user = userEvent.setup();
    abrir();

    await user.click(screen.getByRole("button", { name: "Desativar usuário" }));
    await user.click(
      screen.getByRole("button", { name: "Confirmar desativação" }),
    );

    expect(request).toHaveBeenCalledWith(`/usuarios/${ALVO}/desativar`, {
      method: "POST",
      body: {},
    });
    expect(await screen.findByText(/Inativo desde/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Desativar usuário" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Salvar escopo" })).toBeNull();
    expect(seletorDePapel()).toBeDisabled();
  });
});

describe("reenviar convite", () => {
  it("aparece para quem está ativo e não aceitou", () => {
    abrir({ user: membro({ invitation_accepted: false }) });

    expect(
      screen.getByRole("button", { name: "Reenviar convite" }),
    ).toBeInTheDocument();
  });

  it.each([
    ["convite aceito", membro({ invitation_accepted: true })],
    [
      "inativo",
      membro({
        invitation_accepted: false,
        active: false,
        deactivated_at: "2026-09-30T15:00:00Z",
      }),
    ],
  ])("não aparece para %s", (_caso, user) => {
    abrir({ user });

    expect(
      screen.queryByRole("button", { name: "Reenviar convite" }),
    ).toBeNull();
  });

  it("mostra nome, e-mail, status e quem convidou", () => {
    abrir({ user: membro({ invitation_accepted: false }) });

    expect(
      screen.getByRole("heading", { name: "Ana Prado" }),
    ).toBeInTheDocument();
    expect(screen.getByText("ana@fastpark.dev")).toBeInTheDocument();
    expect(screen.getByText("Convite pendente")).toBeInTheDocument();
    expect(screen.getByText("Rita RH")).toBeInTheDocument();
  });
});

describe("as recusas viram frase pt-BR, nunca o código cru", () => {
  async function trocarPapel(detail: string) {
    request.mockRejectedValue(
      recusa(detail, detail === "not_owner" ? 403 : 409),
    );
    const user = userEvent.setup();
    abrir({
      user: membro({ role: "owner", scope_mode: "by_role", scope: [] }),
    });
    await user.selectOptions(seletorDePapel(), "viewer");
    await user.click(screen.getByRole("button", { name: "Salvar papel" }));
  }

  it.each(["not_owner", "ultimo_owner", "member_not_found"])(
    "papel: `%s`",
    async (detail) => {
      await trocarPapel(detail);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        ROLE_ERROR_MESSAGE[detail],
      );
      expect(screen.getByRole("alert")).not.toHaveTextContent(detail);
    },
  );

  it.each([
    "e_voce_mesmo",
    "owner_so_por_owner",
    "ultimo_owner",
    "not_admin",
    "member_not_found",
  ])("desativar: `%s`", async (detail) => {
    request.mockRejectedValue(recusa(detail));
    const user = userEvent.setup();
    abrir();

    await user.click(screen.getByRole("button", { name: "Desativar usuário" }));
    await user.click(
      screen.getByRole("button", { name: "Confirmar desativação" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      DEACTIVATE_ERROR_MESSAGE[detail],
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(detail);
  });

  it.each([
    "escopo_vazio",
    "escopo_invalido",
    "escopo_sem_empresa",
    "empresa_fora_do_tenant",
    "unidade_fora_da_empresa",
    "not_admin",
  ])("escopo: `%s`", async (detail) => {
    request.mockRejectedValue(recusa(detail, 422));
    const user = userEvent.setup();
    abrir();

    await user.click(screen.getByLabelText("Sul"));
    await user.click(screen.getByRole("button", { name: "Salvar escopo" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      SCOPE_ERROR_MESSAGE[detail],
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(detail);
  });

  it("código desconhecido cai na frase padrão, sem o código", async () => {
    await trocarPapel("codigo_que_ninguem_conhece");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui salvar o papel agora. Tente de novo.",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "codigo_que_ninguem_conhece",
    );
  });

  it("401 diz que a sessão expirou", async () => {
    request.mockRejectedValue(new ApiError(401, null));
    const user = userEvent.setup();
    abrir();

    await user.click(screen.getByRole("button", { name: "Desativar usuário" }));
    await user.click(
      screen.getByRole("button", { name: "Confirmar desativação" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Sua sessão expirou/,
    );
  });
});

describe("⛔ nenhum segredo em tela, log ou storage", () => {
  const VAZAMENTO = {
    password: "SENHA-VAZADA-1",
    token: "TOKEN-VAZADO-2",
    action_link: "https://auth.example/verify?token=LINK-VAZADO-3",
    access_token: "ACCESS-VAZADO-4",
  };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("campos a mais nas respostas não chegam à tela, ao console nem ao storage", async () => {
    const espioes = [
      vi.spyOn(Storage.prototype, "setItem"),
      vi.spyOn(console, "log"),
      vi.spyOn(console, "info"),
      vi.spyOn(console, "warn"),
      vi.spyOn(console, "error"),
      vi.spyOn(console, "debug"),
    ];
    request.mockResolvedValue({
      ...membro({ role: "hr", scope_mode: "by_role", scope: [] }),
      ...VAZAMENTO,
    });
    const user = userEvent.setup();
    const { container } = abrir({
      user: {
        ...membro({ invitation_accepted: false }),
        ...VAZAMENTO,
        invited_by: {
          user_id: "a0000000-0000-4000-8000-0000000000ff",
          email: "rh@fastpark.dev",
          name: "Rita RH",
          ...VAZAMENTO,
        },
      } as TenantUser,
      matrix: { ...MATRIZ, ...VAZAMENTO } as RoleDomainMatrix,
    });

    await user.selectOptions(seletorDePapel(), "hr");
    await user.click(screen.getByRole("button", { name: "Salvar papel" }));
    await screen.findByText("Papel salvo: RH.");

    for (const sentinela of Object.values(VAZAMENTO)) {
      expect(container.innerHTML).not.toContain(sentinela);
    }
    for (const espiao of espioes) {
      expect(espiao).not.toHaveBeenCalled();
    }
    expect(container.querySelector('input[type="password"]')).toBeNull();
  });

  it.each([
    "src/components/usuarios/user-detail.tsx",
    "src/components/usuarios/scope-picker.tsx",
    "src/app/dashboard/usuarios/[userId]/page.tsx",
  ])("`%s` não usa storage nem console", (file) => {
    const source = readFileSync(file, "utf8");

    expect(source).not.toMatch(/localStorage|sessionStorage|console\./);
  });
});
