import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

vi.mock("../components/Dialog", () => ({
  useDialog: () => ({ confirm: vi.fn(), prompt: vi.fn(), selectOption: vi.fn() }),
}));
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));
vi.mock("../components/ProjectLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  useProject: () => ({
    id: 1,
    project: {
      id: 1,
      name: "Conciliação de Razão",
      subdomain: "concilia-razao",
      status: "live",
      output_folder_name: "output",
      access_mode: "whitelist",
    },
    setProject: vi.fn(),
  }),
}));
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(() => Promise.resolve([])),
    post: vi.fn(() => Promise.resolve({})),
    patch: vi.fn(() => Promise.resolve({})),
    put: vi.fn(() => Promise.resolve({})),
    del: vi.fn(() => Promise.resolve({})),
  },
}));

import ProjectSettings from "./ProjectSettings";

describe("ProjectSettings (Configurações)", () => {
  it("renderiza as abas e a aba Geral editável no novo design", async () => {
    renderScreen(<ProjectSettings />, {
      route: "/projects/1/settings",
      path: "/projects/:id/settings/*",
    });

    expect(await screen.findByRole("heading", { name: "Geral" })).toBeInTheDocument();
    // aba Geral agora edita Nome e Subdomínio (Subdomínio deixou de ser aba própria)
    expect(screen.getByDisplayValue("Conciliação de Razão")).toBeInTheDocument();
    expect(screen.getByDisplayValue("concilia-razao")).toBeInTheDocument();
    // abas horizontais (Tabelas preservada apesar de ausente no mockup)
    expect(screen.getByRole("link", { name: /Conectores/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Chaves de API/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Tabelas/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Variáveis de Ambiente/ })).toBeInTheDocument();
  });

  it("renderiza a seção Conectores com grid e botão", async () => {
    renderScreen(<ProjectSettings />, {
      route: "/projects/1/settings/connectors",
      path: "/projects/:id/settings/*",
    });
    expect(await screen.findByRole("heading", { name: "Conectores" })).toBeInTheDocument();
    expect(screen.getByText("+ Novo conector")).toBeInTheDocument();
  });
});
