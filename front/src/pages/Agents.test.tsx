import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, email: "ana@irko.com.br" }, logout: () => {} }),
}));
vi.mock("../components/TopNav", () => ({ default: () => null }));

// dados inline na factory (vi.mock é içado para o topo do arquivo)
vi.mock("../lib/api", () => {
  const DATA = {
    agents: [
      {
        id: "assistente", name: "Assistente (Smart Chat)", role: "Conversa e descoberta",
        level: 1, desc: "Conduz a conversa.", tools: ["Entrevista"], temp: "padrão",
        where: "chat.py", model: "gpt-4o-mini", prompt: "Você é o assistente.",
        x: 380, y: 70, c1: "#155489", c2: "#18b1a8", builtin: true, kind: "assistente", editablePrompt: true,
      },
      {
        id: "construtor", name: "Construtor", role: "Gera código",
        level: 2, desc: "Gera o script.", tools: ["create_file"], temp: "0.2",
        where: "chat.py", model: "gpt-4o-mini", prompt: null,
        x: 110, y: 320, c1: "#0f8f88", c2: "#2dd4c4", builtin: true, kind: "construtor", editablePrompt: false,
      },
    ],
    edges: [{ id: "e0", from: "assistente", to: "construtor" }],
    model: "gpt-4o-mini",
    model_default: "gpt-4o-mini",
    model_catalog: [{ value: "gpt-4o-mini", provider: "OpenAI", note: "Econômico" }],
    ai_enabled: true,
    custom: false,
    applied: { assistant_prompt: true, shared_model: true, orchestration: false },
  };
  return { api: { get: vi.fn().mockResolvedValue(DATA), put: vi.fn(), del: vi.fn() } };
});

import Agents from "./Agents";

describe("Agents (Agentes)", () => {
  it("renderiza o quadro de agentes reais e o painel do Assistente", async () => {
    renderScreen(<Agents />, { route: "/agents", path: "/agents" });

    expect(await screen.findByRole("heading", { name: "Agentes" })).toBeInTheDocument();
    expect(screen.getByText("Quadro de agentes")).toBeInTheDocument();
    // nós reais
    expect(screen.getAllByText("Assistente (Smart Chat)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Construtor").length).toBeGreaterThan(0);
    // painel do Assistente: campo de system prompt
    expect(screen.getByText("System prompt")).toBeInTheDocument();
    // banner de integridade (Fase 1)
    expect(screen.getByText(/Aplicado de verdade no pipeline atual/)).toBeInTheDocument();
  });
});
