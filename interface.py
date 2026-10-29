from datetime import date
from pathlib import Path

import streamlit as st

from utils import matching, search_opportunities
from utils.matching import (
    DATA_DIR,
    SDG_GOALS,
    STUDY_LEVELS,
    build_filter,
    build_profile_text,
    extract_cv_text,
    load_options,
)

PROGRAMMES = {"GV": "Global Volunteer", "GTa": "Global Talent", "GTe": "Global Teacher"}
OPPORTUNITY_URL = {
    "GV": "https://aiesec.org/opportunity/global-volunteer/{}",
    "GTa": "https://aiesec.org/opportunity/global-talent/{}",
    "GTe": "https://aiesec.org/opportunity/global-teacher/{}",
}

st.set_page_config(page_title="YOP matcher", layout="wide")


@st.cache_data
def options(version):
    return load_options()


def data_version():
    # changes when the data files or matching.py change, so the cached options refresh
    paths = [DATA_DIR / "documents.json", DATA_DIR / "opportunities.json", Path(matching.__file__)]
    return tuple(path.stat().st_mtime for path in paths)


@st.cache_data(show_spinner=False)
def cached_search(profile_text, filter, top_k):
    return search_opportunities(profile_text, filter=filter, top_k=top_k)


@st.cache_data(show_spinner=False)
def cached_cv_text(file_bytes):
    return extract_cv_text(file_bytes)


opts = options(data_version())

st.title("YOP matcher")

# filter bar: what the opportunity offers, then what the person brings
with st.container(border=True):
    col1, col2, col3, col4, col5 = st.columns(5)
    programmes = col1.multiselect(
        "Programme", list(PROGRAMMES), format_func=lambda p: PROGRAMMES[p]
    )
    countries = col2.multiselect("Country", opts["countries"])
    sub_products = col3.multiselect("Field (Global Talent)", opts["sub_products"])
    duration_types = col4.multiselect("Duration", ["short", "medium", "long"])
    start_after = col5.date_input("Start on or after", value=None, min_value=date.today())

    col1, col2, col3, col4, col5 = st.columns(5, vertical_alignment="bottom")
    languages = col1.multiselect("Languages I speak", opts["languages"])
    study_level = col2.selectbox("My study level", [None, *STUDY_LEVELS])
    nationality = col3.selectbox("My nationality", [None, *opts["nationalities"]])
    accommodation_covered = col4.checkbox("Accommodation covered")
    food_covered = col4.checkbox("Food covered")
    top_k = col5.slider("Results", 5, 30, 10)

left, right = st.columns([1, 2])

with left:
    st.subheader("Profile")
    about = st.text_area(
        "About me / what I'm looking for",
        placeholder="e.g. Computer science student, want to teach kids coding abroad this summer",
        height=120,
    )
    skills = st.multiselect("Skills", opts["skills"])
    backgrounds = st.multiselect("Backgrounds", opts["backgrounds"])
    causes = st.multiselect(
        "Causes I care about", list(SDG_GOALS), format_func=lambda goal: SDG_GOALS[goal]
    )
    cv_file = st.file_uploader("CV (PDF)", type="pdf")
    cv_text = cached_cv_text(cv_file.getvalue()) if cv_file else ""

    profile_text = build_profile_text(about, skills, backgrounds, causes, cv_text)
    with st.expander("Text sent for embedding"):
        st.text(profile_text or "(empty)")

filter = build_filter(
    programmes=programmes,
    countries=countries,
    sub_products=sub_products,
    duration_types=duration_types,
    languages=languages,
    all_languages=opts["languages"],
    study_level=study_level,
    nationality=nationality,
    start_after=start_after,
    accommodation_covered=accommodation_covered,
    food_covered=food_covered,
)

with right:
    st.subheader("Matches")
    with st.expander("Metadata filter"):
        st.json(filter)

    if not profile_text:
        st.info("Fill in at least one profile field to see matches.")
        st.stop()

    with st.spinner("Matching..."):
        matches = cached_search(profile_text, filter, top_k)

    if not matches:
        st.warning("No opportunities match these filters.")

    for match in matches:
        programme = match.get("programme", "")
        url = OPPORTUNITY_URL.get(programme, "{}").format(match["id"])
        with st.container(border=True):
            st.markdown(
                f"**[{match.get('title', match['id'])}]({url})**  ·  score {match['score']:.3f}"
            )
            details = [
                PROGRAMMES.get(programme, programme),
                match.get("sub_product"),
                match.get("location") or match.get("country"),
                match.get("duration_type"),
                f"{int(match.get('available_openings', 0))} openings",
            ]
            st.caption("  ·  ".join(str(d) for d in details if d))
            if match["duplicate_ids"]:
                st.caption(
                    f"+{len(match['duplicate_ids'])} more slots of the same project"
                )
            with st.expander("Details"):
                st.text(match.get("embedding_text", ""))
                st.json(
                    {
                        k: v
                        for k, v in match.items()
                        if k not in ("embedding_text", "text_hash")
                    }
                )
