import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./admin.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1280px" } },
    extend: {
      fontFamily: { sans: ['"Be Vietnam Pro"', "system-ui", "sans-serif"] },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        success: { DEFAULT: "hsl(var(--success))", foreground: "hsl(var(--success-foreground))" },
        warning: { DEFAULT: "hsl(var(--warning))", foreground: "hsl(var(--warning-foreground))" },
        paddy: { DEFAULT: "hsl(var(--paddy))", foreground: "hsl(var(--paddy-foreground))" },
      },
      // Bo góc vừa phải, tất cả suy từ --radius (8px): sm 4, md 6, lg 8, xl 10, 2xl 12, 3xl 14
      borderRadius: { sm: "calc(var(--radius) - 4px)", md: "calc(var(--radius) - 2px)", lg: "var(--radius)", xl: "calc(var(--radius) + 2px)", "2xl": "calc(var(--radius) + 4px)", "3xl": "calc(var(--radius) + 6px)" },
      boxShadow: { soft: "0 1px 2px rgb(31 74 40 / .06), 0 8px 24px -12px rgb(31 74 40 / .18)", lift: "0 12px 32px -12px rgb(31 74 40 / .28)" },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
        "fade-up": { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        sweep: { from: { top: "6%" }, to: { top: "92%" } },
        float: { "0%, 100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-8px)" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-up": "fade-up .35s ease-out both",
        sweep: "sweep 1.4s ease-in-out infinite alternate",
        float: "float 5s ease-in-out infinite",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
