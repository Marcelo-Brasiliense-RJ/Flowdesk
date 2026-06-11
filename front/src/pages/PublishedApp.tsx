import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Logo, Spinner } from "../components/ui";
import OcrReview from "../components/OcrReview";

interface Stage {
  id: number;
  type: string;
  name: string;
  config: any;
}

export default function PublishedApp() {
  const { subdomain } = useParams();
  const base = `/api/app/${subdomain}`;
  const [info, setInfo] = useState<any>(null);
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(`app_${subdomain}`)
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [stage, setStage] = useState<Stage | null>(null);
  const [phase, setPhase] = useState<"form" | "processing" | "result" | "done">("form");
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`${base}/info`)
      .then((r) => r.json())
      .then((data) => {
        setInfo(data);
        // modo aberto (sem login): entra direto, sem pedir credenciais
        if (data.open && !token) setToken("open");
      })
      .catch(() => setInfo({ error: true }));
  }, [subdomain]);

  useEffect(() => {
    if (token) loadEntry();
  }, [token]);

  async function loadEntry() {
    const flow = await fetch(`${base}/flow?token=${token}`).then((r) => r.json());
    if (flow.entry_stage_id) loadStage(flow.entry_stage_id);
  }

  async function loadStage(stageId: number) {
    const s = await fetch(`${base}/stages/${stageId}?token=${token}`).then((r) =>
      r.json()
    );
    setStage(s);
    setPhase(s.config?.mode === "result" ? "result" : "form");
  }

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const fd = new FormData();
    fd.append("email", email);
    fd.append("password", password);
    const res = await fetch(`${base}/login`, { method: "POST", body: fd });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      setError(d.detail || "Acesso negado");
      return;
    }
    const data = await res.json();
    localStorage.setItem(`app_${subdomain}`, data.access_token);
    setToken(data.access_token);
  }

  async function submitForm(values: Record<string, string>, files: { field: string; file: File }[]) {
    if (!stage) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("token", token!);
    fd.append("payload", JSON.stringify(values));
    fd.append("file_fields", JSON.stringify(files.map((f) => f.field)));
    files.forEach((f) => fd.append("files", f.file));
    const res = await fetch(`${base}/stages/${stage.id}/submit`, {
      method: "POST",
      body: fd,
    }).then((r) => r.json());
    setBusy(false);

    if (res.status === "processing") {
      setPhase("processing");
      pollExecution(res.execution_id, res.result_stage_id);
    } else if (res.status === "next_form") {
      loadStage(res.next_stage_id);
    } else {
      setPhase("done");
    }
  }

  async function pollExecution(execId: string, resultStageId: number | null) {
    const tick = async () => {
      const ex = await fetch(`${base}/executions/${execId}?token=${token}`).then((r) =>
        r.json()
      );
      if (ex.status === "success") {
        setResult(ex.output);
        if (resultStageId) await loadStage(resultStageId);
        setPhase("result");
      } else if (ex.status === "error") {
        setError(ex.stderr || "Erro no processamento");
        setPhase("form");
      } else {
        setTimeout(tick, 1000);
      }
    };
    tick();
  }

  if (!info)
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-8 w-8 text-brand-600" />
      </div>
    );

  if (info.error)
    return (
      <Shell name="Aplicação">
        <p className="text-center text-slate-500">Aplicação não encontrada.</p>
      </Shell>
    );

  if (!token)
    return (
      <Shell name={info.name}>
        <form onSubmit={login} className="space-y-4">
          <p className="text-center text-sm text-slate-500">
            Acesso restrito {info.access_mode === "domain" && info.allowed_domain
              ? `ao domínio @${info.allowed_domain.replace("@", "")}`
              : "a usuários autorizados"}
            .
          </p>
          <input
            className="input"
            type="email"
            placeholder="seu.email@irko.com.br"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            className="input"
            type="password"
            placeholder="senha"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button className="btn-primary w-full">Entrar</button>
        </form>
      </Shell>
    );

  return (
    <Shell name={info.name}>
      {phase === "form" && stage && (
        <FormRenderer stage={stage} busy={busy} error={error} onSubmit={submitForm} />
      )}
      {phase === "processing" && (
        <div className="flex flex-col items-center gap-3 py-8">
          <Spinner className="h-8 w-8 text-brand-600" />
          <p className="text-sm text-slate-500">Processando sua solicitação...</p>
        </div>
      )}
      {phase === "result" && (
        <ResultRenderer stage={stage} result={result} base={base} token={token} />
      )}
      {phase === "done" && (
        <p className="text-center text-emerald-600">Concluído.</p>
      )}
    </Shell>
  );
}

