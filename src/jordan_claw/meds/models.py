from __future__ import annotations

from pydantic import BaseModel


class MedicationEntry(BaseModel):
    """One current medication. dose and prescriber are free text on purpose."""

    name: str
    rxcui: str | None = None
    dose: str | None = None
    prescriber: str | None = None


class MedicationProfile(BaseModel):
    org_id: str
    medications: list[MedicationEntry] = []
    allergies: str | None = None
    notes: str | None = None

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.medications:
            missing.append("medications")
        if not self.allergies:
            missing.append("allergies")
        if not self.notes:
            missing.append("notes")
        return missing
