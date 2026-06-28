import type { Config } from "tailwindcss";

// Tailwind v4 is CSS-first (tokens live in src/styles/globals.css via @theme),
// but this config is loaded via `@config` for content detection and the
// class-based dark mode strategy.
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
} satisfies Config;
