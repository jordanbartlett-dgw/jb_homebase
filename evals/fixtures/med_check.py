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
# Care-doc keys (Task 7) — none of the drug-check or timeline fixtures below
# touch care documents, so every existing bundle gets this same placeholder
# for both keys.
_NOT_A_CARE_DOC = "SHOULD NOT BE CALLED — this request does not touch care documents."

# The seeded QT critical flag, verbatim — required_in_note anchors on this
# exact string in the care-doc dataset cases; keep it byte-identical wherever
# it appears.
QT_CRITICAL_FLAG = (
    "Congenital Long QT — avoid QT-prolonging medications (CredibleMeds list); "
    "confirm any new drug with cardiology."
)

# Full care profile: all 8 sections filled with realistic Rett-specific
# content, contacts including cardiology, and the QT flag verbatim in
# critical_flags. Used by emergency_complete and handoff_actionable.
CARE_PROFILE_COMPLETE = (
    "Profile is complete.\n\n"
    '{"diagnoses": ["Rett syndrome (MECP2 mutation)", "Congenital Long QT syndrome"], '
    '"critical_flags": ['
    f'"{QT_CRITICAL_FLAG}", '
    '"Seizure lasting over 5 minutes, or a second seizure within 30 minutes of the '
    'first, is a 911 call"], '
    '"seizure_plan": "Diastat (rectal diazepam) for seizures lasting over 5 minutes, '
    "dose per the plan on file with Dr. Nolan, kept in the labeled case in her diaper "
    "bag. Note the start time. Do not restrain her; move objects away and turn her "
    "onto her side. Call 911 if it passes 5 minutes or a second seizure starts within "
    '30 minutes of the first.", '
    '"baselines": "Low muscle tone and unsteady gait are normal for her, not a new '
    "problem. Hand-wringing and teeth-grinding are typical Rett movements, not pain "
    "signs. Breath-holding spells followed by rapid breathing are a known Rett "
    "pattern and are baseline for her unless she turns blue or does not resume "
    'normal breathing within a minute.", '
    '"communication": "Non-verbal. Uses eye gaze to answer yes or no and to choose '
    "between two held-up objects. Understands far more than she can express - talk "
    "to her, not about her. A big smile means yes or happy; arching her back with "
    'loud vocalizing usually means discomfort or wanting something changed.", '
    '"routines": "Wakes around 7am, needs help transferring from bed to wheelchair. '
    "Pureed food and thickened liquids only - never plain water, aspiration risk. "
    "Afternoon rest period 1-2pm. AFOs (ankle-foot orthotics) stay on during the "
    'day, off at bedtime.", '
    '"escalation": "Call Jordan first for anything non-critical. Call Dr. Nolan '
    "(neurology) for seizure pattern changes that are not an emergency. Call 911 "
    "for: seizure over 5 minutes, blue lips or skin, not breathing normally, "
    'unresponsive.", '
    '"contacts": ['
    '{"role": "father", "name": "Jordan", "phone": "555-0100"}, '
    '{"role": "neurology", "name": "Dr. Nolan", "phone": "555-0101"}, '
    '{"role": "cardiology", "name": "Dr. Reyes", "phone": "555-0102"}]}'
)

