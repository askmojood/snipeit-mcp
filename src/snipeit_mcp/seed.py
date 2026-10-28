"""Fill an empty local Snipe-IT with Harbor Trading, a made-up Gulf trading company (SAMPLE data).

Everything goes in through Snipe-IT's own API, the way a real customer's data would. Dates are set relative to
today, so whenever it is seeded there are audits due and overdue, a loaner that is late back, warranties running
out and stock below its minimum. Run on an empty Snipe-IT only: `uv run snipeit-seed` (scripts/reset.sh starts
over from nothing).
"""

import secrets
from datetime import date, timedelta

from snipeit_mcp.client import SnipeIT

TODAY = date.today()


def ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


def ahead(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


LOCATIONS = [("Dammam HQ", "Dammam"), ("Riyadh office", "Riyadh"), ("Jeddah warehouse", "Jeddah")]
DEPARTMENTS = ["Finance", "Sales", "Operations", "IT", "Warehouse"]

# first, last, department, job title, location
PEOPLE = [
    ("Sara", "Al-Qahtani", "Finance", "Accountant", "Dammam HQ"),
    ("Omar", "Haddad", "Finance", "Finance manager", "Dammam HQ"),
    ("Layla", "Mansour", "Sales", "Account manager", "Riyadh office"),
    ("Faisal", "Al-Dosari", "Sales", "Sales lead", "Riyadh office"),
    ("Priya", "Nair", "Sales", "Account manager", "Riyadh office"),
    ("Yousef", "Karim", "Operations", "Operations manager", "Dammam HQ"),
    ("Noura", "Al-Shehri", "Operations", "Buyer", "Dammam HQ"),
    ("Ahmed", "Raza", "IT", "IT lead", "Dammam HQ"),
    ("Hana", "Saleh", "IT", "Support engineer", "Dammam HQ"),
    ("Khalid", "Al-Otaibi", "Warehouse", "Warehouse manager", "Jeddah warehouse"),
    ("Bilal", "Hussain", "Warehouse", "Storekeeper", "Jeddah warehouse"),
    ("Maryam", "Al-Harbi", "Warehouse", "Dispatcher", "Jeddah warehouse"),
    ("Tariq", "Aziz", "Warehouse", "Picker", "Jeddah warehouse"),
    ("Reem", "Al-Zahrani", "Operations", "Customer service", "Jeddah warehouse"),
    ("Daniel", "Okafor", "Sales", "Export sales", "Riyadh office"),
]

# category name, type
CATEGORIES = [("Laptops", "asset"), ("Monitors", "asset"), ("Phones", "asset"), ("Scanners", "asset"),
              ("Printers", "asset"), ("Printer supplies", "consumable"), ("Scanner supplies", "consumable"),
              ("Peripherals", "accessory")]

# model name, manufacturer, category, model number
MODELS = [
    ("MacBook Pro 14 (M4)", "Apple", "Laptops", "MX2E3"),
    ("ThinkPad T14 Gen 5", "Lenovo", "Laptops", "21ML"),
    ("Latitude 5450", "Dell", "Laptops", "LAT5450"),
    ("UltraSharp U2724D", "Dell", "Monitors", "U2724D"),
    ("iPhone 16", "Apple", "Phones", "A3287"),
    ("TC22 mobile computer", "Zebra", "Scanners", "TC220"),
    ("LaserJet Pro 4002dn", "HP", "Printers", "2Z605F"),
]


def assets() -> list[dict]:
    """Each asset: tag, model, serial, where it lives, cost (SAR), purchase date, warranty, next audit, holder."""
    out: list[dict] = []

    def add(tag, model, loc, cost, bought_days_ago, warranty_months, audit, holder=None, **extra):
        out.append(dict(tag=tag, model=model, loc=loc, cost=cost, bought=ago(bought_days_ago),
                        warranty=warranty_months, audit=audit, holder=holder, serial=f"HT{secrets.token_hex(4).upper()}", **extra))

    # Laptops: one per office worker, two spares, two loaners (one late back), one at repair.
    laptop_people = [p for p in PEOPLE if p[4] != "Jeddah warehouse" or p[1] in ("Al-Otaibi", "Al-Zahrani")]
    for i, (first, last, *_rest) in enumerate(laptop_people):
        model = "MacBook Pro 14 (M4)" if i % 3 == 0 else "ThinkPad T14 Gen 5" if i % 3 == 1 else "Latitude 5450"
        loc = next(p[4] for p in PEOPLE if p[1] == last)
        # Two warranties run out within 60 days; three audits overdue, two due this month.
        bought = 1065 + i * 3 if i in (2, 5) else 200 + i * 40
        audit = ago(20 + i) if i in (1, 4, 7) else ahead(10 + i) if i in (3, 8) else ahead(120 + i * 9)
        add(f"LAP-{140 + i:04d}", model, loc, 7800 if "MacBook" in model else 5200, bought, 36, audit, f"{first} {last}")
    add("LAP-0160", "ThinkPad T14 Gen 5", "Dammam HQ", 5200, 90, 36, ahead(200))  # the spare for the demo
    add("LAP-0161", "Latitude 5450", "Riyadh office", 4900, 400, 36, ahead(150))
    add("LAP-0162", "ThinkPad T14 Gen 5", "Dammam HQ", 5200, 300, 36, ahead(90), "Daniel Okafor",
        loaner=True, out_days=40, back_days=-12)  # loaner, 12 days late
    add("LAP-0163", "Latitude 5450", "Riyadh office", 4900, 500, 36, ahead(60), "Priya Nair",
        loaner=True, out_days=10, back_days=4)  # loaner, back in 4 days
    add("LAP-0164", "MacBook Pro 14 (M4)", "Dammam HQ", 7800, 700, 36, ago(5), status="Out for repair")

    # Monitors at desks.
    for i, (first, last, _d, _t, loc) in enumerate(PEOPLE[:12]):
        add(f"MON-{210 + i:04d}", "UltraSharp U2724D", loc, 1650, 300 + i * 25, 36,
            ago(3) if i == 6 else ahead(30 + i * 20), f"{first} {last}" if loc != "Jeddah warehouse" else None)

    # Phones for sales and managers.
    phone_people = [p for p in PEOPLE if p[2] == "Sales" or "manager" in p[3] or p[3] == "IT lead"]
    for i, (first, last, _d, _t, loc) in enumerate(phone_people):
        add(f"PHN-{310 + i:04d}", "iPhone 16", loc, 3999, 120 + i * 30, 12, ahead(40 + i * 15), f"{first} {last}")

    # Scanners in the warehouse; one warranty about to end, one audit overdue.
    for i in range(8):
        holder = ["Bilal Hussain", "Maryam Al-Harbi", "Tariq Aziz", None, None, None, None, None][i]
        add(f"SCN-{410 + i:04d}", "TC22 mobile computer", "Jeddah warehouse", 2300, 700 if i == 3 else 250 + i * 20,
            24, ago(40) if i == 5 else ahead(20) if i == 6 else ahead(100 + i * 10), holder)

    # Printers, one per site.
    for i, (loc, _city) in enumerate(LOCATIONS):
        add(f"PRN-{510 + i:04d}", "LaserJet Pro 4002dn", loc, 1450, 600 + i * 50, 12, ahead(70 + i * 30))
    return out


# name, category, kind, quantity, minimum, location
STOCK = [
    ("HP 151A toner", "Printer supplies", "consumable", 2, 4, "Dammam HQ"),
    ("A4 paper, box of 5 reams", "Printer supplies", "consumable", 14, 6, "Jeddah warehouse"),
    ("TC22 spare battery", "Scanner supplies", "consumable", 3, 6, "Jeddah warehouse"),
    ("Thermal label rolls 100×150", "Scanner supplies", "consumable", 40, 20, "Jeddah warehouse"),
    ("USB-C 65 W charger", "Peripherals", "accessory", 3, 5, "Dammam HQ"),
    ("Wireless keyboard and mouse", "Peripherals", "accessory", 9, 4, "Dammam HQ"),
    ("USB-C dock", "Peripherals", "accessory", 6, 3, "Riyadh office"),
]


def seed(api: SnipeIT) -> dict:
    if api.get("hardware", limit=1).get("total", 0):
        raise SystemExit("Snipe-IT already has assets: seed an empty one (scripts/reset.sh)")

    def made(path: str, data: dict) -> int:
        return api.post(path, data)["payload"]["id"]

    loc = {name: made("locations", {"name": name, "city": city, "country": "SA", "currency": "SAR"})
           for name, city in LOCATIONS}
    dept = {name: made("departments", {"name": name}) for name in DEPARTMENTS}
    users = {}
    for first, last, d, title, where in PEOPLE:
        pw = secrets.token_urlsafe(18)  # sample people never sign in
        username = f"{first}.{last}".lower().replace("al-", "al")
        users[f"{first} {last}"] = made("users", {
            "first_name": first, "last_name": last, "username": username, "password": pw, "password_confirmation": pw,
            "email": f"{username}@harbor-trading.example", "jobtitle": title, "department_id": dept[d],
            "location_id": loc[where], "activated": False,
        })
    makers = {m: made("manufacturers", {"name": m}) for m in sorted({x[1] for x in MODELS})}
    cats = {name: made("categories", {"name": name, "category_type": kind}) for name, kind in CATEGORIES}
    models = {name: made("models", {"name": name, "manufacturer_id": makers[mk], "category_id": cats[c], "model_number": num})
              for name, mk, c, num in MODELS}
    status = {s["name"]: s["id"] for s in api.rows("statuslabels")}
    status["Out for repair"] = made("statuslabels", {"name": "Out for repair", "type": "undeployable", "color": "#b45309"})

    n_assets = n_out = 0
    for a in assets():
        aid = made("hardware", {
            "asset_tag": a["tag"], "model_id": models[a["model"]], "serial": a["serial"],
            "status_id": status[a.get("status", "Ready to Deploy")], "rtd_location_id": loc[a["loc"]],
            "location_id": loc[a["loc"]], "purchase_date": a["bought"], "purchase_cost": a["cost"],
            "warranty_months": a["warranty"], "next_audit_date": a["audit"], "notes": "SAMPLE data",
        })
        n_assets += 1
        if a["holder"]:
            body = {"checkout_to_type": "user", "assigned_user": users[a["holder"]], "note": "SAMPLE data"}
            if a.get("loaner"):
                body |= {"checkout_at": ago(a["out_days"]), "expected_checkin": ahead(a["back_days"]),
                         "note": "Loaner while their laptop is at repair (SAMPLE data)"}
            api.post(f"hardware/{aid}/checkout", body)
            n_out += 1
    for name, cat, kind, qty, minimum, where in STOCK:
        made({"consumable": "consumables", "accessory": "accessories"}[kind], {"name": name, "category_id": cats[cat], "qty": qty, "min_amt": minimum, "location_id": loc[where]})
    return {"locations": len(loc), "people": len(users), "assets": n_assets, "checked_out": n_out, "stock_items": len(STOCK)}


def main() -> None:
    print(seed(SnipeIT()))
