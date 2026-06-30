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
        level: 1, parent: null, temp: "padrão", tools: ["Entrevista"],
        desc: "Conduz a conversa.", where: "chat.py", model: "gpt-4o-mini",
        editable: true, prompt: "Você é o assistente.", prompt_overridden: false,
      },
      {
        id: "construtor", name: "Construtor", role: "Gera código",
        level: 2, parent: "assistente", temp: "0.2", tools: ["create_file"],
        desc: "Gera o script.", where: "chat.py", model: "gpt-4o-mini",
        editable: false, prompt: null, prompt_overridden: false,
      },
    ],
    edges: [{ from: "assistente", to: "construtor" }],
    model: "gpt-4o-mini",
    model_default: "gpt-4o-mini",
    model_catalog: [{ value: "gpt-4o-mini", provider: "OpenAI", note: "Econômico" }],
    ai_enabled: true,
  };
  return { api: { get: vi.fn().mockResolvedValue(DATA), put: vi.fn(), del: vi.fn() } };
});

import Agents from "./Agents";

describe("Agents (Agentes)", () => {
  it("renderiza o organograma com os agentes reais e o painel do Assistente", async () => {
    renderScreen(<Agents />, { route: "/agents", path: "/agents" });

    // título da tela
    expect(await screen.findByRole("heading", { name: "Agentes" })).toBeInTheDocument();
    // nós reais do grafo (assistente aparece no nó e no painel)
    expect(screen.getAllByText("Assistente (Smart Chat)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Construtor").length).toBeGreaterThan(0);
    // painel: system prompt editável do Assistente
    expect(screen.getByText("System prompt")).toBeInTheDocument();
    expect(screen.getByText("Salvar prompt")).toBeInTheDocument();
  });
});
