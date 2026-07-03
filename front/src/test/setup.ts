import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom não implementa scrollIntoView (usado por chats que rolam ao fim)
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// limpa o DOM montado entre os testes
afterEach(() => cleanup());