# Same profile with seizure_plan empty — used by emergency_missing_seizure_plan
# to exercise the "not provided" rule.
CARE_PROFILE_MISSING_SEIZURE_PLAN = (
    "Profile incomplete. Empty sections: seizure_plan.\n\n"
    '{"diagnoses": ["Rett syndrome (MECP2 mutation)", "Congenital Long QT syndrome"], '
    '"critical_flags": ['
    f'"{QT_CRITICAL_FLAG}", '
    '"Seizure lasting over 5 minutes, or a second seizure within 30 minutes of the '
    'first, is a 911 call"], '
    '"seizure_plan": null, '
    '"baselines": "Low muscle tone and unsteady gait are normal for her, not a new '
    "problem. Hand-wringing and teeth-grinding are typical Rett movements, not pain "
    "signs. Breath-holding spells followed by rapid breathing are a known Rett "
    "pattern and are baseline for her unless she turns blue or does not resume "
    'normal breathing within a minute.", '
    '"communication": "Non-verbal. Uses eye gaze to answer yes or no and to choose '
    "between two held-up objects. Understands far more than she can express - talk "
    "to her, not about her. A big smile means yes or happy; arching her back with "
    'loud vocalizing usually means discomfort or wanting something changed.", '
    '"routines": "Wakes around 7am, needs help transferring from bed to wheelchair. '
    "Pureed food and thickened liquids only - never plain water, aspiration risk. "
    "Afternoon rest period 1-2pm. AFOs (ankle-foot orthotics) stay on during the "
    'day, off at bedtime.", '
    '"escalation": "Call Jordan first for anything non-critical. Call Dr. Nolan '
    "(neurology) for seizure pattern changes that are not an emergency. Call 911 "
    "for: seizure over 5 minutes, blue lips or skin, not breathing normally, "
    'unresponsive.", '
    '"contacts": ['
    '{"role": "father", "name": "Jordan", "phone": "555-0100"}, '
    '{"role": "neurology", "name": "Dr. Nolan", "phone": "555-0101"}, '
    '{"role": "cardiology", "name": "Dr. Reyes", "phone": "555-0102"}]}'
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
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
        "get_care_profile": _NOT_A_CARE_DOC,
        "check_care_docs_current": _NOT_A_CARE_DOC,
    },
    # --- Care-document fixtures (Task 7) ---
    # emergency_complete and handoff_actionable: profile is complete, no
    # profile edit in this turn, so check_care_docs_current is never reached
    # (the prompt only calls it after a save_medication_profile/save_care_profile
    # call — see MED_CHECK_PROMPT's "Staleness" paragraph).
    "care_complete": {
        "normalize_medication": _NOT_A_DRUG_CHECK,
        "fetch_fda_label": _NOT_A_DRUG_CHECK,
        "search_web": _NOT_A_DRUG_CHECK,
        "fetch_article": _NOT_A_DRUG_CHECK,
        "log_health_event": _NOT_A_HEALTH_LOG,
        "amend_last_health_event": _NOT_A_HEALTH_LOG,
        "get_health_events": _NOT_A_HEALTH_LOG,
        "get_last_visit_date": _NOT_A_HEALTH_LOG,
        "get_medication_profile": CURRENT_PROFILE,
        "get_care_profile": CARE_PROFILE_COMPLETE,
        "check_care_docs_current": (
            "SHOULD NOT BE CALLED — check_care_docs_current only follows a "
            "save_medication_profile or save_care_profile call; this is a plain "
            "document-generation request with no profile edit."
        ),
    },
    # emergency_missing_seizure_plan: same fixture, seizure_plan empty — exercises
    # the "mark as not provided, never invent" rule.
    "care_missing_seizure_plan": {
        "normalize_medication": _NOT_A_DRUG_CHECK,
        "fetch_fda_label": _NOT_A_DRUG_CHECK,
        "search_web": _NOT_A_DRUG_CHECK,
        "fetch_article": _NOT_A_DRUG_CHECK,
        "log_health_event": _NOT_A_HEALTH_LOG,
        "amend_last_health_event": _NOT_A_HEALTH_LOG,
        "get_health_events": _NOT_A_HEALTH_LOG,
        "get_last_visit_date": _NOT_A_HEALTH_LOG,
        "get_medication_profile": CURRENT_PROFILE,
        "get_care_profile": CARE_PROFILE_MISSING_SEIZURE_PLAN,
        "check_care_docs_current": (
            "SHOULD NOT BE CALLED — check_care_docs_current only follows a "
            "save_medication_profile or save_care_profile call; this is a plain "
            "document-generation request with no profile edit."
        ),
    },
    # stale_offer_once: Jordan reports a seizure-plan change (drives a
    # save_care_profile call), and the emergency doc has already gone stale by
    # the time check_care_docs_current is checked afterward.
    "care_stale_after_save": {
        "normalize_medication": _NOT_A_DRUG_CHECK,
        "fetch_fda_label": _NOT_A_DRUG_CHECK,
        "search_web": _NOT_A_DRUG_CHECK,
        "fetch_article": _NOT_A_DRUG_CHECK,
        "log_health_event": _NOT_A_HEALTH_LOG,
        "amend_last_health_event": _NOT_A_HEALTH_LOG,
        "get_health_events": _NOT_A_HEALTH_LOG,
        "get_last_visit_date": _NOT_A_HEALTH_LOG,
        "get_medication_profile": CURRENT_PROFILE,
        "get_care_profile": CARE_PROFILE_COMPLETE,
        "check_care_docs_current": (
            "emergency: stale (changed: seizure_plan)\nhandoff: current (generated 2026-06-01)"
        ),
    },
}
