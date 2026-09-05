import enum


class UserRole(str, enum.Enum):
    # =====================================================
    # SYSTEM
    # =====================================================
    super_admin = "super_admin"

    # =====================================================
    # SCHOOL MANAGEMENT
    # =====================================================
    school_admin = "school_admin"
    principal = "principal"
    vice_principal = "vice_principal"
    registrar = "registrar"

    # =====================================================
    # ACADEMICS
    # =====================================================
    head_of_department = "head_of_department"
    teacher = "teacher"
    class_teacher = "class_teacher"
    librarian = "librarian"
    lab_assistant = "lab_assistant"

    # =====================================================
    # STUDENTS
    # =====================================================
    student = "student"
    prefect = "prefect"

    # =====================================================
    # PARENTS
    # =====================================================
    parent = "parent"
    guardian = "guardian"

    # =====================================================
    # FINANCE
    # =====================================================
    bursar = "bursar"
    accountant = "accountant"
    cashier = "cashier"

    # =====================================================
    # HUMAN RESOURCES
    # =====================================================
    hr_manager = "hr_manager"
    payroll_officer = "payroll_officer"

    # =====================================================
    # ADMISSIONS
    # =====================================================
    admissions_officer = "admissions_officer"

    # =====================================================
    # ICT
    # =====================================================
    ict_manager = "ict_manager"
    system_administrator = "system_administrator"
    support_officer = "support_officer"

    # =====================================================
    # TRANSPORT
    # =====================================================
    transport_manager = "transport_manager"
    driver = "driver"

    # =====================================================
    # HOSTEL
    # =====================================================
    hostel_master = "hostel_master"
    hostel_matron = "hostel_matron"

    # =====================================================
    # HEALTH
    # =====================================================
    nurse = "nurse"
    counselor = "counselor"

    # =====================================================
    # PROCUREMENT
    # =====================================================
    procurement_officer = "procurement_officer"
    store_keeper = "store_keeper"

    # =====================================================
    # SECURITY
    # =====================================================
    security_officer = "security_officer"

    # =====================================================
    # GENERAL EMPLOYEES
    # =====================================================
    employee = "employee"