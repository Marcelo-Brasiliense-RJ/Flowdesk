import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

// Mocks dos módulos de dados/contexto (hoisted pelo vitest).
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));
vi.mock("../components/TopNav", () => ({ default: () => null }));
vi.mock("../components/Dialog", () => ({
  useDialog: () => ({ confirm: vi.fn(), prompt: vi.fn(), selectOption: vi.fn() }),
}));
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) =>
      Promise.resolve(
        p.includes("/api/projects")
          ? [
              {
                id: 1,
                name: "Conciliação de Razão",
                subdomain: "concilia-razao",
                description: "Concilia débito e crédito.",
                status: "live",
                folder_id: null,
                output_folder_name: "output",
                access_mode: "whitelist",
                allowed_domain: "",
                wizard_state: {},
                wizard_dirty: false,
                created_at: "2026-03-12T10:00:00Z",
                updated_at: "2026-03-20T14:31:00Z",
                owner_name: "Ana Souza",
                execution_count: 248,
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

import Console from "./Console";

describe("Console (Automações)", () => {
  it("renderiza o título e o card no formato do novo design", async () => {
    renderScreen(<Console />, { route: "/console" });

    expect(await screen.findByText("Automações")).toBeInTheDocument();
    expect(await screen.findByText("Conciliação de Razão")).toBeInTheDocument();
    // elementos introduzidos pelo re-skin:
    expect(await screen.findByText("Usar")).toBeInTheDocument();
    expect(screen.getByText(/execuções/)).toBeInTheDocument();
    expect(screen.getByText(/Criado por/)).toBeInTheDocument();
  });
});
