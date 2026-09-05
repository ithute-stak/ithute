'use client'

import * as React from 'react'

import {
    GenderEnum,
} from '@/types/shared.primitive'

import { StudentRead } from '@/types/student'

export function useStudentFilters(
    data: StudentRead[] = []
) {
    /* ================= FILTERS ================= */

    const [search, setSearch] =
        React.useState('')

    const [classId, setClassId] =
        React.useState<string>('all')

    const [gender, setGender] =
        React.useState<string>('all')

    const [nationality, setNationality] =
        React.useState<string>('all')

    /* ================= NATIONALITIES ================= */

    const nationalities =
        React.useMemo(() => {
            return Array.from(
                new Set(
                    data
                        .map(
                            (student) =>
                                student.user
                                    .person
                                    ?.nationality
                        )
                        .filter(Boolean)
                )
            ).sort()
        }, [data])

    /* ================= FILTERED ================= */

    const filtered = React.useMemo(() => {
        return data.filter((student) => {
            const fullName = `
                ${student.user.person?.first_name ?? ''}
                ${student.user.person?.last_name ?? ''}
            `.toLowerCase()

            const matchesSearch =
                fullName.includes(
                    search.toLowerCase()
                ) ||
                student.admission_number
                    ?.toLowerCase()
                    .includes(
                        search.toLowerCase()
                    )

            const matchesClass =
                classId === 'all' ||
                student.class_id === classId

            const matchesGender =
                gender === 'all' ||
                student.user.person
                    ?.gender === gender

            const matchesNationality =
                nationality === 'all' ||
                student.user.person
                    ?.nationality ===
                nationality

            return (
                matchesSearch &&
                matchesClass &&
                matchesGender &&
                matchesNationality
            )
        })
    }, [
        data,
        search,
        classId,
        gender,
        nationality,
    ])

    /* ================= PAGINATION ================= */

    const ITEMS_PER_PAGE = 20

    const [page, setPage] =
        React.useState(1)

    const totalPages = Math.max(
        1,
        Math.ceil(
            filtered.length /
            ITEMS_PER_PAGE
        )
    )

    const currentPage = Math.min(
        page,
        totalPages
    )

    const paginatedStudents =
        React.useMemo(() => {
            const start =
                (currentPage - 1) *
                ITEMS_PER_PAGE

            const end =
                start + ITEMS_PER_PAGE

            return filtered.slice(
                start,
                end
            )
        }, [
            filtered,
            currentPage,
        ])

    return {
        /* filters */
        search,
        setSearch,

        classId,
        setClassId,

        gender,
        setGender,

        nationality,
        setNationality,

        nationalities,

        /* data */
        filtered,
        paginatedStudents,

        /* pagination */
        page: currentPage,
        setPage,

        totalPages,
        ITEMS_PER_PAGE,

        /* enums */
        genders: [
            GenderEnum.male,
            GenderEnum.female,
        ],
    }
}