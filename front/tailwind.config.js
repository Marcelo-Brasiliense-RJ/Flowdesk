/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
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
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
