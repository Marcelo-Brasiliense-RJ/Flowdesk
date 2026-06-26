import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

/**
 * Renderiza uma tela dentro de um Router de memória.
 *
 * Os testes devem mockar os módulos de dados antes de importar a tela:
 *   vi.mock("../lib/api", () => ({ api: { get: vi.fn().mockResolvedValue([]) } }));
 *   vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: { is_admin: true } }) }));
 *
 * `route` é a URL inicial e `path` o padrão de rota (use ":id" quando a tela
 * lê useParams, ex: renderScreen(<Editor/>, { route: "/projects/1/editor", path: "/projects/:id/editor" }))
 */
export function renderScreen(
  ui: ReactElement,
  opts: { route?: string; path?: string } = {}
) {
  const { route = "/", path = "*" } = opts;
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path} element={ui} />
      </Routes>
    </MemoryRouter>
  );
}
