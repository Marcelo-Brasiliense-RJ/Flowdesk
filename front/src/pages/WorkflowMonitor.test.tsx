import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

// reactflow é pesado e usa APIs de layout/DOM ausentes no jsdom: stub mínimo.
vi.mock("reactflow", () => ({
  default: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="reactflow">{children}</div>
  ),
  Background: () => null,
  BackgroundVariant: { Dots: "dots" },
  Controls: () => null,
  MarkerType: { ArrowClosed: "arrowclosed" },
  useNodesState: () => [[], vi.fn(), vi.fn()],
  useEdgesState: () => [[], vi.fn(), vi.fn()],
}));

vi.mock("../components/flowNodes", () => ({ nodeTypes: {} }));

vi.mock("../components/ProjectLayout", () => ({
  default: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  useProject: () => ({ id: 1, project: { id: 1, name: "Projeto" } }),
}));

vi.mock("../lib/api", () => ({
  api: { get: vi.fn(() => Promise.resolve([])) },
  getToken: () => "tok",
}));

// WebSocket não existe no jsdom: stub que não faz nada.
class FakeWS {
  onmessage: ((ev: MessageEvent) => void) | null = null;
  close() {}
}
vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);

import WorkflowMonitor from "./WorkflowMonitor";

describe("WorkflowMonitor (Monitor)", () => {
  it("renderiza o chrome do novo design e preserva o canvas", async () => {
    renderScreen(<WorkflowMonitor />, {
      route: "/projects/1/workflow",
      path: "/projects/:id/workflow",
    });

    expect(await screen.findByText("Monitor do Workflow")).toBeInTheDocument();
    // selo introduzido pelo re-skin:
    expect(screen.getByText("tempo real")).toBeInTheDocument();
    expect(screen.getByText("Editar projeto")).toBeInTheDocument();
    // canvas (ReactFlow) preservado:
    expect(screen.getByTestId("reactflow")).toBeInTheDocument();
  });
});
