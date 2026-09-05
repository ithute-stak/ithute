import {UserCreate, UserRead} from "@/types/user";
import {UUID} from "node:crypto";

export interface ParentBase {}

export interface ParentCreate {
    user: UserCreate;
}

export interface ParentRead {
    id: UUID;
    user: UserRead;
}

export interface StudentBasic {
    id: UUID;
    admission_number: string;
}

export interface ParentWithChildren extends ParentRead {
    children: StudentBasic[];
}