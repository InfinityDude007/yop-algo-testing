import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ENDPOINT = "https://gis-api.aiesec.org/graphql"
PROGRAMMES = [7, 8, 9]
PER_PAGE = 500
OUTPUT_PATH = Path(__file__).parent / "data" / "opportunities.json"

query_fields = """
    id
    title
    programme { id short_name_display }
    sub_product { name }
    description
    project_description
    company_description
    skills { constant_name option }
    backgrounds { constant_name option }
    languages { constant_name option }
    study_levels { name }
    nationalities { constant_name }
    sdg_info { sdg_target { goal_index target_index description } }
    role_info { learning_points_list }
    available_slots { id status start_date end_date applications_close_date available_openings }
    opportunity_duration_type { duration_type }
    home_mc { name }
    host_lc { name }
    location
    lat
    lng
    organisation { name }
    logistics_info {
        accommodation_covered accommodation_provided
        food_covered food_provided
        transportation_covered computer_provided
    }
    specifics_info { salary salary_currency { alphabetic_code } salary_periodicity }
"""


query = f"""
query ($page: Int!, $per_page: Int!, $programmes: [Int]) {{
    opportunities(filters: {{programmes: $programmes}}, is_v2: true, page: $page, per_page: $per_page) {{
        paging {{ total_items total_pages current_page }}
        data {{ {query_fields} }}
    }}
}}
"""


def load_token():
    load_dotenv()
    token = os.environ.get("GIS_TOKEN")

    if not token:
        sys.exit("GIS_TOKEN not set. Add GIS_TOKEN=<your token> to .env")
    return token


def fetch_page(token, page, retries=3):
    body = json.dumps(
        {
            "query": query,
            "variables": {"page": page, "per_page": PER_PAGE, "programmes": PROGRAMMES},
        }
    ).encode()

    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": token},
    )

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                sys.exit(
                    f"GIS API returned {error.code}: GIS_TOKEN in .env is invalid or expired. "
                    "Get a fresh token and update .env"
                )
            # other 4xx errors won't change on retry
            if error.code < 500 or attempt == retries:
                raise
            print(f"  page {page} failed ({error}), retrying...")
            time.sleep(2 * attempt)
            continue
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == retries:
                raise
            print(f"  page {page} failed ({error}), retrying...")
            time.sleep(2 * attempt)
            continue

        if result.get("errors"):
            sys.exit(
                f"GraphQL error on page {page}: {json.dumps(result['errors'], indent=2)}"
            )

        return result["data"]["opportunities"]

    raise RuntimeError("unreachable: the last failed attempt re-raises")


def fetch_opportunities():
    token = load_token()
    opportunities = []
    page, total_pages = 1, 1

    while page <= total_pages:
        result = fetch_page(token, page)
        total_pages = result["paging"]["total_pages"]
        opportunities.extend(result["data"])
        print(
            f"page {page}/{total_pages}: {len(opportunities)}/{result['paging']['total_items']}"
        )
        page += 1

    # write to a temp file first
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(opportunities, indent=2, ensure_ascii=False))
    tmp_path.replace(OUTPUT_PATH)
    print(f"Wrote {len(opportunities)} opportunities to {OUTPUT_PATH}")
