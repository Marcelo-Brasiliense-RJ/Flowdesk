import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderScreen } from "../test/utils";

// framer-motion é pesado e anima fora do jsdom: substitui motion.* por tags simples
// e neutraliza AnimatePresence/hooks. Preserva a árvore renderizada.
vi.mock("framer-motion", () => {
  const passthrough = (tag: string) => (props: any) => {
    const { children, ...rest } = props;
    // remove props de animação que não são atributos DOM válidos
    [
      "initial", "animate", "exit", "transition", "variants", "whileHover",
      "whileTap", "layoutId", "layout",
    ].forEach((k) => delete rest[k]);
    const E: any = tag;
    return <E {...rest}>{children}</E>;
  };
  return {
    motion: new Proxy({}, { get: (_t, tag: string) => passthrough(tag) }),
    AnimatePresence: ({ children }: any) => <>{children}</>,
    useReducedMotion: () => true,
  };
});

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: { is_admin: true, name: "Ana" } }),
}));
vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn((p: string) => {
      if (p.endsWith("/stages")) return Promise.resolve([]);
      if (/\/api\/projects\/\d+$/.test(p))
        return Promise.resolve({
          id: 1,
          name: "Conciliação de Razão",
          description: "Concilia débito e crédito.",
          wizard_state: {},
          wizard_dirty: false,
        });
      return Promise.resolve([]);
    }),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    postForm: vi.fn().mockResolvedValue({ name: "x" }),
  },
  getToken: () => "t",
}));
// componentes filhos pesados: não precisam renderizar no smoke
vi.mock("../components/OcrReview", () => ({ default: () => null }));
vi.mock("../components/ProgressTimeline", () => ({ default: () => null }));
vi.mock("../components/ClassificacaoReview", () => ({ default: () => null }));

import Wizard from "./Wizard";

describe("Wizard (Assistente)", () => {
  it("renderiza a tela 'Descreva' com o visual do novo design", async () => {
    renderScreen(<Wizard />, {
      route: "/projects/1/assistente",
      path: "/projects/:id/assistente",
    });

    // cabeçalho: nome do projeto + badge Assistente
    expect(await screen.findByText("Conciliação de Razão")).toBeInTheDocument();
    expect(screen.getByText("Assistente")).toBeInTheDocument();
    // hero da tela inicial (passo -1) preservada
    expect(screen.getByText("O que você quer automatizar?")).toBeInTheDocument();
    expect(screen.getByText("Analisar pedido →")).toBeInTheDocument();
  });
});
