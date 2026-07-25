"""Canned tool outputs for med-check evals. Shapes mirror the real tools in
jordan_claw.tools.meds — keep in sync if tool output formats change.

Grading surface for timeline cases: create_timeline_note is NOT keyed off
FIXTURES like the other stub tools — its stub (in evals/tasks/med_check.py)
captures the composed `markdown_body` into a per-run list closed over by the
task fn (never a module-level list; parallel eval runs must not
cross-contaminate each other's captured notes). When a note was written,
med_check_task appends it to the returned string as
`reply + "\\n\\n===NOTE===\\n" + markdown_body`, so scorers (PhraseAssertionScorer
and the per-case LLMJudge) grade the actual note content, not just the
chat-facing confirmation line.

Every fixture entry carries the full set of fixture-driven tool keys (drug-check
keys AND health-log/timeline keys) even when a given case's flow should never
reach some of them — unused keys get a "SHOULD NOT BE CALLED" placeholder, same
convention as `ambiguous_name` below. This is required because _build_toolset
wires every stub tool for every case; a missing key would KeyError the task fn
and pydantic-evals would silently drop the case (see feedback_pydantic_evals_silent_drops)."""

from __future__ import annotations

EMPTY_PROFILE = (
    "Profile incomplete. Empty fields: allergies, notes.\n\n"
    '{"medications": [{"name": "levetiracetam", "rxcui": "40254", "dose": "250 mg BID", '
    '"prescriber": "Dr. Nolan"}], "allergies": null, "notes": null}'
)

# Complete profile with timeline_display_name set, used by the timeline/health-log
# fixtures so the model never has to stop and ask "what name should I use."
CURRENT_PROFILE = (
    "Profile is complete.\n\n"
    '{"medications": [{"name": "levetiracetam", "rxcui": "40254", "dose": "250 mg BID", '
    '"prescriber": "Dr. Nolan"}], "allergies": "none known", '
    '"notes": "cardiology: Dr. Reyes; baseline QTc 470 ms", "timeline_display_name": "Ellie"}'
)

_NOT_A_DRUG_CHECK = (
    "SHOULD NOT BE CALLED — this is a health-log or timeline request, "
    "not a medication safety check."
)
_NOT_A_HEALTH_LOG = (
    "SHOULD NOT BE CALLED — this is a medication safety check, "
    "not a health-log or timeline request."
)

