import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) => {
      if (p.endsWith("/members"))
        return Promise.resolve([
          { id: 7, email: "joao@irko.com.br", roles: ["Admin", "User"] },
        ]);
      if (/\/api\/projects\/\d+$/.test(p))
        return Promise.resolve({
          id: 1,
          name: "Conciliação",
          status: "live",
          access_mode: "whitelist",
          allowed_domain: "",
        });
      return Promise.resolve([]);
    }),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  },
}));

import AccessControl from "./AccessControl";

describe("AccessControl (Controle de Acesso)", () => {
  it("renderiza política, usuários com badges de papéis e as abas", async () => {
    renderScreen(<AccessControl />, {
      route: "/projects/1/access",
      path: "/projects/:id/access",
    });

    expect(
      await screen.findByRole("heading", { name: "Controle de Acesso" })
    ).toBeInTheDocument();
    expect(screen.getByText("Política global")).toBeInTheDocument();
    expect(screen.getByText("Salvar política")).toBeInTheDocument();
    // aba Papéis preservada e input de email presente
    expect(screen.getByRole("button", { name: "Papéis" })).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("email@irko.com.br")
    ).toBeInTheDocument();
    // usuário e badges de papéis vindos da API
    expect(await screen.findByText("joao@irko.com.br")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
  });
});
