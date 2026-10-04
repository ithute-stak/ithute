/// <reference lib="webworker" />

type WorkerRequest = {
  id: string;
  operation: "byte-stats";
  bytes: ArrayBuffer;
};

function byteStats(data: Uint8Array) {
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

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  if (request.operation !== "byte-stats") {
    self.postMessage({ id: request.id, ok: false, error: "Unknown browser engine operation" });
    return;
  }
  self.postMessage({ id: request.id, ok: true, result: byteStats(new Uint8Array(request.bytes)) });
};

export {};
