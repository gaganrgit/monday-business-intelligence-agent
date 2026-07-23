# 📊 Monday Business Intelligence Agent

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32.0-FF4B4B.svg)](https://streamlit.io/)
[![Monday.com API](https://img.shields.io/badge/Monday.com-GraphQL%20v2-6C5CE7.svg)](https://developer.monday.com/)
[![Fireworks AI](https://img.shields.io/badge/LLM-Fireworks%20AI-orange.svg)](https://fireworks.ai/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

A conversational AI assistant designed for founders and executives to query business intelligence directly from **live monday.com boards** (Deals and Work Orders). 

Users import operational CSVs into monday.com as boards; from that point forward, the application operates purely via fresh, read-only GraphQL queries against monday.com. It features a **deterministic Python Business Computation Layer** to prevent numerical LLM hallucinations, ensuring all KPIs, win rates, revenue pipeline figures, and operational delays are calculated with 100% precision.

---

## 📋 Table of Contents
- [1. Key Capabilities](#1-key-capabilities)
- [2. Application Screenshots & Visual Showcase](#2-application-screenshots--visual-showcase)
- [3. Architecture & Design Philosophy](#3-architecture--design-philosophy)
- [4. Project Directory Structure](#4-project-directory-structure)
- [5. Setup & Installation](#5-setup--installation)
- [6. Monday.com Board Configuration](#6-mondaycom-board-configuration)
- [7. Fireworks AI Integration](#7-fireworks-ai-integration)
- [8. Environment Variables](#8-environment-variables)
- [9. Running Locally](#9-running-locally)
- [10. Deployment Options](#10-deployment-options)
- [11. API Specification](#11-api-specification)
- [12. Supported Business Intelligence Queries](#12-supported-business-intelligence-queries)
- [13. Key Assumptions & Data Intelligence](#13-key-assumptions--data-intelligence)
- [14. Limitations & Architectural Trade-offs](#14-limitations--architectural-trade-offs)
- [15. Verification & Troubleshooting](#15-verification--troubleshooting)

---

## 1. Key Capabilities

- **Zero LLM Calculation Hallucination**: Pure Python analytics engine calculates revenue, pipeline value, win rates, sector distribution, delayed work orders, and billing metrics before passing structured evidence to Fireworks AI for executive synthesis.
- **Live Monday.com Read-Only Integration**: Performs direct GraphQL queries against monday.com on every request—no database, no stale local storage, and zero write operations back to monday.com.
- **Dynamic Column Alias Mapping**: Flexible schema normalization matching column variations (e.g., `Client`, `Client Code`, `Customer Code`) case-insensitively, tolerating custom board setups.
- **Cross-Board Analytics Correlation**: Blends performance data from both **Deals** and **Work Orders** boards using `Client Code` as the common key to surface revenue leakage, sector risks, and operational bottlenecks.
- **Smart Time Intelligence & Historical Fallback**: Handles exact time windows ("this quarter", "Q3 2026", "this year"). If a requested period contains no data, the engine explicitly alerts the user and provides historical context rather than silent zero values.
- **Executive Leadership Report Generation**: Instant one-click generation (`GET /leadership-summary` or Streamlit sidebar action) producing an executive summary with financial, pipeline, operational, risk, and data quality insights.
- **Data Quality & Hygiene Audit**: Detects duplicate records, missing closure dates, unparseable monetary figures, and invalid status values automatically.
- **Resilient API Architecture**: Features exponential backoff retries for Monday API connection resets and graceful fallback to deterministic Markdown summaries if Fireworks AI is unavailable.

---

## 2. Application Screenshots & Visual Showcase

### 💬 Conversational BI Assistant (Chat Interface)
Query your monday.com boards in natural language and receive instant, evidence-backed executive responses.
![Conversational AI Chat Interface](results/Screenshot%202026-07-23%20163241.png)

### 📈 Executive Analytics Dashboard
Real-time KPI cards and interactive charts showing Open Pipeline, Weighted Pipeline, Total Invoiced Revenue, Receivables, and Sector Breakdown.
![Analytics Dashboard Overview & Key Metrics](results/Screenshot%20(13).png)

### 📊 Pipeline Probability & Work Order Status
Detailed visual distribution of closure probabilities, work order execution progress, and collection statuses.
![Closure Probability & Work Order Execution Status](results/Screenshot%20(14).png)

### ⚠️ Operational Risk & Delayed Work Orders
Automated identification of delayed projects and upcoming 30-day deal closures to highlight operational bottlenecks.
![Delayed Work Orders & Upcoming Closures](results/Screenshot%20(15).png)

### 🏆 Executive Leaderboards (Customers & Sectors)
Live ranking of top customers by deal volume, sector revenue distributions, and top deal owners.
![Executive Leaderboard - Customers & Sectors](results/Screenshot%20(16).png)

### 💰 Billing & Receivables Leaderboard
Real-time tracking of largest individual deals, top-billed accounts, and highest outstanding receivables.
![Executive Leaderboard - Performers & Receivables](results/Screenshot%20(17).png)

---

## 3. Architecture & Design Philosophy

```
                                  +-----------------------+
                                  |        Founder        |
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  | Streamlit Chat & UI   |  (frontend/streamlit_app.py)
                                  +-----------+-----------+
                                              | HTTP (Local Loopback / IPC)
                                              v
                                  +-----------------------+
                                  |    FastAPI Backend    |  (backend/main.py)
                                  +-----------+-----------+
                                              |
      +---------------------------------------+---------------------------------------+
      |                                       |                                       |
      v                                       v                                       v
+-----------------------+           +-----------------------+           +-----------------------+
|    MondayService      |           | Query Understanding   |           |    Data Cleaning      |
| (GraphQL Live Fetch)  |           |  (Intent Extraction)  |           | (Alias Normalization) |
+-----------+-----------+           +-----------+-----------+           +-----------+-----------+
            |                                 |                                 |
            +---------------------------------+---------------------------------+
                                              |
                                              v
                                  +-----------------------+
                                  | Business Computation  |  (backend/helpers/*)
                                  |   Analytics Engine    |  (backend/analytics/*)
                                  +-----------+-----------+
                                              | Verified Metrics & Evidence Package
                                              v
                                  +-----------------------+
                                  |   Fireworks AI Service|  (LLM Narrative Synthesis)
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  | Executive Response /  |
                                  |   Leadership Report   |
                                  +-----------------------+
```

### Design Principles:
1. **Separation of Computation and Narrative**: Business math is 100% deterministic (Python). The LLM is restricted strictly to framing verified numerical outputs into clear, professional founder narratives.
2. **Lean Architecture**: No vector databases (RAG), heavy agents, or complex message queues (Redis/Celery/Kafka). A direct request-response pipeline ensures sub-second processing and easy maintainability.
3. **Unified Single-Container Runtime**: Managed via a supervisor script (`start.sh`) that runs FastAPI on an internal port and Streamlit on the public port, avoiding CORS complexities and reducing deployment memory overhead.

---

## 4. Project Directory Structure

```
monday-business-intelligence-agent/
├── backend/
│   ├── analytics/
│   │   ├── analytics_engine.py      # Core metric calculations (Revenue, Pipeline, Work Orders)
│   │   └── report_generator.py      # Leadership update Markdown generator
│   ├── app/
│   │   ├── config.py               # Pydantic environment configuration
│   │   ├── logger.py               # Structured logging configuration
│   │   └── schemas.py              # FastAPI request/response Pydantic schemas
│   ├── helpers/
│   │   ├── calculation_helper.py    # General mathematical & aggregator utilities
│   │   ├── data_quality_helper.py   # Board sanity checks & hygiene metrics
│   │   ├── evidence_builder.py      # Prepares deterministic packages for LLM prompt
│   │   ├── pipeline_helper.py       # Open/weighted pipeline and deal status analytics
│   │   ├── revenue_helper.py        # Revenue, ARR/MRR, and collection computations
│   │   ├── time_intelligence_helper.# Flexible date parsing and time window filtering
│   │   └── workorder_helper.py      # Work order status, delay detection, & cross-board links
│   ├── models/
│   │   └── data_models.py           # Canonical schema definitions & dynamic column alias map
│   ├── services/
│   │   ├── chat_orchestrator.py     # Pipeline coordinator tying query, data, engine & LLM
│   │   ├── fireworks_service.py     # LLM service client with fallback formatting
│   │   └── monday_service.py        # Read-only Monday.com GraphQL API client with retries
│   ├── utils/
│   │   ├── data_cleaning.py         # Data type normalization, date parsing, numeric casting
│   │   └── query_understanding.py   # Intent classification & entity extraction engine
│   ├── main.py                      # FastAPI application entry point & route definitions
│   └── requirements.txt             # Backend specific dependencies
├── frontend/
│   ├── streamlit_app.py             # Streamlit chat interface, dashboard, & action sidebar
│   └── requirements.txt             # Frontend specific dependencies
├── .env.example                     # Template environment variables
├── .gitignore                       # Git ignore rules
├── DECISION_LOG.md                  # Detailed architectural decision record & trade-offs
├── Dockerfile                       # Multi-stage production container specification
├── docker-compose.yml               # Local & staging container orchestration configuration
├── Procfile                         # Deployment configuration for Heroku/Railway
├── README.md                        # Master project documentation
├── render.yaml                      # Render Blueprint infrastructure specification
├── requirements.txt                 # Combined project dependencies
└── start.sh                         # Process supervisor launching FastAPI & Streamlit
```

---

## 5. Setup & Installation

### Prerequisites
- **Python**: Version 3.11 or higher
- **Monday.com Account**: Access with permission to read two boards (Deals & Work Orders)
- **Fireworks AI Key**: API Key from [fireworks.ai](https://fireworks.ai)

### Step 1: Clone Repository & Create Virtual Environment
```bash
git clone https://github.com/gaganrgit/monday-business-intelligence-agent.git
cd monday-business-intelligence-agent

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 6. Monday.com Board Configuration

1. **Import CSVs into monday.com**:
   - Import the **Deals** CSV into a new monday.com board (name it e.g. `Deals`).
   - Import the **Work Orders** CSV into a second monday.com board (name it e.g. `Work Orders`).
2. **Obtain Board IDs**:
   - Open each board in your browser.
   - Extract the numeric Board ID from the URL (e.g. `https://yourteam.monday.com/boards/1234567890` -> Board ID is `1234567890`).
3. **Generate API Token**:
   - Click your user profile picture (bottom left) in monday.com -> **Administration** / **Developers** -> **API**.
   - Copy or generate a personal API Token.
4. **Column Alias Mapping**:
   - The application automatically maps flexible board column names using canonical aliases defined in `backend/models/data_models.py`. Standard variations like `Client`, `Client Code`, `Customer Code`, `Deal Value`, `Amount`, `Contract Value`, etc., are normalized automatically.

---

## 7. Fireworks AI Integration

1. Register an account at [fireworks.ai](https://fireworks.ai).
2. Generate an API Key under Account Settings.
3. Configure your `.env` file with `FIREWORKS_API_KEY`.
4. (Optional) Set `FIREWORKS_MODEL`. Defaults to `accounts/fireworks/models/llama-v3p1-70b-instruct`.

---

## 8. Environment Variables

Create a `.env` file in the root directory (or copy `.env.example`):

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `MONDAY_API_TOKEN` | **Yes** | - | Personal access API token for monday.com (Read access) |
| `DEALS_BOARD_ID` | **Yes** | - | Numeric board ID for the Deals board |
| `WORKORDERS_BOARD_ID` | **Yes** | - | Numeric board ID for the Work Orders board |
| `FIREWORKS_API_KEY` | **Yes** | - | Fireworks AI API key |
| `FIREWORKS_MODEL` | No | `accounts/fireworks/models/llama-v3p1-70b-instruct` | LLM model identifier on Fireworks AI |
| `BACKEND_URL` | No | `http://127.0.0.1:8000` | FastAPI URL used by Streamlit frontend |
| `PORT` | No | `8501` | External web service port (Streamlit interface) |
| `BACKEND_INTERNAL_PORT` | No | `8000` | Internal port assigned to FastAPI backend |
| `LOG_LEVEL` | No | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 9. Running Locally

### Option A: Hardened Unified Script (Recommended)
Launches FastAPI backend on internal port `8000`, polls HTTP health until ready, and then starts Streamlit on port `8501`.

```bash
# On Linux/macOS or Git Bash:
bash start.sh
```

Then navigate your browser to `http://localhost:8501`.

### Option B: Dual Terminal Mode (For Active Development)

```bash
# Terminal 1 — Start FastAPI Backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Start Streamlit Frontend
BACKEND_URL=http://localhost:8000 streamlit run frontend/streamlit_app.py --server.port 8501
```

### Option C: Docker Compose
```bash
# Build and start container background daemon
docker compose up --build -d

# View live logs
docker compose logs -f
```

---

## 10. Deployment Options

### Deployment Option 1: Render (Blueprint Deployment)
The repository includes a ready-to-use `render.yaml` specification.
1. Push repository to GitHub.
2. In Render Dashboard, click **New +** -> **Blueprint** and connect your repository.
3. Supply required environment secrets (`MONDAY_API_TOKEN`, `DEALS_BOARD_ID`, `WORKORDERS_BOARD_ID`, `FIREWORKS_API_KEY`).
4. Render will auto-detect `render.yaml` and deploy the unified web service. External traffic routes to `$PORT` (Streamlit), while FastAPI runs internally.

### Deployment Option 2: Docker / Container Platforms
```bash
# Build container image
docker build -t monday-bi-agent .

# Run container with environment file
docker run -d \
  -p 8501:8501 \
  --env-file .env \
  --name monday-bi-agent \
  monday-bi-agent
```

### Deployment Option 3: Railway
1. Connect your repository to Railway.
2. Railway detects the `Procfile` (`web: bash start.sh`) automatically.
3. Configure required environment variables in Railway service settings.

### Deployment Option 4: GCP Cloud Run
```bash
# Build and submit image to Google Artifact Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/monday-bi-agent:latest

# Deploy to Cloud Run
gcloud run deploy monday-bi-agent \
  --image gcr.io/YOUR_PROJECT_ID/monday-bi-agent:latest \
  --port 8501 \
  --set-env-vars MONDAY_API_TOKEN=xxx,DEALS_BOARD_ID=xxx,WORKORDERS_BOARD_ID=xxx,FIREWORKS_API_KEY=xxx \
  --allow-unauthenticated
```

---

## 11. API Specification

### `POST /chat`
Submits a natural language query to the Business Intelligence Agent.

- **Request Body**:
  ```json
  {
    "message": "What is our current open pipeline value by sector?"
  }
  ```
- **Response**:
  ```json
  {
    "answer": "### Open Pipeline by Sector Overview\n\nOur current total open pipeline stands at **$1,250,000** across 14 active deals:\n\n- **Enterprise Drones**: $620,000 (5 deals, weighted: $310,000)\n- **Defense**: $410,000 (3 deals, weighted: $164,000)\n- **Agriculture**: $220,000 (6 deals, weighted: $88,000)..."
  }
  ```

### `GET /leadership-summary`
Generates and returns an executive Markdown report combining deals and work orders data.

- **Response Header**: `Content-Type: text/plain`
- **Sections Included**: Executive Summary, Revenue Overview, Pipeline Health, Sector Performance, Operational Status, Billing & Collections, Risks, Recommendations, Data Quality Notes.

### `GET /dashboard-data`
Returns live JSON analytics metrics and leaderboards powering executive dashboards.

- **Response**:
  ```json
  {
    "analytics": { ... },
    "leaderboards": { ... }
  }
  ```

### `GET /health`
Verifies backend status and configuration readiness.

- **Response**:
  ```json
  {
    "status": "ok",
    "monday_configured": true,
    "fireworks_configured": true
  }
  ```

---

## 12. Supported Business Intelligence Queries

The agent intelligently handles natural language questions across multiple commercial and operational dimensions:

| Dimension | Sample Prompt |
| :--- | :--- |
| **Pipeline & Sales** | *"How is our sales pipeline looking this quarter?"* <br> *"What is our total open pipeline value and weighted average?"* |
| **Revenue & Financials** | *"What is our total revenue collected and closed-won revenue?"* <br> *"Show me revenue performance breakdown by sector."* |
| **Work Orders & Operations** | *"Are there any delayed work orders?"* <br> *"What is the status of active work orders for Client X?"* |
| **Sector Performance** | *"Which sector is generating the highest revenue?"* <br> *"Compare win rates and average deal sizes across sectors."* |
| **Data Hygiene & Quality** | *"Are there any missing dates or invalid contract values in our boards?"* <br> *"Show me data quality warnings and duplicate entries."* |
| **Leadership Briefings** | *"Give me a complete executive update."* *(or use sidebar button)* |

---

## 13. Key Assumptions & Data Intelligence

1. **Open vs. Closed Deals**: A deal is defined as "Open" if its status is **not** in a closed set (`Won`, `Lost`, `Dead`, `Closed`). All non-closed deals (e.g., `In Progress`, `Under Negotiation`, `Proposal Sent`) contribute to the open pipeline.
2. **Work Order Delay Heuristic**: A work order is categorized as delayed if either its status explicitly signals delay (e.g., `Delayed`, `Blocked`, `On Hold`) **OR** its planned end date has passed without being marked `Completed` / `Delivered`.
3. **Cross-Board Correlation**: Client correlation links the Deals board to the Work Orders board via normalized `Client Code` strings.
4. **Time Window Intelligence**: If a query explicitly targets a time window with zero recorded activity (e.g., "Q4 2026"), the system notifies the founder that no records match the criteria and automatically surfaces historical metrics for context.

---

## 14. Limitations & Architectural Trade-offs

- **Direct Read-Through Fetching**: Each incoming query triggers a fresh GraphQL fetch against monday.com. This ensures zero stale data, but adds API network overhead on large boards.
- **Single-Turn Intent Extraction**: Ambiguous queries return explicit clarification options rather than complex multi-turn conversational trees.
- **Prototype Security Boundary**: Auth is omitted per assignment scope. Production deployment requires adding OAuth2/JWT middleware to FastAPI routes.

---

## 15. Verification & Troubleshooting

### Health Check Verification
```bash
# Verify FastAPI backend status:
curl http://localhost:8000/health

# Expected Output:
# {"status":"ok","monday_configured":true,"fireworks_configured":true}

# Verify Streamlit web interface:
curl http://localhost:8501/_stcore/health
```

### Signal Handling & Graceful Shutdown
The unified process supervisor `start.sh` traps `SIGTERM` and `SIGINT` signals, ensuring both backend (Uvicorn) and frontend (Streamlit) child processes terminate cleanly without port leakage.

---

*For detailed architectural evolution, trade-offs, and assignment decision records, please inspect [`DECISION_LOG.md`](file:///c:/projects/monday-business-intelligence-agent/DECISION_LOG.md).*

