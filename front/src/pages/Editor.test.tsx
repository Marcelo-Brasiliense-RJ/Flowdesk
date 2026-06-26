import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

// Stubs leves para libs que não renderizam em jsdom.
vi.mock("@monaco-editor/react", () => ({
  default: ({ value }: { value?: string }) => (
    <div data-testid="monaco">{value}</div>
  ),
}));

vi.mock("reactflow", () => ({
  default: ({ children }: { children?: any }) => (
    <div data-testid="reactflow">{children}</div>
  ),
  Background: () => null,
  Controls: () => null,
  BackgroundVariant: { Dots: "dots" },
  MarkerType: { ArrowClosed: "arrowclosed" },
  addEdge: (c: any, eds: any[]) => [...eds, c],
  useNodesState: () => [[], vi.fn(), vi.fn()],
  useEdgesState: () => [[], vi.fn(), vi.fn()],
}));

// SmartChat puxa framer-motion/react-markdown; stub simples.
vi.mock("../components/SmartChat", () => ({
  default: () => <div data-testid="smartchat" />,
}));

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) => {
      if (p.endsWith("/files"))
        return Promise.resolve([
          { path: "main.py", content: "print(1)", is_dir: false },
        ]);
      if (p.endsWith("/stages")) return Promise.resolve([]);
      if (p.endsWith("/edges")) return Promise.resolve([]);
      if (p.includes("/executions")) return Promise.resolve({ items: [] });
      // /api/projects/:id
      return Promise.resolve({
        id: 1,
        name: "Conciliação de Razão",
        subdomain: "concilia-razao",
        status: "live",
      });
    }),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  },
}));

import Editor from "./Editor";

describe("Editor (re-skin)", () => {
  it("renderiza o chrome do novo design preservando os painéis", async () => {
    renderScreen(<Editor />, {
      route: "/projects/1/editor",
      path: "/projects/:id/editor",
    });

    // cabeçalho re-skin: nome do projeto + subtítulo do modo avançado
    expect(await screen.findByText("Conciliação de Razão")).toBeInTheDocument();
    expect(screen.getByText(/Modo avançado/)).toBeInTheDocument();
    expect(screen.getByText("Salvar e Publicar")).toBeInTheDocument();

    // painéis preservados: SmartChat, explorer (arquivo), canvas (ReactFlow)
    expect(screen.getByTestId("smartchat")).toBeInTheDocument();
    expect(await screen.findByText("main.py")).toBeInTheDocument();
    expect(screen.getByTestId("reactflow")).toBeInTheDocument();

    // rodapé com abas Execuções / Tarefas
    expect(screen.getByText("Execuções")).toBeInTheDocument();
    expect(screen.getByText("Tarefas")).toBeInTheDocument();
  });
});
