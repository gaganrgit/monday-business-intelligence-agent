# Decision Log – Monday.com Business Intelligence Agent

**Author:** Skylark Drones Assignment Submission  
**Date:** July 2026  
**Time Budget:** 6 hours

---

# 1. Key Assumptions

### Monday.com board structure is flexible

The assignment required importing two CSVs into Monday.com and allowed column types to be configured as needed. I assumed the imported column names would be similar, but not necessarily identical, to the CSV headers. To make the solution resilient, I implemented a case-insensitive alias mapping layer (`data_models.py`) that maps common variations (e.g., **Client**, **Client Code**, **Customer Code**) to a canonical field name. This allows the application to work even if board columns are renamed.

### Open pipeline requires a business definition

The dataset contained multiple deal status values (Won, Dead, Active, In Progress, etc.) without a single definition of "open". I adopted an exclusion approach: a deal is considered open when its status is **not** part of a configurable closed-status set (`CLOSED_DEAL_STATUSES`). This is more robust than maintaining a whitelist because custom workflow statuses continue to work without code changes.

### Delayed work orders require both status and schedule checks

A work order is considered delayed if either:

- its execution status indicates delay, **or**
- its planned end date has passed without reaching a completed/delivered status.

Using both checks improves resilience when operational status fields are incomplete or outdated.

### Business metrics must be deterministic

A major architectural decision was separating business computation from natural language generation. All KPIs—including revenue, pipeline, weighted pipeline, trends, rankings, and sector summaries—are computed deterministically in Python before being sent to the LLM. The LLM receives only a structured evidence package and is responsible solely for explanation, not calculation. This minimizes hallucinations and improves auditability.

### Graceful handling of empty time windows

Some time-based queries (e.g., "this quarter") may legitimately return no records because the dataset contains no data for the requested period. Rather than returning misleading zero metrics, the system explicitly informs the user that no data exists for that time window and falls back to presenting the latest available historical metrics, clearly labeling them as historical rather than current-period values.

### No authentication for prototype scope

The assignment focuses on BI capabilities rather than user management. The prototype therefore exposes read-only functionality without authentication. This limitation is documented in the README and would be addressed in a production deployment.

---

# 2. Trade-offs

### Rule-based intent parsing vs. LLM intent classification

I implemented deterministic rule-based intent extraction (`query_understanding.py`) instead of asking the LLM to classify user queries.

**Advantages**

- predictable behavior
- lower latency
- zero additional API cost
- easy debugging and testing

The LLM still receives the original user question for natural language generation but does not decide which business computations to execute.

---

### No caching layer

Every request retrieves fresh data from Monday.com using GraphQL.

**Advantages**

- always reflects current board state
- avoids cache invalidation complexity
- simpler implementation within the assignment timeframe

**Trade-off**

Higher latency and additional API requests.

With additional time, I would introduce a short-lived (60–300 second) TTL cache.

---

### Single-service deployment

The prototype runs FastAPI and Streamlit together using a single Render Web Service and a shared startup script.

**Advantages**

- simpler deployment
- minimal infrastructure
- avoids CORS configuration
- suitable for Render free tier

**Trade-off**

Frontend and backend cannot scale independently.

---

### Fireworks AI for response generation

The application uses Fireworks AI with DeepSeek V4 Pro for response generation.

The business computation layer performs all numerical calculations before invoking the model, ensuring that the model explains verified analytics rather than generating business metrics itself.

---

### Structured evidence instead of raw DataFrames

Instead of exposing raw datasets to the LLM, the Business Computation Layer (`evidence_builder.py`) creates a structured evidence package containing verified metrics, warnings, rankings, and recommendations.

**Advantages**

- deterministic calculations
- traceable outputs
- easier debugging
- prevents numerical hallucinations

---

### Retry logic with exponential backoff

Transient Monday.com API failures are retried with exponential backoff, while permanent errors (authentication failures, missing boards, etc.) are surfaced immediately.

This improves reliability without unnecessarily delaying unrecoverable failures.

---

# 3. What I Would Do Differently With More Time

### Multi-turn conversation memory

Currently, conversation history exists only within the Streamlit session. Follow-up questions such as "break that down by month" lose prior analytical context.

A production implementation would maintain a server-side conversation context passed with each request.

---

### Expanded clarification handling

The current system asks clarification questions only for genuinely ambiguous pipeline requests.

With more time, I would extend clarification flows for other ambiguous business questions, such as unspecified time ranges or grouping dimensions.

---

### Short-lived caching

Introducing a 2–5 minute in-memory cache for Monday.com board retrieval would substantially reduce repeated query latency while maintaining acceptable data freshness.

---

### Semantic column matching

The current alias mapping is manually maintained.

A semantic matching approach using embeddings or similarity search could automatically adapt to arbitrary customer-specific column names.

---

### Streaming responses

Responses are currently returned after complete generation.

Server-Sent Events (SSE) or streaming responses would improve perceived responsiveness, particularly for leadership summaries.

---

# 4. Interpretation of "Leadership Updates"

I interpreted "leadership updates" as concise executive summaries intended for business stakeholders rather than operational users.

The goal is to provide a short, decision-oriented report covering commercial performance, operational health, business risks, recommendations, and data quality caveats without requiring leaders to inspect dashboards or raw datasets.

To support this, I implemented:

- a dedicated `GET /leadership-summary` endpoint
- a "Generate Leadership Update" action in the Streamlit sidebar
- deterministic business analytics across both Monday.com boards
- structured evidence generation before invoking the LLM

The generated report contains the following sections:

- Executive Summary
- Revenue Overview
- Pipeline Health
- Sector Performance
- Operational Status
- Billing & Collections
- Risks
- Recommendations
- Data Quality Notes

All business metrics are computed by the Business Computation Layer. The LLM is responsible only for producing a readable executive narrative while preserving the supplied evidence without modifying business calculations.

---

*Approximately two pages.*