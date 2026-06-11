import { NavLink } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Logo } from "./ui";

const LINKS = [
  ["/chat", "Chat"],
  ["/", "Projetos"],
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
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
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
                  `rounded-lg px-3 py-1.5 font-medium ${
                    isActive
                      ? "bg-brand-50 text-brand-700"
                      : "text-slate-500 hover:text-brand-700"
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-500">{user?.email}</span>
          <button onClick={logout} className="btn-outline py-1.5">
            Sair
          </button>
        </div>
      </div>
    </header>
  );
}
