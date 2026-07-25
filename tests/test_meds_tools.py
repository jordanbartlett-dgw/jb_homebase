from __future__ import annotations

import pytest

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.tools import meds


def make_deps() -> AgentDeps:
    return AgentDeps(
        org_id="org-1",
        tavily_api_key="tv",
        fastmail_username="u",
        fastmail_app_password="p",
    )


class FakeCtx:
    def __init__(self):
        self.deps = make_deps()


APPROX_ZOFRAN = {  # misspelled brand "zofrann" resolves via approximateTerm
    "approximateGroup": {
        "candidate": [
            {"rxcui": "196474", "score": "88", "rank": "1"},
            {"rxcui": "196474", "score": "88", "rank": "2"},  # dupe rxcui must collapse
        ]
    }
}
PROPS_ZOFRAN = {"properties": {"rxcui": "196474", "name": "Zofran", "tty": "BN"}}
RELATED_ZOFRAN = {
    "relatedGroup": {
        "conceptGroup": [
            {
                "tty": "IN",
                "conceptProperties": [{"rxcui": "26225", "name": "ondansetron", "tty": "IN"}],
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_normalize_resolves_misspelled_brand_to_generic(monkeypatch):
    async def fake_get_json(url, params=None):
        if "approximateTerm" in url:
            return 200, APPROX_ZOFRAN
        if url.endswith("/rxcui/196474/properties.json"):
            return 200, PROPS_ZOFRAN
        if url.endswith("/rxcui/196474/related.json"):
            return 200, RELATED_ZOFRAN
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(meds, "_get_json", fake_get_json)
    out = await meds.normalize_medication(FakeCtx(), "zofrann")
    assert "Zofran" in out
    assert "ondansetron" in out
    assert "brand" in out.lower()
    assert out.count("rxcui") == 1  # duplicate candidate collapsed


APPROX_COMBO = {"approximateGroup": {"candidate": [{"rxcui": "10510", "score": "90", "rank": "1"}]}}
PROPS_COMBO = {"properties": {"rxcui": "10510", "name": "Bactrim", "tty": "BN"}}
RELATED_COMBO = {
    "relatedGroup": {
        "conceptGroup": [
            {
                "tty": "IN",
                "conceptProperties": [
                    {"rxcui": "10831", "name": "sulfamethoxazole", "tty": "IN"},
                    {"rxcui": "10832", "name": "trimethoprim", "tty": "IN"},
                ],
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_normalize_combination_product_lists_every_ingredient(monkeypatch):
    async def fake_get_json(url, params=None):
        if "approximateTerm" in url:
            return 200, APPROX_COMBO
        if url.endswith("/properties.json"):
            return 200, PROPS_COMBO
        if url.endswith("/related.json"):
            return 200, RELATED_COMBO
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(meds, "_get_json", fake_get_json)
    out = await meds.normalize_medication(FakeCtx(), "bactrim")
    assert "sulfamethoxazole" in out
    assert "trimethoprim" in out


@pytest.mark.asyncio
async def test_ingredient_lookup_failure_is_distinct_from_no_ingredients(monkeypatch):
    async def fake_get_json(url, params=None):
        if "approximateTerm" in url:
            return 200, APPROX_ZOFRAN
        if url.endswith("/rxcui/196474/properties.json"):
            return 200, PROPS_ZOFRAN
        if url.endswith("/rxcui/196474/related.json"):
            return 0, None  # ingredient lookup fails, e.g. timeout
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(meds, "_get_json", fake_get_json)
    out = await meds.normalize_medication(FakeCtx(), "zofrann")
    assert "FAILED" in out
    assert "could not verify ingredients" in out
    assert "returned nothing" not in out


@pytest.mark.asyncio
async def test_normalize_all_detail_lookups_fail(monkeypatch):
    async def fake_get_json(url, params=None):
        if "approximateTerm" in url:
            return 200, APPROX_ZOFRAN
        if url.endswith("/properties.json"):
            return 0, None  # every candidate's detail lookup fails
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(meds, "_get_json", fake_get_json)
    out = await meds.normalize_medication(FakeCtx(), "zofrann")
    assert "detail lookups failed" in out


@pytest.mark.asyncio
async def test_normalize_no_match_is_explicit(monkeypatch):
    async def fake_get_json(url, params=None):
        return 200, {"approximateGroup": {"candidate": []}}

    monkeypatch.setattr(meds, "_get_json", fake_get_json)
    out = await meds.normalize_medication(FakeCtx(), "xyzzynotadrug")
    assert "No RxNorm match" in out


@pytest.mark.asyncio
async def test_normalize_network_failure_is_distinct_from_no_match(monkeypatch):
    async def fake_get_json(url, params=None):
        return 0, None

    monkeypatch.setattr(meds, "_get_json", fake_get_json)
    out = await meds.normalize_medication(FakeCtx(), "ibuprofen")
    assert "failed" in out.lower()
    assert "No RxNorm match" not in out
