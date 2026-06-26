import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Logo, Spinner } from "../components/ui";

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // já autenticado: não mostra o formulário de novo
  useEffect(() => {
    if (user) nav("/", { replace: true });
  }, [user, nav]);

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
    <div
      className="relative flex min-h-full items-center justify-center overflow-hidden p-6"
      style={{ background: "linear-gradient(135deg, #0a1f33, #14406b 55%, #155489)" }}
    >
      <div
        className="pointer-events-none absolute"
        style={{
          top: -160,
          left: "50%",
          width: 620,
          height: 620,
          transform: "translateX(-50%)",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(45,212,196,.22), transparent 70%)",
          filter: "blur(40px)",
        }}
      />
      <div className="relative w-full" style={{ maxWidth: 404 }}>
        <div className="mb-6 flex justify-center">
          <Logo light />
        </div>
        <div
          className="p-8"
          style={{
            borderRadius: 20,
            border: "1px solid rgba(255,255,255,.12)",
            background: "rgba(255,255,255,.06)",
            backdropFilter: "blur(18px)",
            WebkitBackdropFilter: "blur(18px)",
            boxShadow: "0 40px 80px -30px rgba(0,0,0,.6)",
          }}
        >
          <h1 className="text-xl font-bold text-white">Entrar</h1>
          <p className="mt-1.5 text-sm" style={{ color: "rgba(234,241,248,.7)" }}>
            Plataforma de automação com IA da IRKO
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label
                className="mb-1.5 block text-sm font-medium"
                style={{ color: "rgba(234,241,248,.85)" }}
              >
                E-mail
              </label>
              <input
                className="login-input"
                type="email"
                autoComplete="username"
                placeholder="seu.email@irko.com.br"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label
                className="mb-1.5 block text-sm font-medium"
                style={{ color: "rgba(234,241,248,.85)" }}
              >
                Senha
              </label>
              <div className="relative">
                <input
                  className="login-input pr-16"
                  type={showPwd ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPwd((v) => !v)}
                  className="absolute inset-y-0 right-2 my-auto h-7 rounded px-2 text-xs font-medium"
                  style={{ color: "rgba(234,241,248,.6)" }}
                  tabIndex={-1}
                >
                  {showPwd ? "ocultar" : "mostrar"}
                </button>
              </div>
            </div>
            {error && (
              <div
                className="rounded-lg px-3 py-2 text-sm"
                style={{ background: "rgba(255,122,122,.15)", color: "#ffb4b4" }}
              >
                {error}
              </div>
            )}
            <button
              className="mt-1 flex w-full items-center justify-center rounded-xl py-3 text-sm font-semibold text-white"
              style={{
                background: "linear-gradient(135deg, #18b1a8, #2dd4c4)",
                boxShadow: "0 14px 30px -12px rgba(45,212,196,.6)",
              }}
              disabled={loading}
            >
              {loading ? <Spinner /> : "Entrar"}
            </button>
          </form>
        </div>
        <p
          className="mt-4 text-center text-xs"
          style={{ color: "rgba(234,241,248,.5)" }}
        >
          © IRKO · FlowDesk
        </p>
      </div>
    </div>
  );
}
