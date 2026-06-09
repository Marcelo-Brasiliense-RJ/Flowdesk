import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

interface ConfirmOpts {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}
interface PromptOpts {
  title: string;
  label?: string;
  defaultValue?: string;
  placeholder?: string;
  confirmLabel?: string;
}
interface SelectOpts {
  title: string;
  label?: string;
  options: { value: string; label: string }[];
  confirmLabel?: string;
}

type State =
  | { kind: "confirm"; opts: ConfirmOpts; resolve: (v: boolean) => void }
  | { kind: "prompt"; opts: PromptOpts; resolve: (v: string | null) => void }
  | { kind: "select"; opts: SelectOpts; resolve: (v: string | null) => void }
  | null;

interface DialogApi {
  confirm: (opts: ConfirmOpts) => Promise<boolean>;
  prompt: (opts: PromptOpts) => Promise<string | null>;
  selectOption: (opts: SelectOpts) => Promise<string | null>;
}

const Ctx = createContext<DialogApi>(null!);
export const useDialog = () => useContext(Ctx);

export function DialogProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(null);
  const [value, setValue] = useState("");

  const confirm = (opts: ConfirmOpts) =>
    new Promise<boolean>((resolve) => setState({ kind: "confirm", opts, resolve }));
  const prompt = (opts: PromptOpts) =>
    new Promise<string | null>((resolve) => {
      setValue(opts.defaultValue ?? "");
      setState({ kind: "prompt", opts, resolve });
    });
  const selectOption = (opts: SelectOpts) =>
    new Promise<string | null>((resolve) => {
      setValue(opts.options[0]?.value ?? "");
      setState({ kind: "select", opts, resolve });
    });

  function finish(result: boolean | string | null) {
    if (!state) return;
    (state.resolve as (v: any) => void)(result);
    setState(null);
  }
  function cancel() {
    finish(state?.kind === "confirm" ? false : null);
  }
  function accept() {
    if (!state) return;
    if (state.kind === "confirm") finish(true);
    else finish(value);
  }

  useEffect(() => {
    if (!state) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancel();
      if (e.key === "Enter" && state.kind !== "select") accept();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, value]);

  return (
    <Ctx.Provider value={{ confirm, prompt, selectOption }}>
      {children}
      {state && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-brand-900/40 p-4 backdrop-blur-sm"
          onMouseDown={cancel}
        >
          <div
            className="modal-in w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-brand-900">{state.opts.title}</h2>

            {state.kind === "confirm" && state.opts.message && (
              <p className="mt-2 text-sm text-slate-500">{state.opts.message}</p>
            )}

            {state.kind === "prompt" && (
              <div className="mt-4">
                {state.opts.label && (
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    {state.opts.label}
                  </label>
                )}
                <input
                  autoFocus
                  className="input"
                  placeholder={state.opts.placeholder}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
              </div>
            )}

            {state.kind === "select" && (
              <div className="mt-4">
                {state.opts.label && (
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    {state.opts.label}
                  </label>
                )}
                <select
                  autoFocus
                  className="input"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                >
                  {state.opts.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="mt-6 flex justify-end gap-2">
              <button onClick={cancel} className="btn-outline py-1.5 text-sm">
                {state.kind === "confirm" ? state.opts.cancelLabel || "Cancelar" : "Cancelar"}
              </button>
              <button
                onClick={accept}
                className={`py-1.5 text-sm ${
                  state.kind === "confirm" && state.opts.danger
                    ? "btn bg-red-600 text-white hover:bg-red-700"
                    : "btn-primary"
                }`}
              >
                {(state.opts as any).confirmLabel ||
                  (state.kind === "confirm" ? "Confirmar" : "Salvar")}
              </button>
            </div>
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}
