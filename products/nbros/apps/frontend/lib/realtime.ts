type RealtimeSession = {
  access_token: string;
  websocket_url: string;
};

async function getRealtimeSession(): Promise<RealtimeSession> {
  let response = await fetch("/api/auth/realtime-session", {
    cache: "no-store",
    credentials: "same-origin",
  });

  if (response.status === 401) {
    const refresh = await fetch("/api/auth/refresh", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
    });
    if (refresh.ok) {
      response = await fetch("/api/auth/realtime-session", {
        cache: "no-store",
        credentials: "same-origin",
      });
    }
  }

  if (!response.ok) throw new Error("NBros realtime session unavailable");
  return (await response.json()) as RealtimeSession;
}

export async function connectCentralRealtime(): Promise<WebSocket> {
  const session = await getRealtimeSession();

  return new Promise((resolve, reject) => {
    const socket = new WebSocket(session.websocket_url);
    let settled = false;
    const timeout = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      socket.close();
      reject(new Error("Central realtime authentication timed out"));
    }, 10000);

    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ type: "auth", access_token: session.access_token }));
    });

    socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(String(event.data)) as { type?: string };
        if (message.type === "ready" && !settled) {
          settled = true;
          window.clearTimeout(timeout);
          resolve(socket);
        }
      } catch {
        // Ignore non-JSON frames until the authenticated ready frame arrives.
      }
    });

    socket.addEventListener("close", () => {
      if (!settled) {
        settled = true;
        window.clearTimeout(timeout);
        reject(new Error("Central realtime authentication closed before ready"));
      }
    });

    socket.addEventListener("error", () => {
      if (!settled) {
        settled = true;
        window.clearTimeout(timeout);
        reject(new Error("Central realtime connection failed"));
      }
    });
  });
}
