import { useCallback, useState } from "react";

const KEY = "bsct-sidebar";

/** Thanh bên trái trên máy tính: mở rộng (có chữ) hoặc thu gọn (chỉ biểu tượng); nhớ lựa chọn trong localStorage. */
export function useSidebar() {
  const [collapsed, set] = useState(() => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } });
  const toggle = useCallback(() => set((c) => { try { localStorage.setItem(KEY, c ? "0" : "1"); } catch { /* chế độ riêng tư */ } return !c; }), []);
  return { collapsed, toggle };
}
