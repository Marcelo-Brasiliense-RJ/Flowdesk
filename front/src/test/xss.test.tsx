import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MessageContent, safeUrl } from "../components/SmartChat";

describe("XSS na renderização do chat", () => {
  it("safeUrl bloqueia esquemas perigosos e mantém http/mailto", () => {
    expect(safeUrl("javascript:alert(1)")).toBe("");
    expect(safeUrl("  javascript:alert(1)")).toBe("");
    expect(safeUrl("data:text/html,<script>")).toBe("");
    expect(safeUrl("https://irko.com.br")).toBe("https://irko.com.br");
    expect(safeUrl("mailto:x@irko.com.br")).toBe("mailto:x@irko.com.br");
  });

  it("payload malicioso do assistente é renderizado inerte", () => {
    const payload =
      "<img src=x onerror=alert(1)> <script>alert(1)</script> " +
      "[clique](javascript:alert(1))";
    const { container } = render(<MessageContent text={payload} markdown />);
    // HTML cru não vira elemento (react-markdown escapa por padrão)
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    // nenhum link com href javascript:
    const hrefs = Array.from(container.querySelectorAll("a")).map((a) =>
      a.getAttribute("href") || ""
    );
    expect(hrefs.some((h) => h.toLowerCase().startsWith("javascript:"))).toBe(false);
  });
});
