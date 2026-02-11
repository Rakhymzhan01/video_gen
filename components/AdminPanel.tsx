import React, { useMemo, useState } from "react";

type PostType = "news" | "blog";
type Post = {
  id: string;
  type: PostType;
  title: string;
  content: string;
  imageDataUrl?: string;
  createdAt: number;
};

const KEY = "duutz_posts_v1";

function readAll(): Post[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeAll(posts: Post[]) {
  localStorage.setItem(KEY, JSON.stringify(posts));
}

function listPosts(type: PostType): Post[] {
  return readAll()
    .filter((p) => p.type === type)
    .sort((a, b) => b.createdAt - a.createdAt);
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Failed to read file"));
    r.readAsDataURL(file);
  });
}

export default function AdminPanel() {
  const [type, setType] = useState<PostType>("news");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  const posts = useMemo(() => listPosts(type), [type, refresh]);

  const publish = async () => {
    setStatus(null);
    if (!title.trim() || !content.trim()) {
      setStatus("❌ Title and text are required");
      return;
    }

    let imageDataUrl: string | undefined = undefined;
    if (image) imageDataUrl = await fileToDataUrl(image);

    const p: Post = {
      id: crypto.randomUUID(),
      type,
      title: title.trim(),
      content: content.trim(),
      imageDataUrl,
      createdAt: Date.now(),
    };

    const all = readAll();
    all.push(p);
    writeAll(all);

    setTitle("");
    setContent("");
    setImage(null);
    setStatus("✅ Published");
    setRefresh((x) => x + 1);
  };

  const remove = (id: string) => {
    const all = readAll().filter((p) => p.id !== id);
    writeAll(all);
    setRefresh((x) => x + 1);
  };

  return (
    <div className="w-full p-6 bg-gray-800/50 backdrop-blur-sm border border-gray-700 rounded-2xl shadow-2xl">
      <div className="grid md:grid-cols-3 gap-4">
        <div className="min-w-0">
          <label className="block text-sm font-medium text-gray-300 mb-2">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as PostType)}
            className="w-full bg-gray-900/50 border border-gray-600 rounded-lg p-3 text-gray-200"
          >
            <option value="news">News</option>
            <option value="blog">Blog</option>
          </select>
        </div>

        <div className="md:col-span-2 min-w-0">
          <label className="block text-sm font-medium text-gray-300 mb-2">Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-gray-900/50 border border-gray-600 rounded-lg p-3 text-gray-200"
            placeholder="Topic / Title"
          />
        </div>
      </div>

      <div className="mt-4 min-w-0">
        <label className="block text-sm font-medium text-gray-300 mb-2">Text</label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={7}
          className="w-full bg-gray-900/50 border border-gray-600 rounded-lg p-3 text-gray-200"
          placeholder="Write your text..."
        />
      </div>

      <div className="mt-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <label className="block text-sm font-medium text-gray-300 mb-2">Image</label>
          <input type="file" accept="image/*" onChange={(e) => setImage(e.target.files?.[0] || null)} />
        </div>

        <button
          onClick={publish}
          className="bg-indigo-600 text-white font-bold py-3 px-6 rounded-lg hover:bg-indigo-700 transition-colors"
        >
          Publish
        </button>
      </div>

      {status ? <div className="mt-3 text-sm text-gray-300">{status}</div> : null}

      <div className="mt-8">
        <div className="text-lg font-bold text-white mb-3">Saved {type === "news" ? "News" : "Blog"}</div>

        {posts.length === 0 ? (
          <div className="text-gray-400">No posts yet.</div>
        ) : (
          <div className="grid md:grid-cols-2 gap-6">
            {posts.map((p) => (
              <div
                key={p.id}
                className="rounded-2xl bg-white/5 border border-white/10 overflow-hidden min-w-0"
              >
                {p.imageDataUrl ? (
                  <img src={p.imageDataUrl} className="w-full h-44 object-cover" />
                ) : null}

                <div className="p-5 min-w-0">
                  <div className="text-xl font-bold text-white break-words">{p.title}</div>

                  {/* ВАЖНО: переносим длинные слова/строки */}
                  <div className="text-gray-300 mt-2 whitespace-pre-wrap break-words overflow-hidden">
                    {p.content}
                  </div>

                  <div className="text-xs text-gray-400 mt-3">
                    {new Date(p.createdAt).toLocaleString()}
                  </div>

                  <button
                    onClick={() => remove(p.id)}
                    className="mt-4 px-3 py-2 rounded-lg bg-red-500/20 border border-red-500/30 text-red-200 hover:bg-red-500/30"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
