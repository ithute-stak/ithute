import os


def build_receipt_path(student, academic_year: str, count: int):

    base_dir = "media"

    enrol = getattr(student, "admission_number", None) or str(student.id)

    folder = os.path.join(
        base_dir,
        "students",
        enrol,
        academic_year,
        "fees"
    )

    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(folder, f"{count}th.pdf")

    return file_path