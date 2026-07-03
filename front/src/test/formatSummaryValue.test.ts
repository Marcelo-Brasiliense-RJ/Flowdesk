import { describe, it, expect } from "vitest";
import { formatSummaryValue, summaryEntries } from "../pages/publishedSummary";

describe("formatSummaryValue", () => {
  it("formata escalar", () => {
    expect(formatSummaryValue(1700)).toBe("1700");
  });
  it("formata lista de objetos legível", () => {
    const v = [{ produto: "Plano A", valor: 400 }, { produto: "Plano B", valor: 300 }];
    expect(formatSummaryValue(v)).toBe("Plano A: 400; Plano B: 300");
  });
  it("formata objeto chave-valor", () => {
    expect(formatSummaryValue({ a: 1, b: 2 })).toBe("a: 1; b: 2");
  });
});

describe("summaryEntries", () => {
  it("resumo string vira null (exibe como texto, sem iterar caracteres)", () => {
    expect(summaryEntries("42 casados, 3 não casados.")).toBeNull();
  });
  it("resumo objeto vira linhas da tabela", () => {
    expect(summaryEntries({ casados: 42, "não casados": 3 })).toEqual([
      ["casados", 42],
      ["não casados", 3],
    ]);
  });
  it("resumo lista/numero cai em texto", () => {
    expect(summaryEntries([1, 2])).toBeNull();
    expect(summaryEntries(1700)).toBeNull();
  });
});
