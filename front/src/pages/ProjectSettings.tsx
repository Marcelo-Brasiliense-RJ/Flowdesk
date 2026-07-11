import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useDialog } from "../components/Dialog";
import type { EnvVar, Project } from "../lib/types";
import ProjectLayout, { useProject } from "../components/ProjectLayout";

const SUB = [
  ["", "Geral", "📋"],
  ["tables", "Tabelas", "🗄️"],
  ["connectors", "Conectores", "🔌"],
  ["keys", "Chaves de API", "🔑"],
  ["env", "Variáveis de Ambiente", "🔒"],
];

export default function ProjectSettings() {
  const { id, project, setProject } = useProject();
  const params = useParams();
  const sub = (params["*"] || "").replace(/^\//, "");

  return (
    <ProjectLayout project={project}>
      <div className="flex h-full flex-col">
        <nav className="glass flex shrink-0 gap-1 border-b border-line px-4">
          {SUB.map(([key, label, icon]) => (
            <Link
              key={key}
              to={`/projects/${id}/settings${key ? "/" + key : ""}`}
              className={`flex items-center gap-2 border-b-2 px-3 py-3 text-sm transition ${
                sub === key
                  ? "border-accentv font-medium text-accentv"
                  : "border-transparent text-ink2 hover:text-accentv"
              }`}
            >
              <span className="text-xs opacity-70">{icon}</span>
              {label}
            </Link>
          ))}
        </nav>
        <div className="flex-1 overflow-auto p-6">
          {sub === "" && project && <Overview project={project} setProject={setProject} />}
          {sub === "tables" && <Tables id={id} />}
          {sub === "connectors" && <Connectors id={id} />}
          {sub === "keys" && <ApiKeys id={id} />}
          {sub === "env" && <EnvVars id={id} />}
        </div>
      </div>
    </ProjectLayout>
  );
}

function Header({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-bold text-ink">{title}</h1>
      {sub && <p className="text-sm text-ink2">{sub}</p>}
    </div>
  );
}

function Overview({ project, setProject }: { project: Project; setProject: (p: Project) => void }) {
  const [name, setName] = useState(project.name);
  const [sub, setSub] = useState(project.subdomain);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const dirty = name !== project.name || sub !== project.subdomain;

  async function save() {
    setSaving(true);
    setErr("");
    try {
      const p = await api.patch<Project>(`/api/projects/${project.id}`, { name, subdomain: sub });
      setProject(p);
      setName(p.name);
      setSub(p.subdomain);
    } catch (e: any) {
      setErr(e?.message || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <Header title="Geral" sub="Informações e endereço público do projeto" />
      <div className="card max-w-lg space-y-4 p-5">
        <div>
          <label className="mb-1 block text-sm font-medium text-ink">Nome</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ink">Subdomínio</label>
          <div className="flex items-center gap-1">
            <span className="rounded-l-lg border border-r-0 border-line bg-surface-2 px-3 py-2 text-sm text-ink3">/app/</span>
            <input
              className="input rounded-l-none font-mono"
              value={sub}
              onChange={(e) => setSub(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
            />
          </div>
          <p className="mt-1 text-xs text-ink3">
            URL: <code>{location.origin}/app/{sub}</code>
          </p>
        </div>
        {err && <div className="text-sm text-err">{err}</div>}
        <div className="flex items-center gap-2 border-t border-line pt-4">
          <button onClick={save} disabled={saving || !dirty} className="btn-primary py-1.5 text-sm disabled:opacity-50">
            {saving ? "Salvando…" : "Salvar alterações"}
          </button>
          <a href={`/app/${project.subdomain}`} target="_blank" rel="noreferrer" className="btn-outline py-1.5 text-sm">
            Abrir aplicação →
          </a>
        </div>
      </div>
      <div className="card mt-4 max-w-lg divide-y divide-[color:var(--border)] p-5 text-sm">
        <Row label="Status" value={project.status} />
        <Row label="Pasta de saída" value={project.output_folder_name} />
        <Row label="Política de acesso" value={project.access_mode} />
      </div>
    </div>
  );
}
function Row({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between py-2">
      <span className="text-ink3">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </div>
  );
}

/* ---------------- Tabelas (banco interno, CRUD visual) ---------------- */
interface DTable { id: number; name: string; columns: { name: string; type: string }[] }
interface DRow { id: number; values: Record<string, any> }

function Tables({ id }: { id: number }) {
  const dlg = useDialog();
  const [tables, setTables] = useState<DTable[]>([]);
  const [sel, setSel] = useState<DTable | null>(null);
  const [rows, setRows] = useState<DRow[]>([]);

  async function loadTables() {
    setTables(await api.get<DTable[]>(`/api/projects/${id}/tables`));
  }
  useEffect(() => {
    loadTables();
  }, [id]);

  async function openTable(t: DTable) {
    setSel(t);
    setRows(await api.get<DRow[]>(`/api/projects/${id}/tables/${t.id}/rows`));
  }
  async function createTable() {
    const name = await dlg.prompt({ title: "Nova tabela", label: "Nome da tabela", placeholder: "Ex: clientes" });
    if (!name?.trim()) return;
    await api.post(`/api/projects/${id}/tables?name=${encodeURIComponent(name.trim())}`);
    loadTables();
  }
  async function delTable(t: DTable) {
    if (!(await dlg.confirm({ title: "Excluir tabela", message: `"${t.name}" e seus dados serão removidos.`, danger: true, confirmLabel: "Excluir" }))) return;
    await api.del(`/api/projects/${id}/tables/${t.id}`);
    if (sel?.id === t.id) setSel(null);
    loadTables();
  }
  async function addColumn() {
    if (!sel) return;
    const name = await dlg.prompt({ title: "Nova coluna", label: "Nome da coluna" });
    if (!name?.trim()) return;
    const type = await dlg.selectOption({
      title: "Tipo da coluna",
      label: name,
      options: [
        { value: "text", label: "Texto" },
        { value: "number", label: "Número" },
        { value: "date", label: "Data" },
      ],
    });
    const columns = [...(sel.columns || []), { name: name.trim(), type: type || "text" }];
    const upd = await api.patch<DTable>(`/api/projects/${id}/tables/${sel.id}`, { columns });
    setSel(upd);
  }
  async function addRow() {
    if (!sel) return;
    const r = await api.post<DRow>(`/api/projects/${id}/tables/${sel.id}/rows`, { values: {} });
    setRows((rs) => [...rs, r]);
  }
  async function saveCell(row: DRow, col: string, value: string) {
    if (!sel) return;
    const values = { ...row.values, [col]: value };
    await api.patch(`/api/projects/${id}/tables/${sel.id}/rows/${row.id}`, { values });
    setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, values } : r)));
  }
  async function delRow(row: DRow) {
    if (!sel) return;
    await api.del(`/api/projects/${id}/tables/${sel.id}/rows/${row.id}`);
    setRows((rs) => rs.filter((r) => r.id !== row.id));
  }

  return (
    <div>
      <Header title="Tabelas" sub="Banco de dados interno do projeto" />
      <div className="flex gap-4">
        {/* tables list */}
        <div className="w-52 shrink-0">
          <button onClick={createTable} className="btn-primary mb-2 w-full py-1.5 text-sm">
            + Nova tabela
          </button>
          <div className="space-y-1">
            {tables.map((t) => (
              <div
                key={t.id}
                className={`group flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                  sel?.id === t.id ? "bg-surface-2 text-brandv" : "text-ink2 hover:bg-surface-2"
                }`}
              >
                <button onClick={() => openTable(t)} className="flex-1 truncate text-left">
                  🗄️ {t.name}
                </button>
                <button onClick={() => delTable(t)} className="hidden text-ink3 hover:text-err group-hover:block">
                  ×
                </button>
              </div>
            ))}
            {tables.length === 0 && <div className="px-3 py-2 text-xs text-ink3">Nenhuma tabela.</div>}
          </div>
        </div>

        {/* table data grid */}
        <div className="min-w-0 flex-1">
          {!sel ? (
            <div className="card flex h-48 items-center justify-center text-sm text-ink3">
              Selecione ou crie uma tabela.
            </div>
          ) : (
            <div className="card overflow-hidden">
              <div className="flex items-center justify-between border-b border-line px-4 py-2">
                <span className="font-semibold text-ink">{sel.name}</span>
                <div className="flex gap-2">
                  <button onClick={addColumn} className="btn-outline py-1 text-xs">+ Coluna</button>
                  <button onClick={addRow} disabled={!sel.columns?.length} className="btn-primary py-1 text-xs disabled:opacity-50">
                    + Linha
                  </button>
                </div>
              </div>
              {!sel.columns?.length ? (
                <div className="p-6 text-center text-sm text-ink3">
                  Adicione colunas para começar.
                </div>
              ) : (
                <div className="overflow-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-surface-2 text-xs uppercase text-ink3">
                      <tr>
                        {sel.columns.map((c) => (
                          <th key={c.name} className="px-3 py-2">
                            {c.name} <span className="text-[9px] text-ink3">{c.type}</span>
                          </th>
                        ))}
                        <th className="w-8" />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.id} className="border-t border-line">
                          {sel.columns.map((c) => (
                            <td key={c.name} className="px-1 py-1">
                              <input
                                className="w-full rounded px-2 py-1 text-sm outline-none focus:bg-surface-2"
                                type={c.type === "number" ? "number" : c.type === "date" ? "date" : "text"}
                                defaultValue={row.values[c.name] ?? ""}
                                onBlur={(e) => saveCell(row, c.name, e.target.value)}
                              />
                            </td>
                          ))}
                          <td className="px-2">
                            <button onClick={() => delRow(row)} className="text-ink3 hover:text-err">×</button>
                          </td>
                        </tr>
                      ))}
                      {rows.length === 0 && (
                        <tr><td colSpan={sel.columns.length + 1} className="px-3 py-4 text-center text-ink3">Sem linhas.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Conectores (funcional) ---------------- */
const CONNECTOR_TYPES = [
  { value: "google_sheets", label: "Google Sheets" },
  { value: "slack", label: "Slack" },
  { value: "http", label: "HTTP / API externa" },
];

function Connectors({ id }: { id: number }) {
  const dlg = useDialog();
  const [items, setItems] = useState<any[]>([]);
  async function load() {
    setItems(await api.get<any[]>(`/api/projects/${id}/connectors`));
  }
  useEffect(() => {
    load();
  }, [id]);

  async function add() {
    const type = await dlg.selectOption({ title: "Novo conector", label: "Tipo", options: CONNECTOR_TYPES });
    if (!type) return;
    const label = CONNECTOR_TYPES.find((t) => t.value === type)?.label || type;
    const name = await dlg.prompt({ title: "Nome do conector", label: "Identificação", defaultValue: label });
    if (!name?.trim()) return;
    const secret = await dlg.prompt({ title: "Configuração", label: "URL / token / chave (opcional)", placeholder: "https://… ou token" });
    await api.post(`/api/projects/${id}/connectors`, { type, name: name.trim(), config: secret ? { secret } : {} });
    load();
  }
  async function del(c: any) {
    if (!(await dlg.confirm({ title: "Remover conector", message: c.name, danger: true, confirmLabel: "Remover" }))) return;
    await api.del(`/api/projects/${id}/connectors/${c.id}`);
    load();
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <Header title="Conectores" sub="Integrações externas do projeto" />
        <button onClick={add} className="btn-primary py-1.5 text-sm">+ Novo conector</button>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {items.map((c) => (
          <div key={c.id} className="card p-4">
            <div className="flex items-start justify-between">
              <div className="font-medium text-ink">{c.name}</div>
              <button onClick={() => del(c)} className="text-ink3 hover:text-err">×</button>
            </div>
            <div className="text-xs text-ink3">{CONNECTOR_TYPES.find((t) => t.value === c.type)?.label || c.type}</div>
            <span className="badge mt-2" data-status={c.connected ? "success" : "inactive"}>
              {c.connected ? "Conectado" : "Não conectado"}
            </span>
          </div>
        ))}
        {items.length === 0 && (
          <div className="col-span-full rounded-xl border border-dashed border-line p-8 text-center text-sm text-ink3">
            Nenhum conector. Adicione Google Sheets, Slack ou uma API externa.
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Chaves de API ---------------- */
function ApiKeys({ id }: { id: number }) {
  const dlg = useDialog();
  const [keys, setKeys] = useState<any[]>([]);
  async function load() {
    setKeys(await api.get<any[]>(`/api/projects/${id}/api-keys`));
  }
  useEffect(() => {
    load();
  }, [id]);
  async function create() {
    const name = await dlg.prompt({ title: "Nova chave de API", label: "Nome da chave" });
    if (!name?.trim()) return;
    await api.post(`/api/projects/${id}/api-keys?name=${encodeURIComponent(name.trim())}`);
    load();
  }
  async function del(k: any) {
    if (!(await dlg.confirm({ title: "Revogar chave", message: k.name, danger: true, confirmLabel: "Revogar" }))) return;
    await api.del(`/api/projects/${id}/api-keys/${k.id}`);
    load();
  }
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <Header title="Chaves de API" sub="Tokens para acesso programático" />
        <button onClick={create} className="btn-primary py-1.5 text-sm">+ Gerar chave</button>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <tbody>
            {keys.map((k) => (
              <tr key={k.id} className="border-t border-line first:border-0">
                <td className="px-4 py-2 font-medium text-ink">🔑 {k.name}</td>
                <td className="px-4 py-2 font-mono text-xs text-ink2">{k.token}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => del(k)} className="text-xs text-err hover:underline">revogar</button>
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td className="px-4 py-6 text-center text-ink3">Nenhuma chave gerada.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------------- Variáveis de Ambiente ---------------- */
function EnvVars({ id }: { id: number }) {
  const [vars, setVars] = useState<EnvVar[]>([]);
  const [reveal, setReveal] = useState<Record<number, boolean>>({});
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  async function load() {
    setVars(await api.get<EnvVar[]>(`/api/projects/${id}/env`));
  }
  useEffect(() => {
    load();
  }, [id]);
  async function save() {
    if (!key) return;
    await api.put(`/api/projects/${id}/env`, { key, value, secret: true });
    setKey("");
    setValue("");
    load();
  }
  return (
    <div>
      <Header title="Variáveis de Ambiente" sub="Injetadas no subprocesso dos scripts. Valores ocultos por padrão." />
      <div className="card overflow-hidden">
        <div className="flex gap-2 border-b border-line p-3">
          <input className="input max-w-[180px] font-mono" placeholder="CHAVE" value={key} onChange={(e) => setKey(e.target.value.toUpperCase())} />
          <input className="input" type="password" autoComplete="off" placeholder="valor (oculto)" value={value} onChange={(e) => setValue(e.target.value)} />
          <button onClick={save} className="btn-primary py-1.5 text-sm">Adicionar</button>
        </div>
        <table className="w-full text-left text-sm">
          <tbody>
            {vars.map((v) => (
              <tr key={v.id} className="border-t border-line">
                <td className="px-4 py-2 font-mono text-brandv">🔒 {v.key}</td>
                <td className="px-4 py-2 font-mono text-ink2">{reveal[v.id] ? v.value : "••••••••"}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => setReveal((r) => ({ ...r, [v.id]: !r[v.id] }))} className="mr-3 text-xs text-brandv hover:underline">
                    {reveal[v.id] ? "ocultar" : "revelar"}
                  </button>
                  <button onClick={() => api.del(`/api/projects/${id}/env/${v.id}`).then(load)} className="text-xs text-err hover:underline">excluir</button>
                </td>
              </tr>
            ))}
            {vars.length === 0 && (
              <tr><td colSpan={3} className="px-4 py-6 text-center text-ink3">Nenhuma variável.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
