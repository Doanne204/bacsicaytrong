import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";

/* Giọng nói bằng Web Speech API có sẵn trong trình duyệt (Chrome trên Android và máy tính hỗ trợ tiếng Việt);
   không gửi âm thanh lên máy chủ của ứng dụng. */
type Recognition = { lang: string; interimResults: boolean; continuous: boolean; start(): void; stop(): void; abort(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null; onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null };
const SR = (window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition });
export const speechInputAvailable = () => !!(SR.SpeechRecognition || SR.webkitSpeechRecognition);
export const speechOutputAvailable = () => "speechSynthesis" in window;

function pickVoice() {
  const vs = speechSynthesis.getVoices();
  return vs.find((v) => v.lang.toLowerCase().startsWith("vi")) || null;
}

/** Nút đọc văn bản thành tiếng (bấm lại để dừng). */
export function SpeakButton({ text, className, label = "Đọc kết quả", variant = "outline" }: { text: string; className?: string; label?: string; variant?: "outline" | "ghost" }) {
  const [on, setOn] = useState(false);
  useEffect(() => () => speechSynthesis?.cancel(), []);
  if (!speechOutputAvailable()) return null;
  const toggle = () => {
    if (on) { speechSynthesis.cancel(); setOn(false); return; }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/\s+/g, " ").slice(0, 3000));
    u.lang = "vi-VN"; const v = pickVoice(); if (v) u.voice = v; u.rate = 1;
    u.onend = () => setOn(false); u.onerror = () => setOn(false);
    speechSynthesis.speak(u); setOn(true);
  };
  return <Button type="button" variant={variant} className={className} onClick={toggle} aria-pressed={on}>{on ? <VolumeX /> : <Volume2 />}{on ? "Dừng đọc" : label}</Button>;
}

/** Nút micro: nhận dạng tiếng Việt, gọi onText với câu nói (chỉ hiện khi trình duyệt hỗ trợ). */
export function MicButton({ onText, onInterim, disabled, className }: { onText: (t: string) => void; onInterim?: (t: string) => void; disabled?: boolean; className?: string }) {
  const [on, setOn] = useState(false);
  const rec = useRef<Recognition | null>(null);
  useEffect(() => () => rec.current?.abort(), []);
  if (!speechInputAvailable()) return null;
  const toggle = () => {
    if (on) { rec.current?.stop(); return; }
    const R = (SR.SpeechRecognition || SR.webkitSpeechRecognition)!;
    const r = new R();
    r.lang = "vi-VN"; r.interimResults = true; r.continuous = false;
    let final = "";
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) { const t = e.results[i][0].transcript; if (e.results[i].isFinal) final += t; else interim += t; }
      onInterim?.(final + interim);
    };
    r.onend = () => { setOn(false); rec.current = null; if (final.trim()) onText(final.trim()); };
    r.onerror = () => { setOn(false); rec.current = null; };
    rec.current = r; r.start(); setOn(true);
  };
  return (
    <Button type="button" variant="ghost" size="icon" disabled={disabled} onClick={toggle} aria-label={on ? "Dừng nghe" : "Nói câu hỏi"} title="Hỏi bằng giọng nói" className={cn(on && "bg-destructive/15 text-destructive animate-pulse", className)}>
      {on ? <MicOff /> : <Mic />}
    </Button>
  );
}
