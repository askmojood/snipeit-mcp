"""Against the local Snipe-IT with the SAMPLE data (scripts/reset.sh). Skipped when it isn't running.

Run: uv run --env-file .env pytest tests/test_live.py
"""

import os

import httpx
import pytest

from snipeit_mcp import tools
from snipeit_mcp.client import SnipeIT


def _up() -> bool:
    try:
        return bool(os.environ.get("SNIPEIT_TOKEN")) and httpx.get(
            os.environ.get("SNIPEIT_URL", "http://127.0.0.1:8088") + "/login", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="local Snipe-IT not running (scripts/up.sh)")


@pytest.fixture(scope="module")
def api():
    return SnipeIT()


def test_find_by_tag_and_by_model(api):
    assert tools.find_asset(api, "LAP-0160").assets[0].model == "ThinkPad T14 Gen 5"
    assert tools.find_asset(api, "ThinkPad").total >= 3


def test_what_sara_holds(api):
    h = tools.whats_assigned_to(api, "Sara Al-Qahtani")
    assert h.person.department == "Finance" and h.assets


def test_the_seeded_problems_show(api):
    n = tools.needs_attention(api)
    assert n.audits_overdue and n.audits_due and n.warranties_ending
    assert [a.tag for a in n.returns_overdue] == ["LAP-0162"]
    assert [a.tag for a in n.out_of_service] == ["LAP-0164"]
    assert {s.name for s in tools.low_stock(api)} == {"HP 151A toner", "TC22 spare battery", "USB-C 65 W charger"}


def test_check_out_and_back_in_is_in_the_history(api):
    p = tools.check_out_asset(api, "LAP-0161", "Omar Haddad")
    d = tools.check_out_asset(api, "LAP-0161", "Omar Haddad", confirmation=p.confirmation)
    assert d.done and d.asset.held_by == "Omar Haddad"
    back = tools.check_in_asset(api, "LAP-0161", confirmation=tools.check_in_asset(api, "LAP-0161").confirmation)
    assert back.done and back.asset.held_by is None
    rid = api.get("hardware/bytag/LAP-0161")["id"]
    notes = [r.get("note") for r in api.get(f"hardware/{rid}/history").get("rows", [])]
    assert notes.count(tools.NOTE) >= 2
