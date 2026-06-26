import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) =>
      Promise.resolve(
        p.includes("/fs")
          ? {
              entries: [
                {
                  name: "uploads",
                  is_dir: true,
                  size: 0,
                  modified_at: "2026-03-20T14:31:00Z",
                  path: "uploads",
                },
                {
                  name: "relatorio.pdf",
                  is_dir: false,
                  size: 2048,
                  modified_at: "2026-03-21T09:00:00Z",
                  path: "relatorio.pdf",
                },
              ],
            }
          : { id: 1, name: "Projeto X", status: "draft" }
      )
    ),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
    postForm: vi.fn(),
  },
  getToken: () => "tok",
}));

vi.mock("../components/ui", () => ({
  Logo: () => null,
  StatusBadge: () => null,
}));

import Files from "./Files";

describe("Files (Arquivos)", () => {
  it("renderiza o cabeçalho, breadcrumb e linhas no novo design", async () => {
    renderScreen(<Files />, {
      route: "/projects/1/files",
      path: "/projects/:id/files",
    });

    expect(
      await screen.findByRole("heading", { name: "Arquivos" })
    ).toBeInTheDocument();
    expect(await screen.findByText(/relatorio\.pdf/)).toBeInTheDocument();
    // elementos do re-skin:
    expect(screen.getByText("+ Nova pasta")).toBeInTheDocument();
    expect(screen.getByText("Enviar")).toBeInTheDocument();
    expect(screen.getByText("raiz")).toBeInTheDocument();
    expect(screen.getByText("Ações")).toBeInTheDocument();
  });
});
