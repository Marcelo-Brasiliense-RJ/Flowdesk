import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Logo, Spinner } from "../components/ui";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@irko.com.br");
  const [password, setPassword] = useState("REMOVED-SEED-PASSWORD");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      nav("/");
    } catch (err: any) {
      setError(err.message || "Falha no login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-brand-900 via-brand-800 to-brand-700 p-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex justify-center">
          <Logo light />
        </div>
        <div className="card p-8">
          <h1 className="text-xl font-semibold text-brand-900">Entrar</h1>
          <p className="mt-1 text-sm text-slate-500">
            Plataforma de automação com IA da IRKO
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                E-mail
              </label>
              <input
                className="input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Senha
              </label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && (
              <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}
            <button className="btn-primary w-full" disabled={loading}>
              {loading ? <Spinner /> : "Entrar"}
            </button>
          </form>
          <p className="mt-4 text-center text-xs text-slate-400">
            Seed: admin@irko.com.br · REMOVED-SEED-PASSWORD
          </p>
        </div>
      </div>
    </div>
  );
}
