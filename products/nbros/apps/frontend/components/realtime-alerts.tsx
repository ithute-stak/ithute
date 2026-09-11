"use client";

import { useEffect, useRef, useState } from "react";

import { connectCentralRealtime } from "@/lib/realtime";

type FleetAlertFrame = {
  type?: string;
  event_id?: string;
  route?: string;
  title?: string;
  body?: string;
  severity?: string;
};

export default function RealtimeAlerts() {
  const [alert, setAlert] = useState<FleetAlertFrame | null>(null);
  const clearTimer = useRef<number | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let stopped = false;
    let reconnectTimer: number | null = null;
    let heartbeatTimer: number | null = null;

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== null) return;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, 5000);
    };

    const connect = async () => {
      try {
        socket = await connectCentralRealtime();
        if (stopped) {
          socket.close();
          return;
        }

        heartbeatTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "ping" }));
          }
        }, 30000);

        socket.addEventListener("message", (event) => {
          try {
            const frame = JSON.parse(String(event.data)) as FleetAlertFrame;
            if (frame.type !== "fleet.alert.changed") return;

            setAlert(frame);
            if (clearTimer.current !== null) {
              window.clearTimeout(clearTimer.current);
            }
            clearTimer.current = window.setTimeout(() => setAlert(null), 12000);

            if (frame.event_id && socket?.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: "ack", event_id: frame.event_id, state: "received" }));
            }

            if ("Notification" in window && Notification.permission === "granted") {
              const notification = new Notification(frame.title || "NBros Fleet alert", {
                body: frame.body || "Fleet status changed.",
                tag: frame.event_id || undefined,
              });
              notification.onclick = () => {
                window.focus();
                if (frame.route) window.location.assign(frame.route);
                notification.close();
              };
            }
          } catch {
            // Ignore protocol frames that are not JSON Fleet alerts.
          }
        });

        socket.addEventListener("close", () => {
          if (heartbeatTimer !== null) {
            window.clearInterval(heartbeatTimer);
            heartbeatTimer = null;
          }
          scheduleReconnect();
        });
      } catch {
        scheduleReconnect();
      }
    };

    void connect();

    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
      if (clearTimer.current !== null) window.clearTimeout(clearTimer.current);
      socket?.close();
    };
  }, []);

  if (!alert) return null;

  return (
    <button
      type="button"
      aria-live="polite"
      onClick={() => alert.route && window.location.assign(alert.route)}
      style={{
        position: "fixed",
        top: 18,
        right: 18,
        zIndex: 9999,
        width: "min(390px, calc(100vw - 36px))",
        padding: "14px 16px",
        border: "1px solid rgba(255,255,255,.18)",
        borderRadius: 14,
        background: alert.severity === "red" ? "#790d29" : "#35434c",
        color: "#fff",
        boxShadow: "0 18px 50px rgba(35,15,22,.28)",
        textAlign: "left",
        cursor: alert.route ? "pointer" : "default",
      }}
    >
      <strong style={{ display: "block", marginBottom: 5 }}>
        {alert.title || "Fleet alert"}
      </strong>
      <span style={{ display: "block", fontSize: 13, lineHeight: 1.45, opacity: 0.92 }}>
        {alert.body || "Fleet status changed."}
      </span>
    </button>
  );
}
