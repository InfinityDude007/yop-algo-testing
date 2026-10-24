import json
from datetime import date
from pathlib import Path

INPUT_PATH = Path(__file__).parent / "data" / "opportunities.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "documents.json"

PROGRAMME_NAMES = {
    "GV": "Global Volunteer",
    "GTa": "Global Talent",
    "GTe": "Global Teacher",
}


def names(items, key="constant_name", option=None):
    """Constant names from a list, optionally only those with a given option."""
    return [
        item[key]
        for item in items or []
        if item.get(key) and (option is None or item.get("option") == option)
    ]


def is_yes(value, yes):
    """logistics_info values are strings like "covered" / "not_covered"."""
    return value == yes if value else None


def to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_embedding_text(op):
    programme = op["programme"]["short_name_display"]
    field = (op.get("sub_product") or {}).get("name")
    sdg_target = (op.get("sdg_info") or {}).get("sdg_target") or {}
    learning_points = (op.get("role_info") or {}).get("learning_points_list") or []

    # skills with option=None are study levels
    sections = [
        ("Title", op.get("title")),
        ("Programme", PROGRAMME_NAMES.get(programme, programme)),
        ("Field", field if field != "Other" else None),
        ("Description", op.get("description")),
        ("Project", op.get("project_description")),
        ("About the organisation", op.get("company_description")),
        ("Cause", sdg_target.get("description")),
        ("Required skills", ", ".join(names(op.get("skills"), option="required"))),
        ("Preferred skills", ", ".join(names(op.get("skills"), option="preferred"))),
        (
            "Required backgrounds",
            ", ".join(names(op.get("backgrounds"), option="required")),
        ),
        (
            "Preferred backgrounds",
            ", ".join(names(op.get("backgrounds"), option="preferred")),
        ),
        ("What you will learn", "; ".join(str(point) for point in learning_points)),
    ]
    return "\n\n".join(
        f"{label}: {value.strip()}"
        for label, value in sections
        if value and value.strip()
    )


def build_metadata(op, today):
    logistics = op.get("logistics_info") or {}
    specifics = op.get("specifics_info") or {}
    sdg_target = (op.get("sdg_info") or {}).get("sdg_target") or {}

    # slots that are live and still taking applications
    slots = [
        slot
        for slot in op.get("available_slots") or []
        if slot.get("status") == "live"
        and (slot.get("applications_close_date") or "") >= today
    ]
    start_dates = sorted(slot["start_date"] for slot in slots if slot.get("start_date"))
    end_dates = sorted(slot["end_date"] for slot in slots if slot.get("end_date"))
    close_dates = sorted(slot["applications_close_date"] for slot in slots)

    return {
        "programme": op["programme"]["short_name_display"],
        "programme_id": int(op["programme"]["id"]),
        "sub_product": (op.get("sub_product") or {}).get("name"),
        "duration_type": (op.get("opportunity_duration_type") or {}).get(
            "duration_type"
        ),
        "country": (op.get("home_mc") or {}).get("name"),
        "host_lc": (op.get("host_lc") or {}).get("name"),
        "location": op.get("location"),
        "lat": to_number(op.get("lat")),
        "lng": to_number(op.get("lng")),
        "organisation": (op.get("organisation") or {}).get("name"),
        "sdg_goal": sdg_target.get("goal_index"),
        "required_languages": names(op.get("languages"), option="required"),
        "preferred_languages": names(op.get("languages"), option="preferred"),
        "study_levels": names(op.get("study_levels"), key="name"),
        # empty list means any nationality can apply
        "nationalities": names(op.get("nationalities")),
        "accommodation_covered": is_yes(
            logistics.get("accommodation_covered"), "covered"
        ),
        "accommodation_provided": is_yes(
            logistics.get("accommodation_provided"), "provided"
        ),
        "food_covered": is_yes(logistics.get("food_covered"), "covered"),
        "food_provided": is_yes(logistics.get("food_provided"), "provided"),
        "transportation_covered": is_yes(
            logistics.get("transportation_covered"), "covered"
        ),
        "computer_provided": is_yes(logistics.get("computer_provided"), "provided"),
        "salary": to_number(specifics.get("salary")),
        "salary_currency": (specifics.get("salary_currency") or {}).get(
            "alphabetic_code"
        ),
        "salary_periodicity": specifics.get("salary_periodicity"),
        "slot_count": len(slots),
        "available_openings": sum(
            slot.get("available_openings") or 0 for slot in slots
        ),
        "earliest_start_date": start_dates[0] if start_dates else None,
        "latest_end_date": end_dates[-1] if end_dates else None,
        "applications_close_date": close_dates[-1] if close_dates else None,
    }


def build_documents():
    opportunities = json.loads(INPUT_PATH.read_text())
    today = date.today().isoformat()
    documents = [
        {
            "id": op["id"],
            "embedding_text": build_embedding_text(op),
            "metadata": build_metadata(op, today),
        }
        for op in opportunities
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(documents, indent=2, ensure_ascii=False))
    tmp_path.replace(OUTPUT_PATH)

    unique_texts = len({doc["embedding_text"] for doc in documents})
    print(
        f"Wrote {len(documents)} documents ({unique_texts} unique texts) to {OUTPUT_PATH}"
    )
