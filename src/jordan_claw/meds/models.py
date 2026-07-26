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
    date_of_birth: str | None = None

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.medications:
            missing.append("medications")
        if not self.allergies:
            missing.append("allergies")
        if not self.notes:
            missing.append("notes")
        return missing


class CareContact(BaseModel):
    """One care-team contact. role is free text ("mom", "cardiology", "pharmacy")."""

    role: str
    name: str
    phone: str | None = None


class CareProfile(BaseModel):
    org_id: str
    diagnoses: list[str] = []
    critical_flags: list[str] = []
    seizure_plan: str | None = None
    baselines: str | None = None
    communication: str | None = None
    routines: str | None = None
    escalation: str | None = None
    contacts: list[CareContact] = []

    def empty_sections(self) -> list[str]:
        empty: list[str] = []
        if not self.diagnoses:
            empty.append("diagnoses")
        if not self.critical_flags:
            empty.append("critical_flags")
        if not self.seizure_plan:
            empty.append("seizure_plan")
        if not self.baselines:
            empty.append("baselines")
        if not self.communication:
            empty.append("communication")
        if not self.routines:
            empty.append("routines")
        if not self.escalation:
            empty.append("escalation")
        if not self.contacts:
            empty.append("contacts")
        return empty


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
