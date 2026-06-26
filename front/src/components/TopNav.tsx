import { NavLink } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Logo, ThemeToggle } from "./ui";

const LINKS = [
  ["/chat", "Chat"],
  ["/", "Automações"],
  ["/dashboard", "Dashboard"],
];

export default function TopNav() {
  const { user, logout } = useAuth();
  const canManage = !!(user?.is_admin || user?.is_dev);
  const links = [
    ...LINKS,
    ...(canManage ? [["/manage", "Gerenciar"]] : []),
    ...(user?.is_admin ? [["/admin", "Admin"]] : []),
  ];
  return (
    <header className="glass border-b border-line">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-7 py-3">
        <div className="flex items-center gap-8">
          <NavLink to="/">
            <Logo />
          </NavLink>
          <nav className="flex gap-1 text-sm">
            {links.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 font-medium transition ${
                    isActive ? "text-accent-500" : "text-ink3 hover:text-ink2"
                  }`
                }
                style={({ isActive }) =>
                  isActive
                    ? { background: "var(--accent-soft)", color: "var(--accent)" }
                    : undefined
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <ThemeToggle />
          <span className="text-ink3">{user?.email}</span>
          <button onClick={logout} className="btn-outline py-1.5">
            Sair
          </button>
        </div>
      </div>
    </header>
  );
}
