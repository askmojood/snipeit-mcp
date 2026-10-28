"""Unit tests over a fake Snipe-IT API (httpx.MockTransport): no Docker needed."""

import json

import httpx
import pytest

from snipeit_mcp import tools
from snipeit_mcp.client import SnipeIT, SnipeITError

LAPTOP = {"id": 7, "asset_tag": "LAP-0160", "serial": "HT1", "model": {"name": "ThinkPad T14 Gen 5"},
          "category": {"name": "Laptops"}, "status_label": {"name": "Ready to Deploy", "status_type": "deployable"},
          "assigned_to": None, "location": {"name": "Dammam HQ"}, "next_audit_date": {"date": "2027-01-01"},
          "warranty_expires": {"date": "2029-01-01"}, "expected_checkin": None}
SARA = {"id": 3, "name": "Sara Al-Qahtani", "jobtitle": "Accountant", "department": {"name": "Finance"},
        "location": {"name": "Dammam HQ"}}


class Fake:
    """Just enough of Snipe-IT: one laptop, one or two users, checkout and checkin."""

    def __init__(self, users=(SARA,)):
        self.asset = dict(LAPTOP)
        self.users = list(users)
        self.posts: list[tuple[str, dict]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path.removeprefix("/api/v1/")
        if req.method == "POST":
            body = json.loads(req.content)
            self.posts.append((path, body))
            if path.endswith("/checkout"):
                self.asset["assigned_to"] = {"name": next(u["name"] for u in self.users if u["id"] == body["assigned_user"])}
            elif path.endswith("/checkin"):
                self.asset["assigned_to"] = None
            return httpx.Response(200, json={"status": "success"})
        if path == "hardware/bytag/LAP-0160" or path == "hardware/7":
            return httpx.Response(200, json=self.asset)
        if path.startswith("hardware/bytag/"):
            return httpx.Response(200, json={"status": "error", "messages": "Asset does not exist."})
        if path == "users":
            q = req.url.params["search"].lower()
            rows = [u for u in self.users if q in u["name"].lower()]
            return httpx.Response(200, json={"total": len(rows), "rows": rows})
        if path in ("consumables", "accessories"):
            rows = [{"name": "HP 151A toner", "remaining": 2, "min_amt": 4}, {"name": "Paper", "remaining": 9, "min_amt": 6}] if path == "consumables" else []
            return httpx.Response(200, json={"total": len(rows), "rows": rows})
        return httpx.Response(404)


@pytest.fixture
def fake():
    return Fake()


def api(fake: Fake) -> SnipeIT:
    return SnipeIT("http://snipe.test", "token", transport=httpx.MockTransport(fake))


def test_needs_a_token(monkeypatch):
    monkeypatch.delenv("SNIPEIT_TOKEN", raising=False)
    with pytest.raises(SnipeITError):
        SnipeIT("http://snipe.test", "")


def test_error_status_becomes_an_exception(fake):
    with pytest.raises(SnipeITError, match="does not exist"):
        api(fake).get("hardware/bytag/NOPE")


def test_dates_and_datetimes_keep_the_day():
    assert tools._date({"date": "2026-11-01"}) == "2026-11-01"
    assert tools._date({"datetime": "2026-11-01 00:00:00", "formatted": "x"}) == "2026-11-01"
    assert tools._date(None) is None


def test_checkout_changes_nothing_without_a_code(fake):
    c = tools.check_out_asset(api(fake), "LAP-0160", "Sara")
    assert not c.done and c.confirmation and "Sara Al-Qahtani" in c.summary
    assert fake.posts == []


def test_checkout_with_the_code_acts_once(fake):
    a = api(fake)
    code = tools.check_out_asset(a, "LAP-0160", "Sara").confirmation
    done = tools.check_out_asset(a, "LAP-0160", "Sara", confirmation=code)
    assert done.done and done.asset.held_by == "Sara Al-Qahtani"
    assert fake.posts == [("hardware/7/checkout", {"checkout_to_type": "user", "assigned_user": 3, "note": tools.NOTE})]
    assert not tools.check_out_asset(a, "LAP-0160", "Sara", confirmation=code).done  # now held, and the code is used


def test_a_code_only_fits_its_own_request(fake):
    fake.users.append({"id": 4, "name": "Omar Haddad"})
    a = api(fake)
    code = tools.check_out_asset(a, "LAP-0160", "Sara").confirmation
    other = tools.check_out_asset(a, "LAP-0160", "Omar", confirmation=code)
    assert not other.done and "doesn't match" in other.problem
    noted = tools.check_out_asset(a, "LAP-0160", "Sara", note="new hire", confirmation=code)
    assert not noted.done
    assert fake.posts == []


def test_an_expired_code_is_refused(fake, monkeypatch):
    a = api(fake)
    code = tools.check_out_asset(a, "LAP-0160", "Sara").confirmation
    monkeypatch.setattr(tools, "CONFIRM_TTL_S", -1)
    assert not tools.check_out_asset(a, "LAP-0160", "Sara", confirmation=code).done
    assert fake.posts == []


def test_ambiguous_person_asks_which(fake):
    fake.users.append({"id": 5, "name": "Sara Khan"})
    c = tools.check_out_asset(api(fake), "LAP-0160", "Sara")
    assert not c.confirmation and "Sara Al-Qahtani" in c.problem and "Sara Khan" in c.problem


def test_cannot_check_out_what_is_out_of_service(fake):
    fake.asset["status_label"] = {"name": "Out for repair", "status_type": "undeployable"}
    c = tools.check_out_asset(api(fake), "LAP-0160", "Sara")
    assert not c.confirmation and "Out for repair" in c.problem


def test_unknown_tag(fake):
    assert "No asset" in tools.check_out_asset(api(fake), "LAP-9999", "Sara").problem


def test_checkin_previews_then_acts(fake):
    fake.asset["assigned_to"] = {"name": "Sara Al-Qahtani"}
    a = api(fake)
    p = tools.check_in_asset(a, "LAP-0160")
    assert not p.done and fake.posts == []
    d = tools.check_in_asset(a, "LAP-0160", confirmation=p.confirmation)
    assert d.done and d.asset.held_by is None
    assert fake.posts == [("hardware/7/checkin", {"note": tools.NOTE})]


def test_low_stock_lists_only_below_minimum(fake):
    assert [(s.name, s.remaining, s.minimum) for s in tools.low_stock(api(fake))] == [("HP 151A toner", 2, 4)]


def test_an_asset_that_is_out_reads_deployed():
    row = dict(LAPTOP, status_label={"name": "Ready to Deploy", "status_type": "deployable", "status_meta": "deployed"},
               assigned_to={"name": "Sara Al-Qahtani"})
    a = tools.asset_of(row, "http://snipe.test")
    assert (a.status, a.held_by) == ("Deployed", "Sara Al-Qahtani")
    assert tools.asset_of(dict(LAPTOP), "http://snipe.test", held_by="Omar Haddad").held_by == "Omar Haddad"
