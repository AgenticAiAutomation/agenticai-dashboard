import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#2563EB",
        "primary-hover": "#1D4ED8",
        secondary: "#64748b",
        success: "#10b981",
        warning: "#f59e0b",
        danger: "#ef4444",
        // Dark surface ramp: `bg` is the page, `surface` the cards, `raised`
        // for inputs and rows sitting on top of a card.
        bg: "#0B1120",
        surface: "#111827",
        raised: "#1B2434",
        line: "#243044",
        muted: "#94A3B8",
      },
      fontSize: {
        kpi: ["3rem", { lineHeight: "1", letterSpacing: "-0.02em" }],
        label: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.06em" }],
      },
    },
  },
  plugins: [],
};
export default config;
