from enum import StrEnum


class CoverageStatus(StrEnum):
    UNCOVERED = "non_presidiato"
    PARTIAL = "parzialmente_coperto"
    SATURATED = "saturo"


def classify_coverage(results: list[dict]) -> CoverageStatus:
    if not results:
        return CoverageStatus.UNCOVERED
    if len(results) < 5:
        return CoverageStatus.PARTIAL
    return CoverageStatus.SATURATED
