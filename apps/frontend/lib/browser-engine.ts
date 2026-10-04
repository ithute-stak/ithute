export type BrowserByteStats = {
  bytes: number;
  lines: number;
  ascii: number;
  nonAscii: number;
};

type WorkerRequest = {
  id: string;
  operation: "byte-stats";
  bytes: ArrayBuffer;
};

type WorkerResponse = {
  id: string;
  ok: boolean;
  result?: BrowserByteStats;
  error?: string;
};

function fallbackByteStats(data: Uint8Array): BrowserByteStats {
  let ascii = 0;
  let lines = data.byteLength ? 1 : 0;
  for (const value of data) {
    if (value < 128) ascii += 1;
    if (value === 10) lines += 1;
  }
  return {
    bytes: data.byteLength,
    lines,
    ascii,
    nonAscii: data.byteLength - ascii,
  };
}

let worker: Worker | null = null;
let sequence = 0;
const pending = new Map<string, {
  resolve: (value: BrowserByteStats) => void;
  reject: (reason?: unknown) => void;
}>();

function getWorker(): Worker | null {
  if (typeof window === "undefined" || typeof Worker === "undefined") return null;
  if (worker) return worker;
  try {
    worker = new Worker(new URL("../workers/ithute-compute.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const item = pending.get(event.data.id);
      if (!item) return;
      pending.delete(event.data.id);
      if (event.data.ok && event.data.result) item.resolve(event.data.result);
      else item.reject(new Error(event.data.error || "Browser engine task failed"));
    };
    worker.onerror = () => {
      for (const item of pending.values()) item.reject(new Error("Browser compute worker failed"));
      pending.clear();
      worker?.terminate();
      worker = null;
    };
    return worker;
  } catch {
    worker = null;
    return null;
  }
}

export async function browserByteStats(data: Uint8Array): Promise<{ result: BrowserByteStats; engine: "worker" | "typescript-fallback" }> {
  const active = getWorker();
  if (!active) return { result: fallbackByteStats(data), engine: "typescript-fallback" };

  const id = `byte-stats-${Date.now()}-${sequence++}`;
  const owned = data.slice().buffer;
  const request: WorkerRequest = { id, operation: "byte-stats", bytes: owned };
  try {
    const result = await new Promise<BrowserByteStats>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        pending.delete(id);
        reject(new Error("Browser compute worker timed out"));
      }, 5000);
      pending.set(id, {
        resolve: (value) => {
          window.clearTimeout(timeout);
          resolve(value);
        },
        reject: (reason) => {
          window.clearTimeout(timeout);
          reject(reason);
        },
      });
      active.postMessage(request, [owned]);
    });
    return { result, engine: "worker" };
  } catch {
    return { result: fallbackByteStats(data), engine: "typescript-fallback" };
  }
}
