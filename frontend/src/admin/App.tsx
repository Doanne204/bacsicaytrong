import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useMe } from "@/shared/hooks/use-me";
import { api } from "@/shared/lib/api";
import { Skeleton } from "@/shared/ui/misc";
import { Console } from "./layout/Console";
import Gate from "./pages/Gate";
import type { Stats } from "./lib/types";

const Overview = lazy(() => import("./pages/Overview"));
const Posts = lazy(() => import("./pages/Posts"));
const Comments = lazy(() => import("./pages/Comments"));
const Users = lazy(() => import("./pages/Users"));
const Ratings = lazy(() => import("./pages/Ratings"));
const Data = lazy(() => import("./pages/Data"));
const Keys = lazy(() => import("./pages/Keys"));
const Stats = lazy(() => import("./pages/Stats"));
const Models = lazy(() => import("./pages/Models"));

export default function App() {
  const { me, loading } = useMe();
  const stats = useQuery({ queryKey: ["admin", "stats"], queryFn: () => api<Stats>("/api/admin/stats"), enabled: me?.role === "admin", refetchInterval: 60_000 });
  if (loading) return <div className="p-8"><Skeleton className="h-10 w-1/3" /><Skeleton className="mt-4 h-64" /></div>;
  if (!me || me.role !== "admin") return <Gate me={me} />;
  return (
    <Console stats={stats.data}>
      <Suspense fallback={<div className="space-y-3"><Skeleton className="h-8 w-1/3" /><Skeleton className="h-64" /></div>}>
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview stats={stats.data} refetch={() => stats.refetch()} />} />
          <Route path="/posts" element={<Posts onChange={() => stats.refetch()} />} />
          <Route path="/comments" element={<Comments onChange={() => stats.refetch()} />} />
          <Route path="/users" element={<Users />} />
          <Route path="/ratings" element={<Ratings />} />
          <Route path="/data" element={<Data stats={stats.data} />} />
          <Route path="/keys" element={<Keys />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/models" element={<Models />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </Suspense>
    </Console>
  );
}
