"""The six tools, as plain functions over a Snipe-IT client (the MCP wiring is in server.py).

Four only read. The two that change something (check out, check in) never act on the first call: they return a
preview and a one-time confirmation code, and act only when called again with that code and the same request.
Every change goes through Snipe-IT's own checkout/checkin calls with a note, so it lands in Snipe-IT's history
like any person's change.
"""

import secrets
import time
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from snipeit_mcp.client import SnipeIT, SnipeITError

NOTE = "via Claude (Mojood Connect demo)"
CONFIRM_TTL_S = 10 * 60


class Asset(BaseModel):
    tag: str
    model: str | None = None
    category: str | None = None
    serial: str | None = None
    status: str | None = None
    held_by: str | None = Field(None, description="who has it checked out; empty when it's on the shelf")
    location: str | None = None
    next_audit: str | None = None
    warranty_ends: str | None = None
    due_back: str | None = Field(None, description="expected check-in date, for loans")
    link: str | None = Field(None, description="the asset's page in Snipe-IT")


def _name(v: dict | None) -> str | None:
    return v.get("name") if isinstance(v, dict) else None


def _date(v: dict | None) -> str | None:
    """Snipe-IT sends {"date": …} for dates and {"datetime": …} for date-times (check-in dates); keep the day."""
    if not isinstance(v, dict):
        return None
    d = v.get("date") or v.get("datetime")
    return d[:10] if d else None


def asset_of(row: dict, base_url: str, held_by: str | None = None) -> Asset:
    status = row.get("status_label") or {}
    # Snipe-IT keeps the label ("Ready to Deploy") while an asset is out; its own pages then say "Deployed".
    shown = "Deployed" if status.get("status_meta") == "deployed" else status.get("name")
    return Asset(
        tag=row["asset_tag"], model=_name(row.get("model")), category=_name(row.get("category")),
        serial=row.get("serial") or None, status=shown, held_by=_name(row.get("assigned_to")) or held_by,
        location=_name(row.get("location")) or _name(row.get("rtd_location")),
        next_audit=_date(row.get("next_audit_date")), warranty_ends=_date(row.get("warranty_expires")),
        due_back=_date(row.get("expected_checkin")), link=f"{base_url}/hardware/{row['id']}",
    )


def _base(api: SnipeIT) -> str:
    return str(api.http.base_url).removesuffix("/api/v1/")


# ---------- read ----------

class Found(BaseModel):
    assets: list[Asset]
    total: int = Field(description="how many match in all; only the first 10 are listed")


def find_asset(api: SnipeIT, query: str) -> Found:
    q = query.strip()
    try:
        return Found(assets=[asset_of(api.get(f"hardware/bytag/{q}"), _base(api))], total=1)
    except SnipeITError:
        pass
    page = api.get("hardware", search=q, limit=10)
    return Found(assets=[asset_of(r, _base(api)) for r in page.get("rows", [])], total=page.get("total", 0))


class Person(BaseModel):
    name: str
    job_title: str | None = None
    department: str | None = None
    location: str | None = None


class Holdings(BaseModel):
    person: Person | None = Field(None, description="empty when the name matched no one, or more than one person")
    candidates: list[Person] = Field(default_factory=list, description="when more than one person matched: ask which")
    assets: list[Asset] = Field(default_factory=list)
    accessories: list[str] = Field(default_factory=list)


def _person(row: dict) -> Person:
    return Person(name=row["name"], job_title=row.get("jobtitle"), department=_name(row.get("department")),
                  location=_name(row.get("location")))


def _one_user(api: SnipeIT, name: str) -> tuple[dict | None, list[dict]]:
    rows = api.get("users", search=name.strip(), limit=10).get("rows", [])
    exact = [r for r in rows if r["name"].lower() == name.strip().lower()]
    if len(exact) == 1 or len(rows) == 1:
        return (exact or rows)[0], []
    return None, rows


def whats_assigned_to(api: SnipeIT, person: str) -> Holdings:
    user, many = _one_user(api, person)
    if not user:
        return Holdings(candidates=[_person(r) for r in many])
    assets = api.get(f"users/{user['id']}/assets").get("rows", [])
    accessories = api.get(f"users/{user['id']}/accessories").get("rows", [])
    return Holdings(person=_person(user), assets=[asset_of(a, _base(api), user["name"]) for a in assets],
                    accessories=[a["name"] for a in accessories])


class Attention(BaseModel):
    audits_overdue: list[Asset]
    audits_due: list[Asset] = Field(description="due within Snipe-IT's audit warning window")
    returns_overdue: list[Asset] = Field(description="loans past their expected check-in date")
    returns_due: list[Asset] = Field(description="loans due back within `days`")
    warranties_ending: list[Asset] = Field(description="warranty ends within `days`")
    out_of_service: list[Asset] = Field(description="in a status that can't be deployed, e.g. out for repair")
    days: int


