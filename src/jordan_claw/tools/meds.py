from __future__ import annotations

import re

import httpx
import structlog
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps

log = structlog.get_logger()

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
HTTP_TIMEOUT_S = 10.0
MAX_CANDIDATES = 4

# Cached so the underlying httpx connection pool is reused across calls
# (same pattern as web_search/embeddings client caches).
_http_client: httpx.AsyncClient | None = None


def get_meds_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)
    return _http_client


async def _get_json(url: str, params: dict | None = None) -> tuple[int, dict | None]:
    """GET a JSON endpoint. Returns (status_code, body). status 0 = network failure.

    Callers must distinguish 404/empty (a real "not found" answer) from 0/5xx
    (the call failed) — the agent reports these differently.
    """
    try:
        resp = await get_meds_http_client().get(url, params=params)
    except httpx.HTTPError as exc:
        log.warning("meds_http_error", url=url, error=str(exc))
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


_BRAND_TTYS = {"BN", "SBD", "SBDC", "BPCK"}
_GENERIC_TTYS = {"IN", "MIN", "PIN", "SCD", "SCDC", "GPCK"}


async def _candidate_summary(rxcui: str) -> str | None:
    """One formatted line for an rxcui: canonical name, brand/generic, ingredients."""
    status, props = await _get_json(f"{RXNAV_BASE}/rxcui/{rxcui}/properties.json")
    if status != 200 or not props or "properties" not in props:
        return None
    name = props["properties"].get("name", "?")
    tty = props["properties"].get("tty", "")
    kind = (
        "brand" if tty in _BRAND_TTYS else "generic" if tty in _GENERIC_TTYS else tty or "unknown"
    )

    status, related = await _get_json(f"{RXNAV_BASE}/rxcui/{rxcui}/related.json", {"tty": "IN"})
    if status != 200 or related is None:
        ing = (
            "(ingredient lookup FAILED — could not verify ingredients, "
            "report the check as incomplete)"
        )
    else:
        ingredients: list[str] = []
        for group in (related.get("relatedGroup") or {}).get("conceptGroup") or []:
            for concept in group.get("conceptProperties") or []:
                if concept.get("name") and concept["name"] not in ingredients:
                    ingredients.append(concept["name"])
        ing = ", ".join(ingredients) if ingredients else "(ingredient lookup returned nothing)"
    return f"- rxcui {rxcui}: {name} ({kind}) — active ingredient(s): {ing}"


async def normalize_medication(ctx: RunContext[AgentDeps], name: str) -> str:
    """Resolve a medication name (including misspellings and brand names) to RxNorm
    identities with rxcui, canonical name, brand/generic, and every active ingredient.
    ALWAYS call this first for any medication mentioned, before any other check.
    If more than one distinct drug comes back, present the candidates and ask Jordan
    which one — never guess between different drugs. A single strong match may proceed.
    NOT for safety information — use fetch_fda_label and web search for that."""
    status, data = await _get_json(
        f"{RXNAV_BASE}/approximateTerm.json", {"term": name, "maxEntries": MAX_CANDIDATES}
    )
    if status != 200 or data is None:
        return (
            f"RxNorm lookup failed for '{name}' (network or API error). "
            "Report that drug identity could not be verified; do not guess."
        )

    candidates = (data.get("approximateGroup") or {}).get("candidate") or []
    seen: list[str] = []
    for cand in candidates:
        rxcui = cand.get("rxcui")
        if rxcui and rxcui not in seen:
            seen.append(rxcui)

    if not seen:
        return f"No RxNorm match for '{name}'. Ask Jordan to check the spelling or the packaging."

    lines: list[str] = []
    for rxcui in seen[:MAX_CANDIDATES]:
        summary = await _candidate_summary(rxcui)
        if summary:
            lines.append(summary)

    if not lines:
        return (
            f"RxNorm matched '{name}' but detail lookups failed (network or API error). "
            "Report that drug identity could not be verified; do not guess."
        )

    header = f"RxNorm candidates for '{name}':"
    if len(lines) > 1:
        header += " MULTIPLE distinct candidates — ask Jordan which one before checking."
    return header + "\n" + "\n".join(lines)


OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
SECTION_CHAR_BUDGET = 1500
LABEL_SECTIONS = (
    "boxed_warning",
    "contraindications",
    "warnings",
    "warnings_and_cautions",
    "drug_interactions",
    "adverse_reactions",
)
QT_PATTERN = re.compile(r"\bQTc?\b|torsade|arrhythmi|proarrhythmic|sudden death", re.IGNORECASE)


def _qt_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if QT_PATTERN.search(s)]


def _clip(text: str, budget: int = SECTION_CHAR_BUDGET) -> str:
    return text if len(text) <= budget else text[:budget] + " [truncated]"


async def fetch_fda_label(ctx: RunContext[AgentDeps], drug_name: str) -> str:
    """Fetch the FDA prescribing label for a drug from openFDA and return the
    safety-relevant sections (boxed warning, contraindications, warnings,
    interactions, adverse reactions) plus every QT/torsades/arrhythmia sentence
    extracted verbatim. Call with the GENERIC name from normalize_medication;
    it falls back to brand-name search automatically.
    NOT for drug identity (use normalize_medication) and NOT a CredibleMeds
    category (use web search for that)."""
    result: dict | None = None
    failed = False
    for field in ("openfda.generic_name", "openfda.brand_name"):
        status, data = await _get_json(
            OPENFDA_LABEL_URL, {"search": f'{field}:"{drug_name}"', "limit": 1}
        )
        if status == 200 and data and data.get("results"):
            result = data["results"][0]
            break
        if status in (0,) or status >= 500:
            failed = True
    if result is None:
        if failed:
            return (
                f"openFDA query failed for '{drug_name}' (network or API error). "
                "The FDA-label check did NOT complete — report it as incomplete."
            )
        return (
            f"No FDA label found for '{drug_name}' (searched generic and brand name). "
            "This is a definitive no-result, not an error."
        )

    parts: list[str] = []
    qt_hits: list[str] = []
    for section in LABEL_SECTIONS:
        values = result.get(section)
        if not values:
            continue
        text = "\n".join(values) if isinstance(values, list) else str(values)
        qt_hits.extend(_qt_sentences(text))
        parts.append(f"## {section}\n{_clip(text)}")

    pharm = result.get("clinical_pharmacology")
    if pharm:
        text = "\n".join(pharm) if isinstance(pharm, list) else str(pharm)
        hits = _qt_sentences(text)
        if hits:  # only include this section when it mentions QT
            qt_hits.extend(hits)
            parts.append(f"## clinical_pharmacology\n{_clip(text)}")

    deduped: list[str] = []
    for hit in qt_hits:
        if hit not in deduped:
            deduped.append(hit)
    if deduped:
        qt_block = "## QT-RELATED SENTENCES (verbatim, never truncated)\n" + "\n".join(
            f"- {h}" for h in deduped
        )
        parts.insert(0, qt_block)
    else:
        parts.insert(0, "## QT-RELATED SENTENCES\nNone found in the label sections returned.")

    if len(parts) == 1:
        parts.append("(No safety sections present in this label.)")
    return f"FDA label for '{drug_name}':\n\n" + "\n\n".join(parts)