function Shell({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-lg">
        <div className="mb-4 flex items-center justify-between">
          <Logo />
          <span className="text-sm text-slate-400">aplicação publicada</span>
        </div>
        <div className="card p-8">
          <h1 className="mb-6 text-xl font-bold text-brand-900">{name}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}

function FormRenderer({
  stage,
  busy,
  error,
  onSubmit,
}: {
  stage: Stage;
  busy: boolean;
  error: string;
  onSubmit: (values: Record<string, string>, files: { field: string; file: File }[]) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<{ field: string; file: File }[]>([]);
  const fields = stage.config?.fields || [];

  function setFile(field: string, file: File | undefined) {
    setFiles((fs) => [...fs.filter((f) => f.field !== field), ...(file ? [{ field, file }] : [])]);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(values, files);
      }}
      className="space-y-4"
    >
      {stage.config?.description && (
        <p className="text-sm text-slate-500">{stage.config.description}</p>
      )}
      {fields.map((f: any) => (
        <div key={f.name}>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            {f.label}
          </label>
          {f.type === "file" ? (
            <input
              type="file"
              className="input"
              onChange={(e) => setFile(f.name, e.target.files?.[0])}
              required
            />
          ) : f.type === "select" ? (
            <select
              className="input"
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
            >
              {(f.options || []).map((o: string) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
            />
          )}
        </div>
      ))}
      {error && <div className="text-sm text-red-600">{error}</div>}
      <button className="btn-primary w-full" disabled={busy}>
        {busy ? <Spinner /> : stage.config?.submit_label || "Enviar"}
      </button>
    </form>
  );
}

function ResultRenderer({
  stage,
  result,
  base,
  token,
}: {
  stage: Stage | null;
  result: any;
  base: string;
  token: string | null;
}) {
  const fileKey = stage?.config?.result_file_key || "arquivo_resultado";
  const summaryKey = stage?.config?.summary_key || "resumo";
  const filePath = result?.[fileKey];
  const summary = result?.[summaryKey];
  const review = result?._ocr_review;
  const [dlError, setDlError] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const blockedByReview = !!review?.needs_review && !reviewed;

  async function download() {
    setDlError("");
    try {
      const res = await fetch(
        `${base}/download?path=${encodeURIComponent(filePath)}&token=${token}`
      );
      if (!res.ok) {
        // não salvar o corpo do erro como arquivo: viraria um .xlsx corrompido
        const d = await res.json().catch(() => ({}));
        setDlError(d.detail || "Não foi possível baixar o arquivo. Tente gerar novamente.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filePath.split(/[\\/]/).pop();
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setDlError("Falha de conexão ao baixar o arquivo.");
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-emerald-600">
        {stage?.config?.description || "Processamento concluído."}
      </p>
      {summary && (
        <div className="rounded-lg bg-slate-50 p-4 text-sm">
          <div className="mb-2 font-semibold text-brand-900">Resumo</div>
          <table className="w-full">
            <tbody>
              {Object.entries(summary).map(([k, v]) => (
                <tr key={k} className="border-b border-slate-100 last:border-0">
                  <td className="py-1 text-slate-400">{k}</td>
                  <td className="py-1 text-right font-medium">{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {review && (
        <OcrReview
          review={review}
          confirmed={reviewed}
          onConfirm={() => setReviewed(true)}
        />
      )}
      {filePath && !blockedByReview && (
        <button onClick={download} className="btn-accent w-full">
          Baixar resultado
        </button>
      )}
      {filePath && blockedByReview && (
        <p className="text-center text-xs text-amber-600">
          Confirme a revisão acima para liberar o download.
        </p>
      )}
      {dlError && <div className="text-sm text-red-600">{dlError}</div>}
      {result?.erro && <div className="text-sm text-red-600">{result.erro}</div>}
    </div>
  );
}
