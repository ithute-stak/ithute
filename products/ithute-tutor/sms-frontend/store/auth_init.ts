import { injectAuth } from "@/lib/axios-setup"
import { store } from "@/store/store"
import {clearAuth, setToken} from "@/store/features/slice/authSlice";

injectAuth({
    getToken: () => store.getState().auth.token,
    setToken: (token) => {
        if (token) {
            store.dispatch(setToken(token))
        } else {
            store.dispatch(clearAuth())
        }
    },
})