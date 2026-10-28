import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useMe } from "@/shared/hooks/use-me";
import { Shell } from "./layout/Shell";
import { PageSkeleton } from "./layout/PageSkeleton";
import { LegacyHashRedirect } from "./layout/LegacyHashRedirect";

const Landing = lazy(() => import("./pages/Landing"));
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Verify = lazy(() => import("./pages/Verify"));
const Forgot = lazy(() => import("./pages/Forgot"));
const Home = lazy(() => import("./pages/Home"));
const Scan = lazy(() => import("./pages/Scan"));
const Diagnosis = lazy(() => import("./pages/Diagnosis"));
const History = lazy(() => import("./pages/History"));
const Chat = lazy(() => import("./pages/Chat"));
const Ratings = lazy(() => import("./pages/Ratings"));
const Profile = lazy(() => import("./pages/Profile"));
const Notifications = lazy(() => import("./pages/Notifications"));
const NewPost = lazy(() => import("./pages/NewPost"));
const PostView = lazy(() => import("./pages/PostView"));
const SharedResult = lazy(() => import("./pages/SharedResult"));
const PrintSheet = lazy(() => import("./pages/PrintSheet"));
const Journal = lazy(() => import("./pages/Journal"));
const JournalDetail = lazy(() => import("./pages/JournalDetail"));
const Weather = lazy(() => import("./pages/Weather"));

export default function App() {
  const { me, loading } = useMe();
  const loc = useLocation();
  if (loc.hash.startsWith("#/")) return <LegacyHashRedirect />;
  if (loading) return <PageSkeleton full />;
  const guard = (el: JSX.Element) => (me ? el : <Navigate to="/login" replace state={{ from: loc.pathname }} />);
  const pub = (el: JSX.Element) => (me ? <Navigate to="/home" replace /> : el);
  return (
    <Suspense fallback={<PageSkeleton full />}>
      <Routes>
        <Route path="/" element={me ? <Navigate to="/home" replace /> : <Landing />} />
        <Route path="/login" element={pub(<Login />)} />
        <Route path="/register" element={pub(<Register />)} />
        <Route path="/verify" element={pub(<Verify />)} />
        <Route path="/forgot" element={pub(<Forgot />)} />
        <Route path="/diagnosis/:id/print" element={guard(<PrintSheet />)} />
        <Route element={guard(<Shell />)}>
          <Route path="/home" element={<Home />} />
          <Route path="/home/mine" element={<Home mine />} />
          <Route path="/scan" element={<Scan />} />
          <Route path="/scan/camera" element={<Scan camera />} />
          <Route path="/diagnosis/:id" element={<Diagnosis />} />
          <Route path="/history" element={<History />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/chat/:id" element={<Chat />} />
          <Route path="/ratings" element={<Ratings />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/post" element={<NewPost />} />
          {/* chia sẻ kết quả tra cứu (React Router 6 không hiểu đoạn "d:did" nên phải là một đoạn riêng) */}
          <Route path="/share/:did" element={<NewPost />} />
          <Route path="/p/:id" element={<PostView />} />
          <Route path="/kq/:id" element={<SharedResult />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/journal/:id" element={<JournalDetail />} />
          <Route path="/weather" element={<Weather />} />
        </Route>
        <Route path="*" element={<Navigate to={me ? "/home" : "/"} replace />} />
      </Routes>
    </Suspense>
  );
}
