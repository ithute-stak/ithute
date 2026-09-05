import os
from datetime import datetime
from typing import Tuple

def get_next_receipt_count(student, academic_year: str) -> int:

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

    # Get all existing pdf files
    existing_files = [
        f for f in os.listdir(folder)
        if f.endswith(".pdf")
    ]

    # Count + 1
    return len(existing_files) + 1