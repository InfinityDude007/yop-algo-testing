# YOP Matching Test
Lightweight repo to test embedding techniques for YOP matching.

Open GV, GTa and GTe opportunities are pulled from the GIS GraphQL API, embedded with Amazon Bedrock (Titan Text Embeddings V2) and stored in S3 Vectors with metadata for filtering.
A Streamlit interface builds a profile from free text, picked skills, causes and an optional CV, then returns the closest opportunities that pass the selected filters.

## Requirements
- Python 3.12+
- A GIS access token
- AWS credentials configured locally (`aws configure`) with access to:
  - `bedrock:InvokeModel` on `amazon.titan-embed-text-v2:0`
  - `s3vectors` index and vector actions on the `yop-test` bucket (`CreateIndex`, `DeleteIndex`, `GetIndex`, `PutVectors`, `GetVectors`, `QueryVectors`)

## Running locally:

1. Clone the repository:
```bash
git clone git@github.com:InfinityDude007/yop-algo-testing.git
cd yop-algo-testing
```

2. Create and activate a virtual environment:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
```
Then set `GIS_TOKEN` in `.env`. The other values default to the shared test bucket:

| Variable | Description |
|---|---|
| `GIS_TOKEN` | GIS API access token. Tokens expire, so a `401` means it needs refreshing |
| `AWS_REGION` | Region of the vector bucket and Bedrock model (`eu-west-1`) |
| `VECTOR_BUCKET` | S3 vector bucket name (`yop-test`) |
| `VECTOR_INDEX` | Index inside the bucket (`opportunities`), recreated on every upload |

5. Fetch, build and upload the opportunities:
```bash
python orchestrator.py
```

6. Start the interface:
```bash
streamlit run interface.py
```

## How it works
`orchestrator.py` runs three steps. Each one overwrites its output, so re-running refreshes everything.

1. **Fetch** (`utils/fetch_opportunities.py`): queries `opportunities` with `is_v2: true`, which only returns open opportunities with live slots, and writes `utils/data/opportunities.json`. Edit `query_fields` to add or drop fields.
2. **Build** (`utils/build_documents.py`): turns each opportunity into a document with
   - `embedding_text`: title, programme, field, descriptions, SDG cause, skills, backgrounds and learning points, for semantic matching
   - `metadata`: flat fields for filtering (programme, country, duration, languages, study levels, nationalities, logistics, salary, slot dates)

   Output goes to `utils/data/documents.json`.
3. **Upload** (`utils/vector_store.py`): embeds each distinct text once with Titan (1024 dimensions), recreates the index and puts all vectors with their metadata. `embedding_text`, `title` and location fields are stored as non-filterable metadata to stay under the 2KB filterable limit.

At search time (`utils/matching.py` + `utils/vector_store.py`), the profile is turned into text with the same labels as the opportunities, embedded with Titan and queried against the index with a metadata filter built from the UI. Copies of the same project share a `text_hash`, so duplicate hits are collapsed into one result.

## Project structure
```
├── orchestrator.py            # fetch → build → upload pipeline
├── interface.py               # Streamlit UI
├── requirements.txt
├── .env.example
└── utils/
    ├── fetch_opportunities.py # GIS GraphQL fetch
    ├── build_documents.py     # embedding_text + metadata per opportunity
    ├── vector_store.py        # Titan embeddings, S3 Vectors upload and search
    ├── matching.py            # profile text, filters, CV parsing, UI options
    └── data/                  # generated JSON (gitignored)
```

## Notes
- `utils/data/` is gitignored, so run `python orchestrator.py` after cloning before starting the interface.
- A full re-index of ~3k opportunities takes under a minute and costs a few cents (Titan is $0.02 per 1M tokens).
- Opportunities listing more than 60 nationalities are treated as open to all nationalities, to fit the metadata limit.
- Scores are cosine similarity. Compare them between results rather than reading them as percentages.
