import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// Hai ứng dụng riêng (client và admin) dùng chung src/shared; build ra dist/ để Flask phục vụ.
// Lúc phát triển: Vite ở cổng 5173, chuyển tiếp /api, /uploads, /static sang Flask 5000.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": resolve(__dirname, "src") } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: { input: { client: resolve(__dirname, "index.html"), admin: resolve(__dirname, "admin.html") } },
  },
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:5000", "/uploads": "http://127.0.0.1:5000", "/static": "http://127.0.0.1:5000" },
  },
});
