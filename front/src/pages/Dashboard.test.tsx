import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

vi.mock("../components/TopNav", () => ({ default: () => null }));
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(() =>
      Promise.resolve({
        kpis: {
          projects: 8, live: 5, draft: 3, executions: 120,
          success: 100, error: 15, running: 5, success_rate: 87, avg_seconds: 42,
        },
        timeline: [{ date: "2026-06-26", success: 10, error: 2, total: 12 }],
        by_project: [
          { id: 1, name: "Conciliação de Razão", status: "live", executions: 248, errors: 3, last_run: null },
        ],
        recent_errors: [
          {
            id: "e1", project_id: 1, project_name: "Conciliação de Razão",
            stage_name: "Validar", started_at: "2026-06-26T10:00:00Z", stderr: "boom",
          },
        ],
        recent_executions: [],
      })
    ),
  },
}));

import Dashboard from "./Dashboard";

describe("Dashboard", () => {
  it("renderiza KPIs, gráfico, tabelas e erros no novo design", async () => {
    renderScreen(<Dashboard />, { route: "/dashboard" });

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
    expect(await screen.findByText("87%")).toBeInTheDocument();
    expect(screen.getByText("Execuções (7 dias)")).toBeInTheDocument();
    expect(screen.getByText("Distribuição")).toBeInTheDocument();
    expect(screen.getByText("Saúde por projeto")).toBeInTheDocument();
    // link da tabela semântica preservado
    expect(screen.getByText("Conciliação de Razão")).toBeInTheDocument();
    // erro recente
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
