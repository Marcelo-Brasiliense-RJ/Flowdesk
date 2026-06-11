import { useState } from "react";

/**
 * Tela de revisão humana do OCR (etapa 3 da validação).
 *
 * Aparece quando a saída de uma automação traz o bloco `_ocr_review`. Mostra a
 * confiança, destaca os trechos lidos com baixa confiança e exige uma confirmação
 * humana antes de o resultado ser considerado confiável. É um checkpoint de
 * verificação: a pessoa confere o que o OCR leu antes de usar o resultado.
 */
export interface OcrReviewData {
  text?: string;
  mean_confidence?: number | null;
  needs_review?: boolean;
  low_confidence?: string[];
}

export default function OcrReview({
  review,
  confirmed,
  onConfirm,
  onReprocess,
}: {
  review: OcrReviewData;
  confirmed: boolean;
  onConfirm: () => void;
  /** Quando presente, permite corrigir o texto e reprocessar a automação com ele. */
  onReprocess?: (textoCorrigido: string) => void;
}) {
  const conf = review.mean_confidence;
  const low = review.low_confidence ?? [];
  const needs = !!review.needs_review;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(review.text || "");

  return (
    <div
      className={`rounded-xl border p-4 ${
        needs ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="font-semibold text-brand-900">Revisão do texto reconhecido</div>
        {typeof conf === "number" && (
          <span
            className={`badge ${
              conf >= 0.85 ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
            }`}
          >
            confiança {Math.round(conf * 100)}%
          </span>
        )}
      </div>

      <p className={`mt-1 text-sm ${needs ? "text-amber-700" : "text-slate-500"}`}>
        {needs
          ? "Alguns trechos foram lidos com baixa confiança. Confira os itens destacados antes de confiar no resultado."
          : "Reconhecimento com alta confiança. Confira mesmo assim, se quiser."}
      </p>

      {low.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">
            Trechos a conferir
          </div>
          <ul className="mt-1 space-y-1">
            {low.map((t, i) => (
              <li key={i} className="rounded bg-amber-100 px-2 py-1 text-sm text-amber-900">
                {t}
              </li>
            ))}
          </ul>
        </div>
      )}

      {editing ? (
        <div className="mt-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Corrija o texto abaixo e reprocesse
          </div>
          <textarea
            className="input mt-1 min-h-[180px] font-mono text-xs"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => onReprocess?.(draft)}
              disabled={!draft.trim()}
              className="btn-primary py-1.5 text-sm disabled:opacity-40"
            >
              Reprocessar com o texto corrigido
            </button>
            <button onClick={() => setEditing(false)} className="btn-ghost py-1.5 text-sm">
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-slate-500">Ver todo o texto extraído</summary>
          <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs text-slate-700">
            {review.text || "(vazio)"}
          </pre>
        </details>
      )}

      {!editing && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {needs && !confirmed && (
            <button onClick={onConfirm} className="btn-primary py-1.5 text-sm">
              Confirmei a revisão
            </button>
          )}
          {onReprocess && (
            <button
              onClick={() => {
                setDraft(review.text || "");
                setEditing(true);
              }}
              className="btn-outline py-1.5 text-sm"
            >
              Corrigir texto
            </button>
          )}
          {confirmed && (
            <span className="text-sm font-medium text-emerald-600">Revisão confirmada.</span>
          )}
        </div>
      )}
    </div>
  );
}
