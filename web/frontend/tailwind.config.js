/** @type {import('tailwindcss').Config} */
// 색상/타이포는 assets/web_example/dais_mlops/DESIGN.md 에서 가져옴.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#004ac6",
        "primary-container": "#2563eb",
        "on-primary": "#ffffff",
        "on-primary-container": "#eeefff",
        secondary: "#495c95",
        "on-secondary": "#ffffff",
        tertiary: "#943700",
        "on-tertiary": "#ffffff",
        error: "#ba1a1a",
        "error-container": "#ffdad6",
        "on-error-container": "#93000a",
        background: "#faf8ff",
        surface: "#faf8ff",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#f3f3fe",
        "surface-container": "#ededf9",
        "surface-container-high": "#e7e7f3",
        "surface-container-highest": "#e1e2ed",
        "surface-variant": "#e1e2ed",
        "on-surface": "#191b23",
        "on-surface-variant": "#434655",
        "inverse-surface": "#2e3039",
        "inverse-on-surface": "#f0f0fb",
        outline: "#737686",
        "outline-variant": "#c3c6d7",
        // 의미적 상태 (Slate scale + functional)
        success: "#16a34a",
        warning: "#d97706",
      },
      fontFamily: {
        sans: ["Inter", "Pretendard", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "0.375rem",
        sm: "0.25rem",
        md: "0.375rem",
        lg: "0.5rem",
        xl: "0.75rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04)",
        modal: "0 4px 12px rgba(0,0,0,0.05)",
      },
    },
  },
  plugins: [],
};
