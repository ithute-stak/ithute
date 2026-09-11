type RealtimeSession = {
  access_token: string;
  websocket_url: string;
};

export async function connectCentralRealtime(): Promise<WebSocket> {
  const sessionResponse = await fetch("/api/auth/realtime-session", { cache: "no-store", credentials: "same-origin" });
  if (!sessionResponse.ok) throw new Error("NBros realtime session unavailable");
  const session = (await sessionResponse.json()) as RealtimeSession;

  return new Promise((resolve, reject) => {
    const socket = new WebSocket(session.websocket_url);
    const timeout = window.setTimeout(() => {
      socket.close();
      reject(new Error("Central realtime authentication timed out"));
    }, 10000);

    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ type: "auth", access_token: session.access_token }));
    });
    socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(String(event.data)) as { type?: string };
        if (message.type === "ready") {
          window.clearTimeout(timeout);
          resolve(socket);
        }
      } catch {
        // Ignore non-JSON frames until the authenticated ready frame arrives.
      }
    });
    socket.addEventListener("error", () => {
      window.clearTimeout(timeout);
      reject(new Error("Central realtime connection failed"));
    });
  });
}
