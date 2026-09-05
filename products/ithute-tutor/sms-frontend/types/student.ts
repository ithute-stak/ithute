import {UserCreate, UserRead} from "@/types/user";
import {UUID} from "@/types/shared.primitive";

export interface StudentBase {
    admission_number: string;
    class_id?: UUID | null;
}

export interface StudentCreate extends StudentBase {
    user: UserCreate;
}

export interface StudentRead extends StudentBase {
    id: UUID;
    user: UserRead;
}

export interface ParentBasic {
    id: UUID;
}

export interface StudentWithParents extends StudentRead {
    parents: ParentBasic[];
}