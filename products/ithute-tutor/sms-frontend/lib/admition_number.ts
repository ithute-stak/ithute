import { StudentRead } from "@/types/student"

export function generateAdmissionNumber(
    students: StudentRead[]
): string {
    const year = new Date().getFullYear().toString()

    // create a Set for fast lookup
    const existing = new Set(
        students.map((s) => s.admission_number)
    )

    let attempts = 0

    while (attempts < 1000000) {
        const random = Math.floor(Math.random() * 999999) + 1

        const padded = random.toString().padStart(6, "0")

        const admissionNumber = `${year}${padded}`

        if (!existing.has(admissionNumber)) {
            return admissionNumber
        }

        attempts++
    }

    throw new Error("Unable to generate unique admission number")
}