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
  it("renderiza a nav lateral e a visão geral no novo design", async () => {
    renderScreen(<ProjectSettings />, {
      route: "/projects/1/settings",
      path: "/projects/:id/settings/*",
    });

    expect(await screen.findByText("Configurações do Projeto")).toBeInTheDocument();
    // itens da nav lateral (inclui a seção Tabelas, ausente no mockup mas preservada)
    expect(screen.getByRole("link", { name: /Conectores/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Chaves de API/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Tabelas/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Subdomínio/ })).toBeInTheDocument();
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
