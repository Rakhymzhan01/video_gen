/**
 * Frontend service for video generation.
 * Uses API Gateway via Nginx route /api/ -> 127.0.0.1:8000
 */

function getAccessToken(): string | null {
  try {
    // На всякий случай проверим, что мы в браузере
    if (typeof window === "undefined") return null;

    const raw = localStorage.getItem("auth_tokens");
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    return parsed.access_token || parsed.token || null;
  } catch {
    return null;
  }
}

export async function generateVideo(
  prompt: string,
  imageFile?: File | null
): Promise<string> {
  const fd = new FormData();
  fd.append("prompt", prompt);

  if (imageFile) {
    fd.append("image", imageFile);
  }

  // Достаём токен и готовим заголовки
  const token = getAccessToken();
  const headers: HeadersInit = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch("/api/v1/videos/generate-public", {
    method: "POST",
    body: fd,
    headers,            // <– добавили
    credentials: "include",
  });

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      msg = data?.detail || data?.message || JSON.stringify(data);
    } catch {}
    throw new Error(msg);
  }

  const data: any = await res.json();

  // Most common response options:
  const url =
    data?.video_url ||
    data?.videoUrl ||
    data?.file_url ||
    data?.fileUrl ||
    data?.url;

  if (typeof url === "string" && url.length > 0) return url;

  // If response returns an id, build file URL that nginx rewrites:
  // /<uuid>/file -> /api/v1/videos/<uuid>/file
  const id = data?.id || data?.video_id || data?.videoId;
  if (typeof id === "string" && id.length > 0) return `/${id}/file`;

  throw new Error("Unexpected API response: no video url/id");
}
