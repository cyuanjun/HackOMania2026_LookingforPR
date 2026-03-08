import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        skywash: "#f5fbff",
        panel: "#ffffff",
        accent: "#0f766e",
        danger: "#b91c1c",
        warning: "#d97706",
        calm: "#2563eb",
        success: "#166534"
      },
      boxShadow: {
        panel: "0 8px 24px rgba(15, 23, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;