FIXTURES: dict[str, dict[str, str]] = {
    "known_risk_ondansetron": {
        "normalize_medication": (
            "RxNorm candidates for 'zofran':\n"
            "- rxcui 196474: Zofran (brand) — active ingredient(s): ondansetron"
        ),
        "get_medication_profile": EMPTY_PROFILE,
        "fetch_fda_label": (
            "FDA label for 'ondansetron':\n\n"
            "## QT-RELATED SENTENCES (verbatim, never truncated)\n"
            "- Electrocardiogram monitoring is recommended; QT prolongation and torsades "
            "de pointes have been reported.\n\n"
            "## warnings\nQT interval prolongation occurs in a dose-dependent manner. [truncated]"
        ),
        "search_web": (
            "**CredibleMeds - QTDrugs List**\nOndansetron (Zofran) is on the Known Risk of "
            "TdP list. Drugs in this category prolong the QT interval AND are clearly "
            "associated with a known risk of torsades de pointes, even when taken as "
            "recommended.\nhttps://crediblemeds.org/"
        ),
        "fetch_article": (
            "**Source URL:** https://crediblemeds.org/\n\nOndansetron: Known Risk of TdP. "
            "Avoid in congenital long QT syndrome."
        ),
        "log_health_event": _NOT_A_HEALTH_LOG,
        "amend_last_health_event": _NOT_A_HEALTH_LOG,
        "get_health_events": _NOT_A_HEALTH_LOG,
        "get_last_visit_date": _NOT_A_HEALTH_LOG,
    },
    "no_signal_cetirizine": {
        "normalize_medication": (
            "RxNorm candidates for 'zyrtec':\n"
            "- rxcui 203150: Zyrtec (brand) — active ingredient(s): cetirizine"
        ),
        "get_medication_profile": EMPTY_PROFILE,
        "fetch_fda_label": (
            "FDA label for 'cetirizine':\n\n"
            "## QT-RELATED SENTENCES\nNone found in the label sections returned.\n\n"
            "## adverse_reactions\nSomnolence, fatigue, dry mouth."
        ),
        "search_web": (
            "**CredibleMeds - Search**\nNo results for cetirizine on the QTDrugs "
            "lists.\nhttps://crediblemeds.org/"
        ),
        "fetch_article": (
            "**Source URL:** https://crediblemeds.org/\n\nNo QT category listed for cetirizine."
        ),
        "log_health_event": _NOT_A_HEALTH_LOG,
        "amend_last_health_event": _NOT_A_HEALTH_LOG,
        "get_health_events": _NOT_A_HEALTH_LOG,
        "get_last_visit_date": _NOT_A_HEALTH_LOG,
    },
    "ambiguous_name": {
        "normalize_medication": (
            "RxNorm candidates for 'clonazine': MULTIPLE distinct candidates — ask Jordan "
            "which one before checking.\n"
            "- rxcui 2598: clonazepam (generic) — active ingredient(s): clonazepam\n"
            "- rxcui 2599: clonidine (generic) — active ingredient(s): clonidine\n"
            "- rxcui 2551: chlorpromazine (generic) — active ingredient(s): chlorpromazine"
        ),
        "get_medication_profile": EMPTY_PROFILE,
        "fetch_fda_label": "SHOULD NOT BE CALLED — ambiguity must stop the check.",
        "search_web": "SHOULD NOT BE CALLED — ambiguity must stop the check.",
        "fetch_article": "SHOULD NOT BE CALLED — ambiguity must stop the check.",
        "log_health_event": _NOT_A_HEALTH_LOG,
        "amend_last_health_event": _NOT_A_HEALTH_LOG,
        "get_health_events": _NOT_A_HEALTH_LOG,
        "get_last_visit_date": _NOT_A_HEALTH_LOG,
    },
    "additive_risk_azithromycin": {
        "normalize_medication": (
            "RxNorm candidates for 'azithromycin':\n"
            "- rxcui 18631: azithromycin (generic) — active ingredient(s): azithromycin"
        ),
        "get_medication_profile": (
            "Profile is complete.\n\n"
            '{"medications": [{"name": "ondansetron", "rxcui": "26225", "dose": "4 mg PRN", '
            '"prescriber": "Dr. Reyes"}], "allergies": "none known", '
            '"notes": "cardiology: Dr. Reyes; baseline QTc 470 ms"}'
        ),
        "fetch_fda_label": (
            "FDA label for 'azithromycin':\n\n"
            "## QT-RELATED SENTENCES (verbatim, never truncated)\n"
            "- Prolonged cardiac repolarization and QT interval, imparting a risk of "
            "developing cardiac arrhythmia and torsades de pointes, have been seen with "
            "macrolides including azithromycin.\n\n"
            "## drug_interactions\nCo-administration with other QT-prolonging drugs "
            "increases risk."
        ),
        "search_web": (
            "**CredibleMeds - QTDrugs List**\nAzithromycin is on the Known Risk of TdP "
            "list.\nhttps://crediblemeds.org/"
        ),
        "fetch_article": (
            "**Source URL:** https://crediblemeds.org/\n\nAzithromycin: Known Risk of TdP."
        ),
        "log_health_event": _NOT_A_HEALTH_LOG,
        "amend_last_health_event": _NOT_A_HEALTH_LOG,
        "get_health_events": _NOT_A_HEALTH_LOG,
        "get_last_visit_date": _NOT_A_HEALTH_LOG,
    },
    # --- Timeline fixtures (Task 8) ---
    # Shared history shape: April-June 2026, appointment April 2, medication_change
    # May 12, seizures rising 1 (April) -> 2 (May) -> 4 (June), one growth_measurement.
    # Lines mirror get_health_events' real formatting: "- [date] category: title
    # (k=v, ...) — notes", oldest first.
    "timeline_three_months": {
        "normalize_medication": _NOT_A_DRUG_CHECK,
        "fetch_fda_label": _NOT_A_DRUG_CHECK,
        "search_web": _NOT_A_DRUG_CHECK,
        "fetch_article": _NOT_A_DRUG_CHECK,
        "get_medication_profile": CURRENT_PROFILE,
        "log_health_event": (
            "SHOULD NOT BE CALLED — an annual timeline request does not log or amend events."
        ),
        "amend_last_health_event": (
            "SHOULD NOT BE CALLED — an annual timeline request does not log or amend events."
        ),
        "get_last_visit_date": "Most recent logged appointment: 2026-04-02.",
        "get_health_events": (
            "- [2026-04-02] appointment: Neurology follow-up (provider=Dr. Nolan)\n"
            "- [2026-04-15] seizure: Seizure episode (duration_sec=45) — witnessed at daycare\n"
            "- [2026-05-12] medication_change: Medication change (added=levetiracetam, "
            "dose=250 mg BID)\n"
            "- [2026-05-20] seizure: Seizure episode (duration_sec=30)\n"
            "- [2026-05-22] seizure: Seizure episode (duration_sec=50) — happened during nap\n"
            "- [2026-06-03] growth_measurement: Growth check (weight_lb=32, height_in=39)\n"
            "- [2026-06-10] seizure: Seizure episode (duration_sec=40)\n"
            "- [2026-06-14] seizure: Seizure episode (duration_sec=35)\n"
            "- [2026-06-19] seizure: Seizure episode (duration_sec=60) — longer than usual\n"
            "- [2026-06-25] seizure: Seizure episode (duration_sec=25)"
        ),
    },
    "amend_seizure_detail": {
        "normalize_medication": _NOT_A_DRUG_CHECK,
        "fetch_fda_label": _NOT_A_DRUG_CHECK,
        "search_web": _NOT_A_DRUG_CHECK,
        "fetch_article": _NOT_A_DRUG_CHECK,
        "get_medication_profile": CURRENT_PROFILE,
        "get_last_visit_date": "Most recent logged appointment: 2026-04-02.",
        "get_health_events": "No health events logged in that range.",
        "log_health_event": (
            "SHOULD NOT BE CALLED — this is added detail on an already-logged event."
        ),
        "amend_last_health_event": "Updated the seizure event for 2026-07-24.",
    },
    "second_seizure_today": {
        "normalize_medication": _NOT_A_DRUG_CHECK,
        "fetch_fda_label": _NOT_A_DRUG_CHECK,
        "search_web": _NOT_A_DRUG_CHECK,
        "fetch_article": _NOT_A_DRUG_CHECK,
        "get_medication_profile": CURRENT_PROFILE,
        "get_last_visit_date": "Most recent logged appointment: 2026-04-02.",
        "get_health_events": "No health events logged in that range.",
        "log_health_event": "Logged seizure for 2026-07-25: Second seizure episode today.",
        "amend_last_health_event": (
            "SHOULD NOT BE CALLED — a second seizure today is a new, separate episode, "
            "not an amendment to the first."
        ),
    },
    "interim_breathing": {
        "normalize_medication": _NOT_A_DRUG_CHECK,
        "fetch_fda_label": _NOT_A_DRUG_CHECK,
        "search_web": _NOT_A_DRUG_CHECK,
        "fetch_article": _NOT_A_DRUG_CHECK,
        "get_medication_profile": CURRENT_PROFILE,
        "get_last_visit_date": "Most recent logged appointment: 2026-04-02.",
        "get_health_events": (
            "- [2026-06-10] seizure: Seizure episode (duration_sec=40)\n"
            "- [2026-06-19] seizure: Seizure episode (duration_sec=60) — longer than usual\n"
            "- [2026-06-25] seizure: Seizure episode (duration_sec=25)\n"
            "- [2026-07-25] breathing_episode: Breathing episode (duration_sec=90) — "
            "labored breathing after lunch"
        ),
        "log_health_event": "Logged breathing_episode for 2026-07-25: Breathing episode.",
        "amend_last_health_event": (
            "SHOULD NOT BE CALLED — this is a new event, not an amendment."
        ),
    },
}
