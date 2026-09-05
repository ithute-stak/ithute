from enum import Enum


class FeeStructureType(str, Enum):
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    ANNUAL = "annual"