import { Link } from "react-router-dom";
import { ScanLine, Sparkles, MessageCircle, ArrowLeft } from "lucide-react";
import { Brand } from "@/shared/components/brand";

/** Bố cục đăng nhập/đăng ký: 2 cột trên máy tính (ảnh + điểm nổi bật bên trái), 1 cột trên điện thoại. */
export function AuthLayout({ title, text, children }: { title: string; text: string; children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden overflow-hidden bg-[#1F4A28] p-12 text-white lg:flex lg:flex-col">
        <img src="/static/img/intro/hero-leaf.jpg" alt="" className="absolute inset-0 h-full w-full object-cover opacity-30" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0E2416] via-[#1F4A28]/70 to-transparent" />
        <div className="relative"><Link to="/"><Brand light /></Link></div>
        <div className="relative mt-auto max-w-lg">
          <h1 className="text-4xl font-extrabold leading-tight xl:text-5xl">Chụp một chiếc lá, biết cây đang bị bệnh gì</h1>
          <ul className="mt-8 space-y-4 text-[#DCEBD6]">
            {[[ScanLine, "Nhận diện 38 bệnh trên 14 loại cây và 204 loài sâu hại bằng mô hình học sâu"], [Sparkles, "Cây chưa có trong dữ liệu được AI phân tích và ghi nhớ cho lần sau"], [MessageCircle, "Hỏi trợ lý AI cách xử lý, chia sẻ kinh nghiệm với bà con"]].map(([Icon, t], i) => {
              const I = Icon as React.ComponentType<{ className?: string }>;
              return <li key={i} className="flex gap-3"><I className="mt-0.5 h-5 w-5 shrink-0 text-paddy" /><span>{t as string}</span></li>;
            })}
          </ul>
        </div>
      </section>
      <section className="flex flex-col px-5 py-6 sm:px-10 lg:justify-center">
        <div className="mb-8 flex items-center justify-between lg:hidden">
          <Link to="/"><Brand /></Link>
          <Link to="/" className="inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground"><ArrowLeft className="h-4 w-4" />Giới thiệu</Link>
        </div>
        <div className="mx-auto w-full max-w-md animate-fade-up">
          <h2 className="text-2xl font-extrabold md:text-3xl">{title}</h2>
          <p className="mb-6 mt-1 text-muted-foreground">{text}</p>
          {children}
        </div>
      </section>
    </div>
  );
}
