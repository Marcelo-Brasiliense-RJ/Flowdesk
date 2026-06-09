import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Member, Project, Role } from "../lib/types";
import ProjectLayout, { useProject } from "../components/ProjectLayout";

export default function AccessControl() {
  const { id, project, setProject } = useProject();
  const [tab, setTab] = useState<"users" | "roles">("users");

  return (
    <ProjectLayout project={project}>
      <div className="p-6">
        <h1 className="mb-4 text-xl font-bold text-brand-900">Controle de Acesso</h1>
        <div className="mb-4 flex gap-1 border-b border-slate-200">
          {[
            ["users", "Usuários"],
            ["roles", "Papéis"],
          ].map(([k, l]) => (
            <button
              key={k}
              onClick={() => setTab(k as any)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
                tab === k
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
        {tab === "users" && project && (
          <Users id={id} project={project} setProject={setProject} />
        )}
        {tab === "roles" && <Roles id={id} />}
      </div>
    </ProjectLayout>
  );
}

function Users({
  id,
  project,
  setProject,
}: {
  id: number;
  project: Project;
  setProject: (p: Project) => void;
}) {
  const [members, setMembers] = useState<Member[]>([]);
  const [mode, setMode] = useState(project.access_mode);
  const [domain, setDomain] = useState(project.allowed_domain);
  const [email, setEmail] = useState("");

  async function load() {
    setMembers(await api.get<Member[]>(`/api/projects/${id}/members`));
  }
  useEffect(() => {
    load();
  }, [id]);

  async function savePolicy() {
    const p = await api.put<Project>(`/api/projects/${id}/access-policy`, {
      access_mode: mode,
      allowed_domain: domain,
    });
    setProject(p);
  }

  async function addMember() {
    if (!email) return;
    await api.post(`/api/projects/${id}/members`, { email, roles: ["User"] });
    setEmail("");
    load();
  }

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <h2 className="mb-3 font-semibold text-brand-900">Política global</h2>
        <label className="mb-2 flex items-center gap-2 text-sm">
          <input
            type="radio"
            checked={mode === "whitelist"}
            onChange={() => setMode("whitelist")}
          />
          Permitir apenas usuários listados
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            checked={mode === "domain"}
            onChange={() => setMode("domain")}
          />
          Permitir todos deste domínio:
          <input
            className="input ml-2 max-w-xs"
            placeholder="@empresa.com.br"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            disabled={mode !== "domain"}
          />
        </label>
        <button onClick={savePolicy} className="btn-primary mt-3 py-1.5 text-sm">
          Salvar política
        </button>
      </div>

      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="font-semibold text-brand-900">Usuários</h2>
          <div className="flex gap-2">
            <input
              className="input max-w-xs"
              placeholder="email@irko.com.br"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button onClick={addMember} className="btn-primary py-1.5 text-sm">
              Adicionar usuários
            </button>
          </div>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-4 py-2">E-mail</th>
              <th className="px-4 py-2">Papéis</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} className="border-t border-slate-100">
                <td className="px-4 py-2">{m.email}</td>
                <td className="px-4 py-2">
                  {m.roles.map((r) => (
                    <span key={r} className="badge mr-1 bg-brand-50 text-brand-600">
                      {r}
                    </span>
                  ))}
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() =>
                      api.del(`/api/projects/${id}/members/${m.id}`).then(load)
                    }
                    className="text-slate-400 hover:text-red-600"
                  >
                    ⋮
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Roles({ id }: { id: number }) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  async function load() {
    setRoles(await api.get<Role[]>(`/api/projects/${id}/roles`));
  }
  useEffect(() => {
    load();
  }, [id]);

  async function add() {
    if (!name) return;
    await api.post(`/api/projects/${id}/roles`, { name, description: desc });
    setName("");
    setDesc("");
    load();
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <input
          className="input max-w-[160px]"
          placeholder="Nome do papel"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="input"
          placeholder="Descrição"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
        />
        <button onClick={add} className="btn-primary py-1.5 text-sm">
          Adicionar papéis
        </button>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-400">
          <tr>
            <th className="px-4 py-2">Nome</th>
            <th className="px-4 py-2">Descrição</th>
            <th className="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.id} className="border-t border-slate-100">
              <td className="px-4 py-2 font-medium">{r.name}</td>
              <td className="px-4 py-2 text-slate-500">{r.description}</td>
              <td className="px-4 py-2 text-right">
                <button
                  onClick={() => api.del(`/api/projects/${id}/roles/${r.id}`).then(load)}
                  className="text-slate-400 hover:text-red-600"
                >
                  ⋮
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
