import io
import json
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from .vector_store import date_to_int

DATA_DIR = Path(__file__).parent / "data"

# lowest to highest, an opportunity listing a level accepts that level and above
STUDY_LEVELS = ["High School", "Associate Degree", "Other tertiary education", "Bachelor", "Masters"]

SDG_GOALS = {
    1: "No Poverty",
    2: "Zero Hunger",
    3: "Good Health and Well-being",
    4: "Quality Education",
    5: "Gender Equality",
    6: "Clean Water and Sanitation",
    7: "Affordable and Clean Energy",
    8: "Decent Work and Economic Growth",
    9: "Industry, Innovation and Infrastructure",
    10: "Reduced Inequalities",
    11: "Sustainable Cities and Communities",
    12: "Responsible Consumption and Production",
    13: "Climate Action",
    14: "Life Below Water",
    15: "Life on Land",
    16: "Peace, Justice and Strong Institutions",
    17: "Partnerships for the Goals",
}

# keep the CV excerpt well inside llama-text-embed-v2's 2048 token input
MAX_CV_CHARS = 5000


def load_options():
    """Values for the UI pickers, taken from the fetched data."""
    documents = json.loads((DATA_DIR / "documents.json").read_text())
    opportunities = json.loads((DATA_DIR / "opportunities.json").read_text())
    metadata = [doc["metadata"] for doc in documents]
    return {
        "countries": sorted({m["country"] for m in metadata if m["country"]}),
        "languages": sorted(
            {lang for m in metadata for lang in m["required_languages"] + m["preferred_languages"]}
        ),
        "skills": sorted(
            {s["constant_name"] for op in opportunities for s in op["skills"] if s.get("option")}
        ),
        "backgrounds": sorted(
            {b["constant_name"] for op in opportunities for b in op["backgrounds"]}
        ),
        "sub_products": sorted({m["sub_product"] for m in metadata if m["sub_product"]}),
    }


def extract_cv_text(file_bytes):
    reader = PdfReader(io.BytesIO(file_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return " ".join(text.split())


def build_profile_text(about="", skills=(), backgrounds=(), causes=(), cv_text=""):
    """Mirror the opportunity embedding_text labels so both sides embed alike."""
    sections = [
        ("About me", about),
        ("Skills", ", ".join(skills)),
        ("Backgrounds", ", ".join(backgrounds)),
        ("Causes I care about", ", ".join(SDG_GOALS[goal] for goal in causes)),
        ("CV", cv_text[:MAX_CV_CHARS]),
    ]
    return "\n\n".join(f"{label}: {value.strip()}" for label, value in sections if value and value.strip())


def build_filter(
    programmes=(),
    countries=(),
    sub_products=(),
    duration_types=(),
    languages=(),
    all_languages=(),
    study_level=None,
    nationality=None,
    start_after=None,
    accommodation_covered=False,
    food_covered=False,
):
    """S3 Vectors metadata filter from the UI filter values. Empty values mean no filter."""
    conditions = []
    if programmes:
        conditions.append({"programme": {"$in": list(programmes)}})
    if countries:
        conditions.append({"country": {"$in": list(countries)}})
    if sub_products:
        conditions.append({"sub_product": {"$in": list(sub_products)}})
    if duration_types:
        conditions.append({"duration_type": {"$in": list(duration_types)}})
    if languages:
        # drop opportunities that require a language the person doesn't speak
        unspoken = [lang for lang in all_languages if lang not in languages]
        if unspoken:
            conditions.append({"required_languages": {"$nin": unspoken}})
    if study_level:
        accepted = STUDY_LEVELS[: STUDY_LEVELS.index(study_level) + 1]
        conditions.append({"study_levels": {"$in": accepted}})
    if nationality:
        conditions.append(
            {"$or": [{"open_to_all_nationalities": True}, {"nationalities": {"$in": [nationality]}}]}
        )
    if start_after:
        conditions.append({"earliest_start_date": {"$gte": date_to_int(start_after.isoformat())}})
    if accommodation_covered:
        conditions.append({"accommodation_covered": True})
    if food_covered:
        conditions.append({"food_covered": True})

    # only slots still taking applications
    conditions.append({"applications_close_date": {"$gte": date_to_int(date.today().isoformat())}})
    return {"$and": conditions}
