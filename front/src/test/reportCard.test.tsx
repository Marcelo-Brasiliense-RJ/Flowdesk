import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportCard } from "../pages/reportCard";

describe("ReportCard", () => {
  it("mostra status e arquivos em sucesso", () => {
    render(<ReportCard report={{ execution_id: "x", status: "success", resumo: "10 casados",
      output_keys: ["resumo"], stderr_excerpt: null, input_files: ["extrato.xlsx", "razao.xlsx"] }} />);
    expect(screen.getByText(/10 casados/)).toBeInTheDocument();
    expect(screen.getByText(/extrato\.xlsx/)).toBeInTheDocument();
  });
  it("mostra trecho do erro quando ha stderr", () => {
    render(<ReportCard report={{ execution_id: "x", status: "error", resumo: null,
      output_keys: [], stderr_excerpt: "KeyError 'Valor'", input_files: [] }} />);
    expect(screen.getByText(/KeyError 'Valor'/)).toBeInTheDocument();
  });
});
