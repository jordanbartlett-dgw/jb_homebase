"""Canned tool outputs for med-check evals. Shapes mirror the real tools in
jordan_claw.tools.meds — keep in sync if tool output formats change."""

from __future__ import annotations

EMPTY_PROFILE = (
    "Profile incomplete. Empty fields: allergies, notes.\n\n"
    '{"medications": [{"name": "levetiracetam", "rxcui": "40254", "dose": "250 mg BID", '
    '"prescriber": "Dr. Nolan"}], "allergies": null, "notes": null}'
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
    },
}
