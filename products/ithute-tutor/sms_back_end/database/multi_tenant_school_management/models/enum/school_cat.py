import enum


class SchoolCategory(str, enum.Enum):
    pre_school = "pre_school"
    junior_school = "junior_school"
    primary_school = "primary_school"
    basic_education_school = "basic_education_school"
    secondary_school = "secondary_school"
    high_school = "high_school"
    junior_college = "junior_college"
    learning_center = "learning_center"