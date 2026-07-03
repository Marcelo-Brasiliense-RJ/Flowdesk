import type { ProgressEvent } from "../lib/types";
import { Spinner } from "./ui";

/** Linha do tempo "o que a automação está fazendo", em linguagem simples. */
export default function ProgressTimeline({
  events,
  running,
}: {
  events: ProgressEvent[];
  running: boolean;
}) {
  // sem eventos ainda: o botão de teste / o "Processando..." do app já indicam o
  // início; um "Iniciando…" aqui seria um segundo spinner para o mesmo estado.
  if (!events.length) return null;
  return (
    <ol className="mt-3 space-y-1.5" aria-label="Etapas da execução">
      {events.map((e, i) => {
        const isLast = i === events.length - 1;
        return (
          <li key={i} className="flex items-start gap-2 text-sm">
            {isLast && running ? (
              <Spinner className="mt-0.5 h-3.5 w-3.5 text-accentv" />
            ) : (
              <svg
                viewBox="0 0 24 24"
                className="mt-0.5 h-3.5 w-3.5 text-ok"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
            <span className="text-ink">{e.etapa}</span>
            {e.detalhe && <span className="text-ink3">{e.detalhe}</span>}
            <span className="ml-auto text-[10px] text-ink3">{e.ts}</span>
          </li>
        );
      })}
    </ol>
  );
}
