import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/shared/ui/misc";
import App from "./App";
import "@/shared/styles/globals.css";

// Trang quản trị ở /admin, điều hướng bằng hash (/admin#/posts) nên Flask chỉ cần một route
const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <TooltipProvider delayDuration={300}>
        <HashRouter>
          <App />
        </HashRouter>
      </TooltipProvider>
      <Toaster position="top-right" richColors closeButton toastOptions={{ className: "font-sans" }} />
    </QueryClientProvider>
  </React.StrictMode>,
);
