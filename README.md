# Trip Planner Agent

Trip Planner Agent is now split into two product lines:

- `智能助手`: a general-purpose assistant for questions, explanations, and idea
  structuring
- `流程工作台`: a structured, form-driven travel planning workbench for
  generating and saving travel plans

## Structure

- `backend/`: Django API, assistant conversation persistence, structured planning runs, trip plan persistence, live data integrations, workflow orchestration, and tests
- `frotend/`: Vue 3 dual-entry shell with standalone assistant pages, structured planning workbench, and plan assets
- `openspec/`: proposal, design, specs, and tracked tasks for product changes

## Local setup

### View
[![Uploading PixPin_2026-06-03_22-52-00.png…]()](https://img.cdn1.vip/i/6a203fcee2333_1780498382.webp)



### Backend

1. Use `uv sync` inside `backend/` to install Python dependencies into `.venv`.
3. Copy `backend/.env.example` to `backend/.env`.
4. Configure the database:
   - local development can keep `USE_MYSQL=false`
   - MySQL uses `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`
4. Provide real credentials for:
   - `DASHSCOPE_API_KEY`
   - `AMAP_API_KEY`
   - `BAIDU_MAPS_API_KEY`
5. Run:
   - `python manage.py migrate`
   - `python manage.py runserver 127.0.0.1:8001`
   - `python manage.py run_planning_worker` when `TRIP_PLANNER_INLINE_JOBS=false`

### Frontend

1. Install dependencies from `frotend/package.json` with `npm install`.
2. Copy `frotend/.env.example` to `frotend/.env`.
3. Start the dev server with `npm run dev`.

## Provider prerequisites

- Qwen `qwen3.5-plus` access requires a valid DashScope API key.
- `QWEN_ENABLE_THINKING=false` is the default recommended setting for this
  project because it shortens response time and avoids very large reasoning
  payloads on the core planning path.
- Amap text search and route-direction estimation both reuse the same Web Service key.
- Baidu Maps place search requires a valid `ak` and is used for food and hotel
  candidate retrieval in the current personal-developer-friendly setup.
- Hotel results are map-based location candidates, not OTA real-time inventory
  or guaranteed booking prices.
- When provider credentials are missing or a provider fails, the backend returns
  degraded output with source and warning metadata instead of silently hiding
  the issue.

## Product workflow

### 1. 智能助手

1. Enter the assistant page and ask a question or discuss an idea.
2. The backend stores the exchange in assistant-specific conversation/message
   models.
3. Assistant history can be resumed later without carrying travel-planning
   semantics.

### 2. 流程工作台

1. Enter the workbench and fill out structured travel constraints.
2. Submit the form to trigger a planning run through `/api/plans/`.
3. Review the generated result and execution timeline.
4. Save the run directly as a draft or final trip plan asset.

### 3. 方案资产

1. View drafts and final plans in `我的方案`.
2. Distinguish whether a plan came from the new workbench or legacy chat
   planning flows.
3. Continue refining workbench-origin plans by pre-filling structured
   constraints back into the workbench.

## Main APIs

- Identity and continuity:
  - `POST /api/auth/codes/`
  - `POST /api/auth/login/verify/`
  - `POST /api/auth/login/password/`
  - `POST /api/auth/password/`
  - `GET /api/auth/me/`
- Assistant conversations:
  - `POST /api/assistant/conversations/`
  - `GET /api/assistant/conversations/`
  - `GET /api/assistant/conversations/recent/`
  - `GET /api/assistant/conversations/<conversation_id>/`
  - `POST /api/assistant/conversations/<conversation_id>/messages/`
- Structured planning workbench:
  - `POST /api/chat/sessions/`
  - `GET /api/chat/sessions/recent/`
  - `POST /api/chat/sessions/<session_id>/messages/`
  - `GET /api/chat/sessions/<session_id>/`
  - `GET /api/chat/sessions/<session_id>/turns/<turn_id>/`
  - `POST /api/chat/sessions/<session_id>/plans/`
  - `POST /api/plans/`
  - `GET /api/plans/<run_id>/`
  - `POST /api/plans/<run_id>/save/`
- Trip assets:
  - `GET /api/trip-plans/`
  - `GET /api/trip-plans/<plan_id>/`
  - `POST /api/trip-plans/<plan_id>/resume/`
- Legacy compatibility planning/chat:
  - existing `/api/chat/...` endpoints remain available as compatibility paths
    while the new frontend uses the split assistant/workbench experience

## Testing

- Backend tests live in `backend/tests/`.
- Frontend tests live in `frotend/tests/`.
- Install project dependencies before running either test suite.
- Frontend verification for the current split-domain change should cover:
  - dual-entry shell copy and navigation
  - standalone assistant conversations
  - structured workbench submission and direct plan saving
  - source-type display in plan assets
