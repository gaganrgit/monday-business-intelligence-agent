# Monday Business Intelligence Agent

A conversational AI assistant that answers founder-level business intelligence
questions using **live data from monday.com**. Users import two CSVs (Deals,
Work Orders) into monday.com as boards; from that point on, the app never
touches the original CSV files — every answer is computed from a fresh
GraphQL read of monday.com.

---

## 1. Project Overview

- **Frontend**: Streamlit chat UI (chat history, chat input, sidebar with
  example questions, "Generate Leadership Update" button)
- **Backend**: FastAPI service exposing `POST /chat` and
  `GET /leadership-summary`
- **Data source**: monday.com GraphQL API (read-only — never creates,
  updates, or deletes records)
- **LLM**: Fireworks AI, used only to turn pre-computed analytics into
  founder-friendly narrative answers (raw board data is never sent to the LLM)
- **Deployment**: A single Render web service running both FastAPI and
  Streamlit together (avoids CORS and simplifies deployment)

## 2. Architecture

```
Founder
  │
  ▼
Streamlit Chat UI  (frontend/streamlit_app.py)
  │  HTTP (same container, localhost)
  ▼
FastAPI Backend  (backend/main.py)
  │
  ▼
MondayService → Monday.com GraphQL API   (live read, every request)
  │
  ▼
Data Cleaning   (backend/utils/data_cleaning.py)
  │
  ▼
Business Analytics   (backend/analytics/analytics_engine.py)
  │
  ▼
FireworksService → Fireworks AI   (summary JSON only, never raw data)
  │
  ▼
Business Insight Response → Founder
```

No LangGraph, no multi-agent orchestration, no vector DB/RAG, no
Redis/Celery/Kafka. Just a straightforward request → fetch → clean →
analyze → summarize → respond pipeline.

## 3. Folder Structure

```
Monday_Business_Intelligence_Agent/
├── backend/
│   ├── app/
│   │   ├── config.py          # env var loading
│   │   ├── logger.py          # logging setup
│   │   └── schemas.py         # request/response models
│   ├── services/
│   │   ├── monday_service.py       # GraphQL client (read-only)
│   │   ├── fireworks_service.py    # LLM client
│   │   └── chat_orchestrator.py    # ties the pipeline together
│   ├── analytics/
│   │   ├── analytics_engine.py     # pure metric functions
│   │   └── report_generator.py     # leadership Markdown report
│   ├── utils/
│   │   ├── data_cleaning.py        # normalization / safe parsing
│   │   └── query_understanding.py  # intent + entity extraction
│   ├── models/
│   │   └── data_models.py          # column alias definitions
│   ├── main.py                     # FastAPI app + routes
│   └── requirements.txt
├── frontend/
│   ├── streamlit_app.py
│   └── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── render.yaml
├── requirements.txt            # combined, used by Render build
└── start.sh                    # launches backend + frontend together
```

## 4. Setup Instructions

### Prerequisites
- Python 3.11+
- A monday.com account with two boards: **Deals** and **Work Orders**
  (created by importing the provided CSVs)
- A Fireworks AI API key

### Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configure environment variables

```bash
cp .env.example .env
# then edit .env with your real values
```

## 5. Monday.com Configuration

1. Import the Deals CSV into a new monday.com board named e.g. "Deals".
2. Import the Work Orders CSV into a second board named e.g. "Work Orders".
3. Open each board and copy its Board ID from the URL
   (`https://yourteam.monday.com/boards/1234567890` → `1234567890`).
4. Generate a personal API token: monday.com → Avatar (bottom left) →
   Admin/Developer → API → **Generate token** (or **My Access Tokens** →
   **Developer** section).
5. Set `MONDAY_API_TOKEN`, `DEALS_BOARD_ID`, `WORKORDERS_BOARD_ID` in `.env`.

Column titles don't need to match exactly — `backend/models/data_models.py`
maps common aliases (e.g. "Client" / "Client Code" / "Customer Code" all map
to the same canonical field) case-insensitively.

## 6. Fireworks Configuration

