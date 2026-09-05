import {UserCreate, UserRead} from "@/types/user";
import {UUID} from "@/types/shared.primitive";

export interface TeacherBase {
    school_id: UUID;
}

export interface TeacherCreate extends TeacherBase {
    user: UserCreate;
}

export interface TeacherRead extends TeacherBase {
    id: UUID;
    user: UserRead;
}