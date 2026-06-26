import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

// Mocks dos módulos de dados/contexto (hoisted pelo vitest).
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));
vi.mock("../components/ProjectLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  useProject: () => ({ id: "1", project: { id: 1, name: "Proj" } }),
}));
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(() =>
      Promise.resolve([
        {
          id: 1,
          hash: "a1b2c3d",
          framework_version: "n8n 1.42.0",
          status: "live",
          created_at: "2026-03-12T10:00:00Z",
        },
      ])
    ),
    post: vi.fn(),
  },
}));

import Builds from "./Builds";

describe("Builds (Versões)", () => {
  it("renderiza o título e a linha da versão no novo design", async () => {
    renderScreen(<Builds />, {
      route: "/projects/1/builds",
      path: "/projects/:id/builds",
    });

    expect(await screen.findByText("Histórico de versões")).toBeInTheDocument();
    // dados existentes da versão:
    expect(await screen.findByText("a1b2c3d")).toBeInTheDocument();
    expect(screen.getByText("n8n 1.42.0")).toBeInTheDocument();
    // colunas do design:
    expect(screen.getByText("Framework")).toBeInTheDocument();
    expect(screen.getByText("Data/Hora")).toBeInTheDocument();
  });
});
