import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));
vi.mock("../components/TopNav", () => ({ default: () => null }));

const dashboard = {
  kpis: {
    projects: 12, live: 8, draft: 4, executions: 340,
    success: 300, error: 20, running: 2, success_rate: 94, avg_seconds: 12,
  },
  timeline: [],
  by_project: [
    { id: 1, name: "Conciliação de Razão", status: "live", executions: 248, errors: 3, last_run: null },
  ],
  recent_errors: [],
  recent_executions: [],
};

const overview = {
  users: { total: 5, active: 4, active_emails: [] },
  chat: {
    messages: 10,
    prompts: 7,
    recent_prompts: [
      { id: 1, project_id: 1, project_name: "Conciliação de Razão", content: "Resuma o razão.", created_at: "2026-06-20T10:00:00Z" },
    ],
  },
  system: { available: false },
  requests: { total: 1000, last_hour: 50, last_minute: 2, by_method: {}, uptime_seconds: 22320 },
  // sem ai_usage: a seção "Uso de IA · Tokens" não deve aparecer
};

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) => {
      if (p.includes("/api/dashboard")) return Promise.resolve(dashboard);
      if (p.includes("/api/admin/overview")) return Promise.resolve(overview);
      if (p.includes("/api/admin/users")) return Promise.resolve([]);
      return Promise.resolve(null);
    }),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  },
}));

import Admin from "./Admin";

describe("Admin (Painel de controle)", () => {
  it("renderiza KPIs, seções e listas no novo design", async () => {
    renderScreen(<Admin />, { route: "/admin", path: "/admin" });

    expect(await screen.findByText("Painel de controle")).toBeInTheDocument();
    expect(await screen.findByText("Consumo de máquina")).toBeInTheDocument();
    expect(await screen.findByText("Usuários e papéis")).toBeInTheDocument();
    expect(await screen.findByText("Aplicações mais usadas")).toBeInTheDocument();
    expect(await screen.findByText("Últimos pedidos ao assistente")).toBeInTheDocument();
    // criação inline de usuário preservada:
    expect(await screen.findByText("+ Novo usuário")).toBeInTheDocument();
  });

  it("omite a seção de IA quando ai_usage não está presente", async () => {
    renderScreen(<Admin />, { route: "/admin", path: "/admin" });

    await screen.findByText("Painel de controle");
    expect(screen.queryByText("Uso de IA · Tokens da API")).not.toBeInTheDocument();
  });
});
