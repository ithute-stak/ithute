import { combineReducers, configureStore } from "@reduxjs/toolkit";
import { persistReducer, persistStore } from "redux-persist";

import storage from "@/store/storage";
import authReducer from "@/store/features/slice/authSlice";
import usersReducer from "@/store/features/slice/user_slices";
import schoolReducer from "@/store/features/slice/schoolSlice";
import classReducer from "@/store/features/slice/classSlice";
import gradeReducer from "@/store/features/slice/gradeSlice";
import teacherReducer from "@/store/features/slice/teacherSlice";
import studentReducer from "@/store/features/slice/studentSlice";
import studentAttendanceReducer from "@/store/features/slice/studentAttendanceSlice";
import schoolFeeConfigurationReducer from "@/store/features/slice/finance/schoolFeeConfiguration/schoolFeeConfigurationSlice";
import feePlanReducer from "@/store/features/slice/finance/feePlan";

// Keep redux-persist compatibility for the existing provider, but never persist
// central authentication data. Browser identity is revalidated through the
// Tutor backend's HttpOnly central-Auth session cookies on each application load.
const authPersistConfig = {
    key: "auth",
    storage,
    whitelist: [] as string[],
};

const rootReducer = combineReducers({
    auth: persistReducer(authPersistConfig, authReducer),
    users: usersReducer,
    schools: schoolReducer,
    class: classReducer,
    grade: gradeReducer,
    teacher: teacherReducer,
    students: studentReducer,
    studentAttendance: studentAttendanceReducer,
    feePlan: feePlanReducer,
    schoolFeeConfiguration: schoolFeeConfigurationReducer,
});

export const store = configureStore({
    reducer: rootReducer,
    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        }),
});

export const persistor = persistStore(store);

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
