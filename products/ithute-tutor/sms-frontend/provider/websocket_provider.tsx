"use client"

import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react"

import { public_api_url } from "@/api/consts"

export type WebSocketMessage<T = unknown> = {
    event?: string
    type?: string
    channel?: string
    data?: T
}

type WebSocketContextType = {
    isConnected: boolean
    lastMessage: WebSocketMessage | null
    sendMessage: (message: unknown) => void
    reconnect: () => void
}

const WebSocketContext = createContext<WebSocketContextType | null>(null)

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
    const socketRef = useRef<WebSocket | null>(null)
    const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const reconnectAttemptsRef = useRef(0)
    const connectRef = useRef<(() => void) | null>(null)

    const [isConnected, setIsConnected] = useState(false)
    const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)

    const getSocketUrl = useCallback(() => {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws"

        if (public_api_url.startsWith("/")) {
            return `${protocol}://${window.location.host}${public_api_url}/ws/events`
        }

        const apiUrl = new URL(public_api_url)
        return `${protocol}://${apiUrl.host}${apiUrl.pathname.replace(/\/$/, "")}/ws/events`
    }, [])

    const clearTimers = useCallback(() => {
        if (heartbeatRef.current) {
            clearInterval(heartbeatRef.current)
            heartbeatRef.current = null
        }
        if (reconnectRef.current) {
            clearTimeout(reconnectRef.current)
            reconnectRef.current = null
        }
    }, [])

    const cleanupSocket = useCallback(() => {
        clearTimers()
        const socket = socketRef.current
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.close()
        }
        socketRef.current = null
        setIsConnected(false)
    }, [clearTimers])

    const connect = useCallback(() => {
        const existingSocket = socketRef.current
        if (
            existingSocket &&
            (existingSocket.readyState === WebSocket.OPEN || existingSocket.readyState === WebSocket.CONNECTING)
        ) {
            return
        }

        const socket = new WebSocket(getSocketUrl())
        socketRef.current = socket

        socket.onopen = () => {
            setIsConnected(true)
            reconnectAttemptsRef.current = 0
            clearTimers()
            heartbeatRef.current = setInterval(() => {
                if (socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({ type: "PING" }))
                }
            }, 25000)
        }

        socket.onmessage = (event: MessageEvent<string>) => {
            try {
                const message = JSON.parse(event.data) as WebSocketMessage
                if (message.type !== "PONG") setLastMessage(message)
            } catch (error) {
                console.error("Invalid websocket message", error)
            }
        }

        socket.onclose = () => {
            setIsConnected(false)
            if (heartbeatRef.current) {
                clearInterval(heartbeatRef.current)
                heartbeatRef.current = null
            }
            const attempt = reconnectAttemptsRef.current + 1
            reconnectAttemptsRef.current = attempt
            reconnectRef.current = setTimeout(
                () => connectRef.current?.(),
                Math.min(1000 * attempt, 10000),
            )
        }

        socket.onerror = () => socket.close()
    }, [getSocketUrl, clearTimers])

    useEffect(() => {
        connectRef.current = connect
    }, [connect])

    const reconnect = useCallback(() => {
        cleanupSocket()
        connectRef.current?.()
    }, [cleanupSocket])

    useEffect(() => {
        const timer = window.setTimeout(() => connectRef.current?.(), 300)
        const handleOnline = () => reconnect()
        const handleVisibilityChange = () => {
            if (document.visibilityState === "visible") reconnect()
        }

        window.addEventListener("online", handleOnline)
        document.addEventListener("visibilitychange", handleVisibilityChange)
        return () => {
            window.clearTimeout(timer)
            window.removeEventListener("online", handleOnline)
            document.removeEventListener("visibilitychange", handleVisibilityChange)
            cleanupSocket()
        }
    }, [reconnect, cleanupSocket])

    const sendMessage = useCallback((message: unknown) => {
        const socket = socketRef.current
        if (!socket || socket.readyState !== WebSocket.OPEN) return
        socket.send(JSON.stringify(message))
    }, [])

    const value = useMemo(
        () => ({ isConnected, lastMessage, sendMessage, reconnect }),
        [isConnected, lastMessage, sendMessage, reconnect],
    )

    return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>
}

export function useWebSocket() {
    const context = useContext(WebSocketContext)
    if (!context) throw new Error("useWebSocket must be used inside WebSocketProvider")
    return context
}
