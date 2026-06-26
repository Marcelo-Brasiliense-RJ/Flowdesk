import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// limpa o DOM montado entre os testes
afterEach(() => cleanup());
