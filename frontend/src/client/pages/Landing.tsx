import { Link } from "react-router-dom";
import { ArrowRight, Bug, Camera, CheckCircle2, Leaf, MessageCircle, ScanLine, Sparkles, Users, Wifi, Smartphone } from "lucide-react";
import { Brand } from "@/shared/components/brand";
import { ThemeToggle } from "@/shared/components/common";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";

/** Trang giới thiệu khi chưa đăng nhập. Ảnh minh họa ở /static/img/intro (ảnh chụp màn hình ứng dụng + ảnh lá/sâu hại từ bộ dữ liệu). */
const FEATURES = [
  { icon: ScanLine, title: "Chụp là biết bệnh", text: "Mô hình MobileNetV3 nhận diện 38 tình trạng bệnh trên 14 loại cây ngay trên điện thoại, chỉ sau vài giây.", img: "shot-result.jpg" },
  { icon: Bug, title: "Nhận diện sâu hại", text: "Mô hình thứ hai học từ 108.000 ảnh của 204 loài sâu, nhện, ốc hại và thiên địch, kèm cách phòng trừ theo IPM.", img: "shot-pest.jpg" },
  { icon: Sparkles, title: "AI học thêm cây mới", text: "Cây chưa có trong dữ liệu được Gemini phân tích, kết quả được ghi nhớ để lần sau nhận ra ngay.", img: "shot-scan.jpg" },
  { icon: MessageCircle, title: "Trợ lý AI và cộng đồng", text: "Hỏi tiếp về cách xử lý, chia sẻ kết quả lên bảng tin, bình luận và học kinh nghiệm từ bà con.", img: "shot-chat.jpg" },
];
const STEPS = [
  { icon: Camera, title: "Chụp hoặc chọn ảnh", text: "Một chiếc lá có vết bệnh, hoặc con sâu trên cây. Đủ sáng, lấy nét, nền đơn giản." },
  { icon: Leaf, title: "Hệ thống phân tích", text: "Mô hình học sâu chạy trước; ảnh lạ được AI kiểm tra thêm và ghi nhớ." },
  { icon: CheckCircle2, title: "Nhận kết quả và cách xử lý", text: "Tên bệnh hoặc loài sâu, độ tin cậy, triệu chứng, hướng phòng trừ, và trợ lý AI để hỏi tiếp." },
];