def needs_attention(api: SnipeIT, days: int = 30) -> Attention:
    base, today = _base(api), date.today()
    soon = (today + timedelta(days=days)).isoformat()
    every = api.rows("hardware")

    def listed(path: str) -> list[Asset]:
        return [asset_of(r, base) for r in api.rows(path)]

    def where(test) -> list[Asset]:
        return [asset_of(r, base) for r in every if test(r)]

    return Attention(
        audits_overdue=listed("hardware/audits/overdue"),
        audits_due=listed("hardware/audits/due"),
        returns_overdue=listed("hardware/checkins/overdue"),
        returns_due=where(lambda r: (d := _date(r.get("expected_checkin"))) and today.isoformat() <= d <= soon),
        warranties_ending=where(lambda r: (d := _date(r.get("warranty_expires"))) and today.isoformat() <= d <= soon),
        out_of_service=where(lambda r: (r.get("status_label") or {}).get("status_type") == "undeployable"),
        days=days,
    )


class StockLine(BaseModel):
    name: str
    kind: Literal["consumable", "accessory"]
    remaining: int
    minimum: int
    location: str | None = None


def low_stock(api: SnipeIT) -> list[StockLine]:
    out = []
    for kind, path in (("consumable", "consumables"), ("accessory", "accessories")):
        for r in api.rows(path):
            left, minimum = int(r.get("remaining") or 0), int(r.get("min_amt") or 0)
            if minimum and left < minimum:
                out.append(StockLine(name=r["name"], kind=kind, remaining=left, minimum=minimum,
                                     location=_name(r.get("location"))))
    return out


# ---------- change (preview, then confirm) ----------

class Change(BaseModel):
    done: bool = Field(description="false: nothing has changed yet; true: Snipe-IT has made the change")
    summary: str
    confirmation: str | None = Field(None, description="when done is false: the code to pass back, only after the user says yes")
    expires_in_minutes: int | None = None
    asset: Asset | None = None
    problem: str | None = Field(None, description="why it can't be done; nothing was changed")


_pending: dict[str, tuple[float, tuple]] = {}


def _ask(request: tuple, summary: str, asset: Asset) -> Change:
    now = time.monotonic()
    for k in [k for k, (t, _) in _pending.items() if now - t > CONFIRM_TTL_S]:
        del _pending[k]
    code = secrets.token_hex(3)
    _pending[code] = (now, request)
    return Change(done=False, summary=summary + " Nothing has changed yet: ask the user to confirm.",
                  confirmation=code, expires_in_minutes=CONFIRM_TTL_S // 60, asset=asset)


def _confirmed(code: str, request: tuple) -> bool:
    held = _pending.get(code.strip())
    if not held or time.monotonic() - held[0] > CONFIRM_TTL_S or held[1] != request:
        return False
    del _pending[code.strip()]
    return True


def _asset_row(api: SnipeIT, tag: str) -> dict | None:
    try:
        return api.get(f"hardware/bytag/{tag.strip()}")
    except SnipeITError:
        return None


def check_out_asset(api: SnipeIT, asset_tag: str, person: str, note: str | None = None,
                    confirmation: str | None = None) -> Change:
    row = _asset_row(api, asset_tag)
    if not row:
        return Change(done=False, summary="", problem=f"No asset has the tag {asset_tag}.")
    a = asset_of(row, _base(api))
    if a.held_by:
        return Change(done=False, summary="", asset=a, problem=f"{a.tag} is already checked out to {a.held_by}; check it in first.")
    if (row.get("status_label") or {}).get("status_type") != "deployable":
        return Change(done=False, summary="", asset=a, problem=f"{a.tag} is {a.status}, so it can't be checked out.")
    user, many = _one_user(api, person)
    if not user:
        names = ", ".join(r["name"] for r in many) or "no one"
        return Change(done=False, summary="", asset=a, problem=f'"{person}" matches {names}. Ask which person.')
    request = ("out", row["id"], user["id"], note or "")
    who = _person(user)
    summary = f"Check out {a.tag} ({a.model}) to {who.name}" + (f", {who.department}, {who.location}." if who.department else ".")
    if not confirmation:
        return _ask(request, summary, a)
    if not _confirmed(confirmation, request):
        return Change(done=False, summary=summary, asset=a, problem="That confirmation code doesn't match this request or has expired. Ask again.")
    api.post(f"hardware/{row['id']}/checkout", {"checkout_to_type": "user", "assigned_user": user["id"],
                                                "note": f"{note} ({NOTE})" if note else NOTE})
    return Change(done=True, summary=f"Done: {a.tag} is checked out to {who.name}. Snipe-IT's history shows it.",
                  asset=asset_of(api.get(f"hardware/{row['id']}"), _base(api)))


def check_in_asset(api: SnipeIT, asset_tag: str, note: str | None = None, confirmation: str | None = None) -> Change:
    row = _asset_row(api, asset_tag)
    if not row:
        return Change(done=False, summary="", problem=f"No asset has the tag {asset_tag}.")
    a = asset_of(row, _base(api))
    if not a.held_by:
        return Change(done=False, summary="", asset=a, problem=f"{a.tag} isn't checked out to anyone.")
    request = ("in", row["id"], note or "")
    summary = f"Check in {a.tag} ({a.model}) from {a.held_by}."
    if not confirmation:
        return _ask(request, summary, a)
    if not _confirmed(confirmation, request):
        return Change(done=False, summary=summary, asset=a, problem="That confirmation code doesn't match this request or has expired. Ask again.")
    api.post(f"hardware/{row['id']}/checkin", {"note": f"{note} ({NOTE})" if note else NOTE})
    return Change(done=True, summary=f"Done: {a.tag} is checked in from {a.held_by}. Snipe-IT's history shows it.",
                  asset=asset_of(api.get(f"hardware/{row['id']}"), _base(api)))
