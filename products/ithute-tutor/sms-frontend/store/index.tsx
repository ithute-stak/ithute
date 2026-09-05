"use client"
import { Provider } from "react-redux"
import { PersistGate } from "redux-persist/integration/react"
import {persistor, store} from "@/store/store";
import React from "react";
import "@/store/auth_init"
import AnimatedLoader from "@/components/animated_loader";


export default function ReduxProvider({children}:Readonly<{children:React.ReactNode}>) {
    return (
        <Provider store={store}>
            <PersistGate loading={<AnimatedLoader />} persistor={persistor}>
                {children}
            </PersistGate>
        </Provider>
    )
}