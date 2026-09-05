// store/features/thunks/classThunks.ts

import { createAsyncThunk } from "@reduxjs/toolkit"
import * as academicAPI from "@/api/academic/actions"

import {
    ClassCreate,
    ClassUpdate
} from "@/types/classes"


/* ========================================
   GET ALL CLASSES
======================================== */

export const getClassesThunk = createAsyncThunk(
    "classes/getAll",
    async () => {
        return await academicAPI.getClasses()
    }
)


/* ========================================
   GET SINGLE CLASS
======================================== */

export const getClassThunk = createAsyncThunk(
    "classes/getOne",
    async (id: string) => {
        return await academicAPI.getClass(id)
    }
)


/* ========================================
   CREATE CLASS
======================================== */

export const createClassThunk = createAsyncThunk(
    "classes/create",
    async (payload: ClassCreate) => {
        return await academicAPI.createClass(payload)
    }
)


/* ========================================
   UPDATE CLASS
======================================== */

export const updateClassThunk = createAsyncThunk(
    "classes/update",
    async ({
               id,
               payload,
           }: {
        id: string
        payload: ClassUpdate
    }) => {
        return await academicAPI.updateClass(id, payload)
    }
)


/* ========================================
   DELETE CLASS
======================================== */

export const deleteClassThunk = createAsyncThunk(
    "classes/delete",
    async (id: string) => {
        await academicAPI.deleteClass(id)
        return id
    }
)