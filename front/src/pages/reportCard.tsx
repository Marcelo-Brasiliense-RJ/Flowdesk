export type ExecutionReport = {
  execution_id: string;
  status: string;
  resumo: string | null;
  output_keys: string[];
  stderr_excerpt: string | null;
  input_files: string[];
};

export function ReportCard({ report }: { report: ExecutionReport }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink3">
        Resultado reportado ({report.status === "error" ? "erro" : "concluído"})
      </div>
      {report.resumo && <div className="text-ink2">{report.resumo}</div>}
      {report.stderr_excerpt && (
        <pre className="mt-1 overflow-auto rounded bg-surface p-2 text-xs text-err">{report.stderr_excerpt}</pre>
      )}
      {report.input_files.length > 0 && (
        <div className="mt-1 text-xs text-ink3">Arquivos: {report.input_files.join(", ")}</div>
      )}
      <div className="mt-1 text-[11px] text-ink3">
        A correção altera o que a automação faz (o script). Problemas de exibição da plataforma não são ajustados aqui.
      </div>
    </div>
  );
}
