"use client"

import React, {
    createContext,
    useContext,
    useEffect,
    useMemo,
    useReducer,
} from "react"

import { useWebSocket } from "@/provider/websocket_provider"

export type AppNotification = {
    id: string
    title: string
    message: string
    event: string
    channel?: string
    isRead: boolean
    createdAt: string
    data?: unknown
}

type NotificationContextType = {
    notifications: AppNotification[]
    unreadCount: number
    markAllAsRead: () => void
    clearNotifications: () => void
}

const NotificationContext =
    createContext<NotificationContextType | null>(null)

type NotificationAction =
    | {
    type: "ADD_NOTIFICATION"
    payload: AppNotification
}
    | {
    type: "MARK_ALL_AS_READ"
}
    | {
    type: "CLEAR_NOTIFICATIONS"
}

function notificationReducer(
    state: AppNotification[],
    action: NotificationAction
): AppNotification[] {

    switch (action.type) {

        case "ADD_NOTIFICATION":

            return [
                action.payload,
                ...state,
            ]

        case "MARK_ALL_AS_READ":

            return state.map((item) => ({
                ...item,
                isRead: true,
            }))

        case "CLEAR_NOTIFICATIONS":

            return []

        default:
            return state
    }
}

export function NotificationProvider({
                                         children,
                                     }: {
    children: React.ReactNode
}) {

    const { lastMessage } =
        useWebSocket()

    const [
        notifications,
        dispatch,
    ] = useReducer(
        notificationReducer,
        []
    )

    useEffect(() => {

        if (!lastMessage) {
            return
        }

        const event =
            lastMessage.event ||
            lastMessage.type ||
            "UNKNOWN_EVENT"

        const notification: AppNotification = {

            id: crypto.randomUUID(),

            title: formatTitle(event),

            message: buildMessage(
                event,
                lastMessage.data
            ),

            event,

            channel: lastMessage.channel,

            isRead: false,

            createdAt:
                new Date().toISOString(),

            data: lastMessage.data,
        }

        queueMicrotask(() => {

            dispatch({
                type: "ADD_NOTIFICATION",
                payload: notification,
            })

        })

    }, [lastMessage])

    const unreadCount =
        notifications.filter(
            (item) => !item.isRead
        ).length

    const markAllAsRead = () => {

        dispatch({
            type: "MARK_ALL_AS_READ",
        })
    }

    const clearNotifications = () => {

        dispatch({
            type: "CLEAR_NOTIFICATIONS",
        })
    }

    const value = useMemo(
        () => ({
            notifications,
            unreadCount,
            markAllAsRead,
            clearNotifications,
        }),
        [
            notifications,
            unreadCount,
        ]
    )

    return (
        <NotificationContext.Provider value={value}>
            {children}
        </NotificationContext.Provider>
    )
}

export function useNotifications() {

    const context =
        useContext(NotificationContext)

    if (!context) {

        throw new Error(
            "useNotifications must be used inside NotificationProvider"
        )
    }

    return context
}

function formatTitle(event: string) {

    return event
        .replaceAll("_", " ")
        .toLowerCase()
        .replace(/\b\w/g, (char) =>
            char.toUpperCase()
        )
}

function buildMessage(
    event: string,
    data: unknown
) {

    if (
        event === "PAYMENT_COMPLETED" &&
        typeof data === "object" &&
        data !== null
    ) {

        const value = data as {
            transaction?: {
                amount_paid?: number,
                phone?: string,
                student_id?:string,
                payment_id?:string
            }
        }

        return `Payment of M${
            value.transaction?.amount_paid ?? ""
        }.00 completed successfully`
    }

    return "New realtime event received"
}