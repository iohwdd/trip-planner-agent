# Trip Planner Backend

This backend uses Django as the HTTP layer and keeps the planning core on
LangChain + LangGraph. The backend now includes:

- MySQL-ready persistence with local MySQL defaults and SQLite fallback for local tests
- Redis-backed cache support with in-memory fallback for local development
- Redis-backed email-code authentication and opaque access/refresh tokens
- guest session ownership and guest-to-user asset migration
- persistent chat sessions, turns, trip plan versions, and planning jobs
- a Redis-backed planning queue with database-persisted job state and fallback polling
- Qwen `qwen3.5-plus` access via DashScope-compatible API
- Amap and Baidu live-data integrations with degraded fallback paths

Qwen is configured in non-thinking mode by default to keep the core planning
path responsive. If you need deeper reasoning and can tolerate higher latency,
set `QWEN_ENABLE_THINKING=true`.

## Development

1. Install dependencies in `backend/`.
2. Copy `.env.example` to `.env`.
3. Choose a database:
   - local fallback: keep `USE_MYSQL=false`
   - MySQL: set `USE_MYSQL=true` and fill `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`
   - default local host is `localhost`
   - local MySQL on macOS can use `MYSQL_UNIX_SOCKET=/tmp/mysql.sock`
4. Optional shared cache:
   - set `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DATABASE`
   - local default is `localhost:6379` with no password
   - if unset, provider cache and auth/session state both fall back to in-process memory cache
   - if set, planning jobs are also pushed through Redis instead of relying on DB polling
5. Configure email-code delivery:
   - default backend is SMTP, no longer the console mock backend
   - for QQ mail, set `DJANGO_EMAIL_HOST=smtp.qq.com`
   - recommended QQ config is `DJANGO_EMAIL_PORT=465` and `DJANGO_EMAIL_USE_SSL=true`
   - set `DJANGO_EMAIL_HOST_USER` to the full mailbox address, for example `2023321332@qq.com`
   - set `DJANGO_EMAIL_HOST_PASSWORD` to the QQ mailbox authorization code, not the QQ login password
   - `DJANGO_DEFAULT_FROM_EMAIL` should usually match the sender mailbox
6. Provide provider credentials as needed:
   - `DASHSCOPE_API_KEY`
   - `AMAP_API_KEY`
   - `BAIDU_MAPS_API_KEY`
7. Run migrations:
   - `python manage.py migrate`
8. Start the API server:
   - `python manage.py runserver 127.0.0.1:8001`
9. For queued execution outside the API process:
   - set `TRIP_PLANNER_INLINE_JOBS=false`
   - run `python manage.py run_planning_worker`

The remote MySQL target for this project uses database name `trip_assistant`.
Keep credentials in environment variables only.

## API overview

- `POST /api/auth/codes/`: request an email login code
- `POST /api/auth/login/verify/`: verify the code and receive Redis-backed access/refresh tokens
- `POST /api/auth/login/password/`: login with email + password
- `GET /api/auth/me/`: fetch current login state, current capabilities, and asset summary counts
- `POST /api/auth/password/`: set or update the current user's password
- `POST /api/auth/logout/`: invalidate the refresh token
- `POST /api/plans/`: compatibility endpoint for one-shot planning
- `GET /api/plans/<run_id>/`: poll one-shot planning status
- `GET /api/chat/sessions/`: list owned sessions with total count, status counts, and recent session id
- `POST /api/chat/sessions/`: create a chat session
- `GET /api/chat/sessions/recent/`: restore the most recent session
- `GET /api/chat/sessions/<session_id>/`: inspect session state, messages, latest result, and confirmed constraints
- `PATCH /api/chat/sessions/<session_id>/`: rename a session
- `DELETE /api/chat/sessions/<session_id>/`: delete a session
- `POST /api/chat/sessions/<session_id>/messages/`: submit a free-text chat message or structured form request
- `POST /api/chat/sessions/<session_id>/messages/stream/`: submit a chat turn and consume incremental SSE events for status, steps, partial result, and final reply
- `GET /api/chat/sessions/<session_id>/turns/<turn_id>/`: poll a chat turn and its execution steps
- `POST /api/chat/sessions/<session_id>/plans/`: save the current result as a draft or final plan
- `GET /api/trip-plans/`: list saved plans with total count and status counts
- `GET /api/trip-plans/<plan_id>/`: fetch a saved plan snapshot
- `DELETE /api/trip-plans/<plan_id>/`: delete a saved plan
- `POST /api/trip-plans/<plan_id>/resume/`: create a new editable session from a saved plan

## Configuration notes

- `AMAP_API_KEY` is used for both POI search and route-leg estimation.
- If `REDIS_HOST` is configured, Django cache, auth/session state, provider response cache, and planning-job queueing all use Redis.
- If direction requests fail or coordinates are missing, the backend still returns
  route legs marked as estimated via the `heuristic-route` source.
- Stream events use a shared phase vocabulary (`queued`, `running`, `clarification`, `partial`, `completed`, `failed`) so the frontend can render a stable multi-stage UI.
- `TRIP_PLANNER_INLINE_JOBS=true` is convenient for local debugging. For a more
  production-like path, disable it and run the worker command separately.
- Auth codes, login sessions, analytics events, and queued job ids are short-lived
  cache / Redis records, which keeps MySQL focused on durable assets instead of transient state.
- Password login reuses Django's built-in password hash on `planner_user`; there is no extra token table in MySQL.
- MySQL 8 `caching_sha2_password` works through `PyMySQL + cryptography`; for local Homebrew MySQL, socket access is often more reliable than TCP.
- Auth codes are protected by TTL, send-rate limits, per-IP window limits, and
  max verification attempts.
- Guest users can create sessions before login. After successful verification,
  guest sessions and related queued assets are migrated to the authenticated user.

## Testing

- `python manage.py test -v 2 --settings=trip_planner_backend.test_settings`
- `python -m pytest tests -q --ds=trip_planner_backend.test_settings`
