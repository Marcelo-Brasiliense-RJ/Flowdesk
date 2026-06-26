import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

// Mocks dos módulos de dados/contexto (hoisted pelo vitest).
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, is_dev: true, name: "Ana" } }),
}));
vi.mock("../components/TopNav", () => ({ default: () => null }));
vi.mock("../components/Dialog", () => ({
  useDialog: () => ({ confirm: vi.fn(), prompt: vi.fn(), selectOption: vi.fn() }),
}));
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) =>
      Promise.resolve(
        p.includes("/api/manage/apps")
          ? [
              {
                id: 1,
                name: "Conciliação de Razão",
                subdomain: "concilia-razao",
                status: "live",
                folder: "Fiscal",
                created_at: "2026-03-12T10:00:00Z",
                updated_at: "2026-03-20T14:31:00Z",
                last_execution: {
                  status: "success",
                  stage: "script",
                  finished_at: "2026-03-20T14:31:00Z",
                },
                errors: 2,
                executions: 248,
              },
            ]
          : []
      )
    ),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  },
}));

import Manage from "./Manage";

describe("Manage (Gerenciamento)", () => {
  it("renderiza título, indicadores, tabela e ações do novo design", async () => {
    renderScreen(<Manage />, { route: "/manage" });

    // título + subtítulo do re-skin
    expect(await screen.findByText("Gerenciamento de automações")).toBeInTheDocument();
    // linha da aplicação
    expect(await screen.findByText("Conciliação de Razão")).toBeInTheDocument();
    expect(screen.getByText("/app/concilia-razao")).toBeInTheDocument();
    expect(screen.getByText("Fiscal")).toBeInTheDocument();
    // stats (rótulos)
    expect(screen.getByText("Automações")).toBeInTheDocument();
    expect(screen.getByText("Com erros")).toBeInTheDocument();
    // ações preservadas
    expect(screen.getByText("Tirar do ar")).toBeInTheDocument();
    expect(screen.getByText("Logs")).toBeInTheDocument();
    expect(screen.getByText("Workflow")).toBeInTheDocument();
    expect(screen.getByText("Excluir")).toBeInTheDocument();
  });
});
