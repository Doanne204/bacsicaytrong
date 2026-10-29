export interface Stats {
  users: number; locked: number; diagnoses: number; today: number; posts: Record<string, number>; pending: number; comments: number; flagged: number;
  ratings: number; rating_avg: number; samples: number; samples_pending: number; reports_open: number; keys: { total: number; enabled: number; cooling: number };
  daily: { day: string; n: number }[]; top: { plant: string; disease: string; n: number }[]; classes: { class_name: string; n: number; approved: number }[];
}
export interface AdminUser { id: number; username: string; email: string; phone: string | null; role: "user" | "admin"; locked: number; created: string; scans: number; posts: number; comments: number; ratings: number; is_me: boolean }
export interface AdminComment { id: number; content: string; created: string; ai_decision: string | null; post_id: number; username: string; post_excerpt: string | null }
export interface AdminRating { id: number; stars: number; comment: string; created: string; username: string; plant: string | null; disease: string | null; image_url: string | null; source: string | null }
export interface AdminKey { id: number; label: string; masked: string | null; enabled: boolean; ok_count: number; fail_count: number; last_used: string | null; last_error: string | null; last_error_at: string | null; created: string; cooling: Record<string, number> }
export interface KeysResponse { keys: AdminKey[]; models: string; fast_models: string; default_models: string; default_fast_models: string }
export interface Sample {
  id: number; class_name: string; confidence: number; status: "pending" | "approved"; created: string; diagnosis_id: number | null; username: string | null;
  plant: string | null; disease: string | null; source: string | null; image_url: string | null;
}
/** Báo kết quả sai của người dùng: nhãn hiện tại (cur_*) và nhãn người dùng đề xuất (class_name hoặc plant/disease tự ghi). */
export interface AdminReport {
  id: number; diagnosis_id: number; username: string | null; class_name: string | null; plant: string | null; disease: string; note: string | null;
  old_label: string | null; status: "open" | "accepted" | "rejected"; answer: string | null; created: string; reviewed: string | null;
  cur_plant: string | null; cur_disease: string | null; cur_raw: string | null; source: string | null; confidence: number | null;
  image_url: string | null; kind: "leaf" | "pest"; top: { raw: string; plant: string; disease: string; prob: number }[];
}
