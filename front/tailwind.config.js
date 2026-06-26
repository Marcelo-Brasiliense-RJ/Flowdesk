/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // IRKO corporate theme: deep navy + teal accent
        brand: {
          50: "#eef4fb",
          100: "#d6e4f4",
          200: "#aecae9",
          300: "#7ba7d8",
          400: "#4a80c2",
          500: "#1f6fb2",
          600: "#155489",
          700: "#14406b",
          800: "#0f2f4f",
          900: "#0a1f33",
        },
        accent: {
          400: "#2dd4c4",
          500: "#18b1a8",
          600: "#0f8f88",
        },
        // Cores semânticas dirigidas por tokens (dark-aware).
        brandv: "var(--brand)",
        accentv: "var(--accent)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        ink: "var(--text)",
        ink2: "var(--text-2)",
        ink3: "var(--text-3)",
        line: "var(--border)",
        "line-strong": "var(--border-strong)",
        ok: "var(--ok)",
        err: "var(--err)",
        warn2: "var(--warn2)",
        neutral2: "var(--neutral)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      boxShadow: {
        token: "var(--shadow)",
        "token-sm": "var(--shadow-sm)",
        "token-lg": "var(--shadow-lg)",
      },
    },
  },
  plugins: [],
};
