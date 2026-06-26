import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) => {
      if (p.includes("/executions")) {
        return Promise.resolve({
          total: 1,
          items: [
            {
              id: "abcdef1234567890",
              stage_name: "Conciliação",
              stage_type: "python",
              status: "success",
              started_at: "2026-03-20T14:31:00Z",
              stdout: "tudo certo",
              stderr: "",
              output_data: { ok: true },
            },
          ],
        });
      }
      if (p.includes("/stages")) {
        return Promise.resolve([{ id: 1, name: "Conciliação" }]);
      }
      // /api/projects/:id (ProjectLayout)
      return Promise.resolve({ id: 1, name: "Projeto", status: "live" });
    }),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  },
}));

import Logs from "./Logs";

describe("Logs (re-skin)", () => {
  it("renderiza título, contagem, filtros e a execução", async () => {
    renderScreen(<Logs />, { route: "/projects/1/logs", path: "/projects/:id/logs" });

    expect(await screen.findByText("Logs de execução")).toBeInTheDocument();
    expect(await screen.findByText("1 execuções")).toBeInTheDocument();
    // filtros
    expect(screen.getByText("Etapa")).toBeInTheDocument();
    expect(screen.getByText("ID de Execução")).toBeInTheDocument();
    // linha da execução (id curto + nome da etapa)
    expect(await screen.findByText("abcdef12")).toBeInTheDocument();
    expect(screen.getByText("python")).toBeInTheDocument();
  });
});
