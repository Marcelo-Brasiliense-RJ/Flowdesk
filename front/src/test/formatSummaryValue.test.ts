import { describe, it, expect } from "vitest";
import { formatSummaryValue } from "../pages/publishedSummary";

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
