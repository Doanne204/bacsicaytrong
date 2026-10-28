import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

/** Liên kết cũ dạng #/p/12, #/diagnosis/3 (trong thông báo, dấu trang) -> đường dẫn mới. */
export function LegacyHashRedirect() {
  const nav = useNavigate();
  useEffect(() => {
    const path = window.location.hash.replace(/^#/, "");
    if (path.startsWith("/admin")) { window.location.replace("/admin" + path.slice(6).replace(/^\//, "#/")); return; }
    nav(path === "/" ? "/home" : path, { replace: true });
  }, [nav]);
  return null;
}
