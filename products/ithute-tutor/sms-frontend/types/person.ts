import {GenderEnum, UUID} from "@/types/shared.primitive";

export interface PersonBase {
    first_name: string;
    last_name: string;
    gender: GenderEnum;
    date_of_birth: string; // ISO date string
    nationality: string;
    national_id?: string | null;
}

export interface PersonCreate extends PersonBase {}

export interface PersonUpdate {
    first_name?: string;
    last_name?: string;
    gender?: GenderEnum;
    date_of_birth?: string;
    nationality?: string;
    national_id?: string | null;
}

export interface PersonRead extends PersonBase {
    id: UUID;
}