1. Create an account at [fireworks.ai](https://fireworks.ai).
2. Generate an API key from the dashboard.
3. Set `FIREWORKS_API_KEY` in `.env`.
4. Optionally override `FIREWORKS_MODEL` (defaults to a Llama 3.1 70B
   instruct model on Fireworks).

## 7. Environment Variables

| Variable              | Required | Description                                    |
|------------------------|----------|------------------------------------------------|
| `MONDAY_API_TOKEN`     | Yes      | monday.com API token (read access)              |
| `DEALS_BOARD_ID`       | Yes      | Board ID of the Deals board                     |
| `WORKORDERS_BOARD_ID`  | Yes      | Board ID of the Work Orders board                |
| `FIREWORKS_API_KEY`    | Yes      | Fireworks AI API key                            |
| `FIREWORKS_MODEL`      | No       | Fireworks model id (has a sensible default)      |
| `BACKEND_URL`          | No       | Where Streamlit finds FastAPI (local dev only)   |
| `PORT`                 | No       | Port FastAPI/Streamlit bind to                   |
| `LOG_LEVEL`            | No       | Python logging level (default `INFO`)            |

These values are only ever read server-side (`backend/app/config.py`) and
are **never** sent to the Streamlit frontend or exposed in API responses.

## 8. Running Locally

Run the backend and frontend in two terminals:

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
BACKEND_URL=http://localhost:8000 streamlit run frontend/streamlit_app.py
```

Or run both together the same way Render does:

```bash
bash start.sh
```

Then open the Streamlit URL printed in the terminal (typically
`http://localhost:8501`).

## 9. Deployment on Render

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint** and point it at the repo (it will
   detect `render.yaml`), or create a single **Web Service** manually with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `bash start.sh`
3. Add the required environment variables in the Render dashboard:
   `MONDAY_API_TOKEN`, `DEALS_BOARD_ID`, `WORKORDERS_BOARD_ID`,
   `FIREWORKS_API_KEY`.
4. Deploy. Render routes external traffic to `$PORT`, which `start.sh`
   assigns to the Streamlit process; FastAPI runs internally on port 8000
   and is only reached by Streamlit over `localhost`, so there's no CORS
   configuration to manage in production.

## 10. API Endpoints

### `POST /chat`
Request:
```json
{ "message": "How is our pipeline this quarter?" }
```
Response:
```json
{ "answer": "..." }
```

### `GET /leadership-summary`
Returns a Markdown report (`Content-Type: text/plain`) with sections:
Executive Summary, Revenue Overview, Pipeline Health, Sector Performance,
Operational Status, Billing & Collections, Risks, Recommendations, Data
Quality Notes.

### `GET /health`
Returns configuration status (no secrets):
```json
{ "status": "ok", "monday_configured": true, "fireworks_configured": true }
```

## 11. Assumptions

- Each monday.com item (row) on both boards represents one Deal or one Work
  Order respectively; column *titles* may vary slightly from the exact names
  in the spec (case-insensitive alias matching is used).
- "Open" deals are those with a status in `{Open, In Progress, Active,
  Pending}`; this can be adjusted in `analytics_engine.py` if your team uses
  different labels.
- A work order is considered "delayed" if its execution status matches a
  delayed/overdue label OR its end date has passed without being marked
  complete.
- Dates may arrive in a variety of formats from monday.com; they are parsed
  leniently and treated as missing (not fatal) if unparseable.
- No authentication is required per the assignment scope; this is not
  intended for handling sensitive data in a multi-tenant production setting
  as-is.

## 12. Limitations

- The app fetches the full contents of both boards on every request (no
  caching layer), which is simple and always fresh but may be slower on very
  large boards (thousands of items).
- Query understanding is keyword/rule-based rather than a full NLU model, so
  highly unusual phrasings may fall back to a general pipeline/revenue
  overview instead of the most specific analytic.
- Only one clarification round-trip is supported (ambiguous "pipeline"
  questions); deeper multi-turn disambiguation is out of scope.
- If Fireworks AI is unavailable, the app falls back to a deterministic,
  non-narrative summary so the user still gets an answer rather than an
  error.
