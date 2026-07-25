from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

HealthCategory = Literal[
    "milestone",
    "seizure",
    "breathing_episode",
    "gi",
    "sleep",
    "motor",
    "communication",
    "scoliosis_orthopedic",
    "growth_measurement",
    "medication_change",
    "appointment",
    "illness",
    "other",
]


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
    timeline_display_name: str | None = None

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.medications:
            missing.append("medications")
        if not self.allergies:
            missing.append("allergies")
        if not self.notes:
            missing.append("notes")
        return missing


class HealthEvent(BaseModel):
    id: str
    org_id: str
    event_date: str
    category: str
    title: str
    details: dict = {}
    notes: str | None = None
    severity: str | None = None
    logged_at: str
