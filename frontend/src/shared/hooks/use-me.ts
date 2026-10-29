import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, send, type Me } from "@/shared/lib/api";
import { disablePush } from "@/shared/lib/pwa";

/** Người dùng đang đăng nhập (null nếu chưa). Dùng chung cho client và admin. */
export function useMe() {
  const q = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try { return await api<Me>("/api/me"); } catch (e) { if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null; throw e; }
    },
    staleTime: 30_000,
    retry: false,
  });
  return { me: q.data ?? null, loading: q.isLoading, refetch: q.refetch };
}

export function useLogout() {
  const qc = useQueryClient();
  return async () => {
    await disablePush().catch(() => {});  // thiết bị này thôi nhận thông báo của tài khoản vừa đăng xuất
    await send("/api/logout", {});
    qc.setQueryData(["me"], null);
    qc.clear();
  };
}