export default function Landing() {
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4 md:px-8">
          <Brand className="mr-auto" />
          <ThemeToggle />
          <Button asChild variant="ghost" className="hidden sm:inline-flex"><Link to="/login">Đăng nhập</Link></Button>
          <Button asChild><Link to="/register">Đăng ký</Link></Button>
        </div>
      </header>

      {/* Mở đầu */}
      <section className="relative overflow-hidden">
        <div className="leaf-pattern absolute inset-0 -z-10" />
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-12 md:grid-cols-2 md:px-8 md:py-20">
          <div className="animate-fade-up">
            <Badge variant="paddy" className="mb-4"><Sparkles />Đề tài: phát hiện sâu bệnh cây trồng bằng AI</Badge>
            <h1 className="text-4xl font-extrabold leading-[1.1] md:text-5xl lg:text-6xl">Chụp một chiếc lá, <span className="text-primary">biết cây đang bị gì</span></h1>
            <p className="mt-5 max-w-lg text-lg text-muted-foreground">Bác sĩ cây trồng nhận diện bệnh trên lá và sâu hại từ ảnh chụp điện thoại, đưa ra cách xử lý và trợ lý AI để hỏi tiếp. Miễn phí cho bà con nông dân.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg"><Link to="/register">Bắt đầu ngay<ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="outline"><Link to="/login">Tôi đã có tài khoản</Link></Button>
            </div>
            <dl className="mt-10 grid grid-cols-3 gap-4 border-t pt-6">
              {[["38", "bệnh trên lá"], ["204", "loài sâu hại"], ["14+", "loại cây trồng"]].map(([n, l]) => (
                <div key={l}><dt className="text-3xl font-extrabold text-primary">{n}</dt><dd className="text-sm text-muted-foreground">{l}</dd></div>
              ))}
            </dl>
          </div>
          <div className="relative mx-auto w-full max-w-md">
            <div className="absolute -inset-6 -z-10 rounded-3xl bg-gradient-to-br from-secondary via-paddy/20 to-transparent blur-2xl" />
            <PhoneFrame src="/static/img/intro/shot-home.jpg" alt="Màn hình chính ứng dụng trên điện thoại" className="animate-float" />
            <img src="/static/img/intro/leaf-card.jpg" alt="" className="absolute -left-6 bottom-10 hidden w-36 rotate-[-8deg] rounded-2xl border-4 border-card shadow-lift sm:block" />
            <img src="/static/img/intro/pest-card.jpg" alt="" className="absolute -right-6 top-16 hidden w-36 rotate-[8deg] rounded-2xl border-4 border-card shadow-lift sm:block" />
          </div>
        </div>
      </section>

      {/* Tính năng */}
      <section className="mx-auto max-w-6xl px-4 py-14 md:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-extrabold md:text-4xl">Mọi thứ bà con cần, trong một ứng dụng</h2>
          <p className="mt-3 text-muted-foreground">Từ lúc thấy lá có dấu hiệu lạ đến khi biết phải làm gì, không cần chờ cán bộ kỹ thuật đến tận ruộng.</p>
        </div>
        {/* Điện thoại: trượt ngang từng tính năng (scroll-snap); máy tính: xen kẽ chữ / ảnh */}
        <div className="-mx-4 mt-8 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-4 no-scrollbar md:hidden">
          {FEATURES.map((f) => (
            <article key={f.title} className="w-[82vw] max-w-[340px] shrink-0 snap-center rounded-2xl border bg-card p-4 shadow-soft">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-secondary text-primary"><f.icon className="h-5 w-5" /></span>
              <h3 className="mt-3 text-lg font-extrabold">{f.title}</h3>
              <p className="mt-1 min-h-[4.5rem] text-sm text-muted-foreground">{f.text}</p>
              <PhoneFrame src={`/static/img/intro/${f.img}`} alt={f.title} className="mx-auto mt-4 w-full max-w-[220px]" />
            </article>
          ))}
        </div>
        <p className="text-center text-xs text-muted-foreground md:hidden">Vuốt sang để xem các tính năng khác</p>
        <div className="mt-12 hidden space-y-16 md:block">
          {FEATURES.map((f, i) => (
            <div key={f.title} className={`grid items-center gap-8 md:grid-cols-2 ${i % 2 ? "md:[&>*:first-child]:order-2" : ""}`}>
              <div>
                <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-secondary text-primary"><f.icon className="h-6 w-6" /></span>
                <h3 className="mt-4 text-2xl font-extrabold">{f.title}</h3>
                <p className="mt-2 text-muted-foreground">{f.text}</p>
              </div>
              <PhoneFrame src={`/static/img/intro/${f.img}`} alt={f.title} className="mx-auto w-full max-w-[280px]" />
            </div>
          ))}
        </div>
      </section>

      {/* Cách hoạt động */}
      <section className="bg-secondary/50 py-14">
        <div className="mx-auto max-w-6xl px-4 md:px-8">
          <h2 className="text-center text-3xl font-extrabold md:text-4xl">Ba bước đơn giản</h2>
          <ol className="mt-10 grid gap-6 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="rounded-3xl border bg-card p-6 shadow-soft">
                <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-full bg-primary text-sm font-extrabold text-primary-foreground">{i + 1}</span><s.icon className="h-6 w-6 text-primary" /></div>
                <h3 className="mt-4 text-lg font-bold">{s.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Máy tính + điện thoại */}
      <section className="mx-auto max-w-6xl px-4 py-14 md:px-8">
        <div className="grid items-center gap-8 md:grid-cols-[1fr_1.3fr]">
          <div>
            <h2 className="text-3xl font-extrabold md:text-4xl">Dùng trên điện thoại hay máy tính đều tiện</h2>
            <ul className="mt-6 space-y-3 text-muted-foreground">
              {[[Smartphone, "Trên điện thoại: chụp trực tiếp bằng camera, thao tác một tay, thêm vào màn hình chính như ứng dụng"], [Wifi, "Chạy trong mạng LAN của gia đình, hợp tác xã, không cần Internet để nhận diện bằng mô hình"], [Users, "Cộng đồng: đăng bài, bình luận, chia sẻ kết quả tra cứu; AI kiểm duyệt nội dung xấu"]].map(([Icon, t], i) => {
                const I = Icon as React.ComponentType<{ className?: string }>;
                return <li key={i} className="flex gap-3"><I className="mt-0.5 h-5 w-5 shrink-0 text-primary" />{t as string}</li>;
              })}
            </ul>
          </div>
          <div className="rounded-3xl border bg-card p-2 shadow-lift"><img src="/static/img/intro/shot-desktop.jpg" alt="Giao diện trên máy tính" className="w-full rounded-2xl" /></div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16 md:px-8">
        <div className="relative overflow-hidden rounded-3xl bg-[#1F4A28] px-6 py-12 text-center text-white md:py-16">
          <img src="/static/img/intro/hero-leaf.jpg" alt="" className="absolute inset-0 h-full w-full object-cover opacity-20" />
          <div className="relative">
            <h2 className="text-3xl font-extrabold md:text-4xl">Sẵn sàng tra cứu chiếc lá đầu tiên?</h2>
            <p className="mx-auto mt-3 max-w-xl text-[#DCEBD6]">Tạo tài khoản trong 30 giây. Mỗi lượt tra cứu giúp hệ thống học thêm và chính xác hơn cho bà con.</p>
            <Button asChild size="lg" variant="paddy" className="mt-8"><Link to="/register">Tạo tài khoản miễn phí<ArrowRight /></Link></Button>
          </div>
        </div>
      </section>
      <footer className="border-t py-6 text-center text-sm text-muted-foreground">Bác sĩ cây trồng · Đề tài khóa luận: phát hiện sâu bệnh cây trồng · PlantVillage, INSECT204, MobileNetV3, YOLO11, Gemini</footer>
    </div>
  );
}

function PhoneFrame({ src, alt, className }: { src: string; alt: string; className?: string }) {
  return (
    <div className={`relative aspect-[9/19] overflow-hidden rounded-[1.6rem] border-[6px] border-[#1a2a1e] bg-[#1a2a1e] shadow-lift ${className || ""}`}>
      <div className="absolute left-1/2 top-2 z-10 h-5 w-24 -translate-x-1/2 rounded-full bg-[#1a2a1e]" />
      <img src={src} alt={alt} className="h-full w-full rounded-[1.2rem] object-cover object-top" loading="lazy" />
    </div>
  );
}
