/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#070d18",
          900: "#0b1220",
          850: "#0e1628",
          800: "#111c33",
          700: "#1a2742",
          600: "#243354",
        },
        accent: { DEFAULT: "#22d3ee", dim: "#0e7490" },
        ok: "#34d399",
        warn: "#fbbf24",
        bad: "#f87171",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
