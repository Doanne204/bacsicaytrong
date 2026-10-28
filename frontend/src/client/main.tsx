import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/shared/ui/misc";
import App from "./App";
import "@/shared/styles/globals.css";

// Sau khi build lại, tab đang mở vẫn trỏ tới các file trang cũ (tên có mã băm) đã bị xóa -> tải trang mới hỏng.
// Vite báo lỗi này qua sự kiện vite:preloadError: tải lại trang một lần để lấy bản mới (chặn lặp vô hạn nếu lỗi thật).
window.addEventListener("vite:preloadError", (e) => {
  try {
    const last = Number(sessionStorage.getItem("chunk-reload") || 0);
    if (Date.now() - last < 10_000) return;
    sessionStorage.setItem("chunk-reload", String(Date.now()));
  } catch { /* không có sessionStorage: vẫn tải lại */ }
  e.preventDefault();
  window.location.reload();
});

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <TooltipProvider delayDuration={300}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </TooltipProvider>
      <Toaster position="top-center" richColors closeButton toastOptions={{ className: "font-sans" }} />
    </QueryClientProvider>
  </React.StrictMode>,
);
