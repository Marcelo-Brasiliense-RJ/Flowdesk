import { describe, it, expect } from "vitest";
import { matchUploads } from "../pages/Wizard";

describe("matchUploads — auto-anexo do teste", () => {
  it("casa por extensão citada no rótulo do campo", () => {
    const out = matchUploads(
      [{ name: "pdf", label: "Pdf" }, { name: "plano", label: "Plano Path" }],
      [
        { name: "extrato.pdf", path: "uploads/extrato.pdf" },
        { name: "plano_contas.csv", path: "uploads/plano_contas.csv" },
      ]
    );
    expect(out.pdf.path).toBe("uploads/extrato.pdf");
    expect(out.plano.path).toBe("uploads/plano_contas.csv");
  });

  it("sem pista de nome, preenche mesmo assim sem repetir arquivo (mais novo primeiro)", () => {
    const out = matchUploads(
      [{ name: "a", label: "Pdf" }, { name: "b", label: "Plano Path" }],
      [
        { name: "recente.xlsx", path: "uploads/recente.xlsx" },
        { name: "antigo.xlsx", path: "uploads/antigo.xlsx" },
      ]
    );
    expect(out.a.path).toBe("uploads/recente.xlsx");
    expect(out.b.path).toBe("uploads/antigo.xlsx");
    expect(out.a.path).not.toBe(out.b.path);
  });

  it("mais campos que arquivos: preenche o que dá, resto fica de fora", () => {
    const out = matchUploads(
      [{ name: "a", label: "Pdf" }, { name: "b", label: "Plano" }],
      [{ name: "unico.xlsx", path: "uploads/unico.xlsx" }]
    );
    expect(out.a.path).toBe("uploads/unico.xlsx");
    expect(out.b).toBeUndefined();
  });
});
