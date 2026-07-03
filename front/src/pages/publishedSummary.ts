/**
 * Linhas da tabela de Resumo, ou null quando o resumo e texto simples (string/numero)
 * e deve ser exibido direto. Sem isto, um resumo string cairia em Object.entries("...")
 * e renderizaria um caractere por linha (index: char).
 */
export function summaryEntries(summary: unknown): [string, unknown][] | null {
  if (summary && typeof summary === "object" && !Array.isArray(summary)) {
    return Object.entries(summary as Record<string, unknown>);
  }
  return null;
}

export function formatSummaryValue(v: unknown): string {
  if (Array.isArray(v)) {
    return v
      .map((item) =>
        item && typeof item === "object"
          ? Object.values(item as Record<string, unknown>).join(": ")
          : String(item)
      )
      .join("; ");
  }
  if (v && typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k}: ${String(val)}`)
      .join("; ");
  }
  return String(v);
}
