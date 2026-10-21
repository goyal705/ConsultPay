# ConsultPay – Wallet based per-minute session billing

Django + DRF backend for paid 1:1 consultations. Users keep a prepaid wallet, book a session with a provider, and get charged every minute while the session is running. When the wallet can't pay for the next minute, the system ends the session.

A small Jinja2 frontend is included so the whole flow can be clicked through in the browser (recharge, mock payment callback, booking, accept/start/end, live billing).

**Stack:** Python 3.11, Django 5.2, Django REST Framework, PostgreSQL (SQLite locally), Jinja2, Gunicorn + WhiteNoise.

## Setup

```bash
git clone <repo-url>
cd consultpay
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000, register one **Provider** account (with a per-minute rate) and one **User** account.

SQLite is used by default. To use Postgres set `DATABASE_URL`, e.g.

```bash
export DATABASE_URL=postgres://user:password@localhost:5432/consultpay
```

Other env vars are listed in `.env.example`.

## Running tests

```bash
python manage.py test
```

31 tests. The required scenarios live in:

| Scenario | Test |
|---|---|
| Insufficient balance to start | `consultations.tests.InsufficientBalanceToStartTests` |
| Happy path (recharge → create → accept → start → 2 min billing → end) | `consultations.tests.HappyPathTests.test_full_flow_bills_two_minutes` |
| Balance runs out | `consultations.tests.BalanceRunsOutTests` |
| Invalid state transition → 400 | `consultations.tests.InvalidTransitionTests` |
| Duplicate recharge callback | `wallet.tests.RechargeTests.test_duplicate_success_callback_credits_once` |
| Duplicate billing | `consultations.tests.DuplicateBillingTests` |

Instead of mocking the clock, tests move `started_at` back in time (or pass `now=` to the service) to simulate elapsed minutes.

## Session state machine

```mermaid
stateDiagram-v2
    [*] --> unassigned: create
    unassigned --> assigned: assign (user picks provider)
    assigned --> accepted_by_provider: accept (provider)
    accepted_by_provider --> in_progress: start (user, needs 5 x rate in wallet)
    in_progress --> completed: end (user / provider)
    in_progress --> completed: bill → balance can't cover next minute (system)
    unassigned --> cancelled: cancel
    assigned --> cancelled: cancel
    accepted_by_provider --> cancelled: cancel
    completed --> [*]
    cancelled --> [*]
```

Anything not in the diagram returns **400** with a message like `Cannot end a session that is 'accepted_by_provider'.` Acting on a session you're not part of (or with the wrong role) returns **403**.

## ER diagram

```mermaid
erDiagram
    USER ||--|| WALLET : has
    USER ||--o{ RECHARGE : makes
    WALLET ||--o{ WALLET_TRANSACTION : ledger
    USER ||--o{ CONSULTATION_SESSION : books
    USER ||--o{ CONSULTATION_SESSION : "provides"

    USER {
        string username
        string role "USER | PROVIDER"
        decimal rate_per_minute "providers only"
    }
    WALLET {
        decimal balance "CHECK >= 0"
    }
    WALLET_TRANSACTION {
        string kind "credit | debit"
        decimal amount
        decimal balance_after
        string reference "UNIQUE"
    }
    RECHARGE {
        decimal amount
        string reference "UNIQUE"
        string status "pending | success | failed"
    }
    CONSULTATION_SESSION {
        string status
        decimal rate_per_minute "locked at start"
        datetime started_at
        datetime ended_at
        int billed_minutes
        decimal billed_amount
        int talk_seconds
        string ended_by "user | provider | system"
        string end_reason
    }
```

## API

Auth is DRF token auth: `Authorization: Token <key>`.

| Method | URL | Who | Notes |
|---|---|---|---|
| POST | `/api/auth/register/` | anyone | `username, password, role, rate_per_minute` → returns token |
| POST | `/api/auth/token/` | anyone | `username, password` → token |
| GET | `/api/auth/providers/` | auth | list providers and rates |
| GET | `/api/wallet/` | auth | balance + last 20 ledger entries |
| GET/POST | `/api/wallet/recharges/` | auth | POST `amount` creates a `pending` recharge |
| POST | `/api/wallet/recharges/callback/` | gateway (no auth) | `reference, status=success|failed` |
| GET/POST | `/api/sessions/` | user | POST optional `provider_id` (if given, session is assigned right away) |
| GET | `/api/sessions/<id>/` | participant | |
| POST | `/api/sessions/<id>/assign/` | user | `provider_id` |
| POST | `/api/sessions/<id>/accept/` | provider | |
| POST | `/api/sessions/<id>/start/` | user | |
| POST | `/api/sessions/<id>/end/` | user / provider | |
| POST | `/api/sessions/<id>/cancel/` | user / provider | optional `reason` |
| POST | `/api/sessions/<id>/bill/` | participant | charge all fully elapsed, unbilled minutes |

If `RECHARGE_WEBHOOK_SECRET` is set, the callback must send it in the `X-Webhook-Secret` header.

Quick curl run:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/token/ -d username=alice -d password=secret123 | jq -r .token)
REF=$(curl -s -X POST localhost:8000/api/wallet/recharges/ -H "Authorization: Token $TOKEN" -d amount=500 | jq -r .reference)
curl -X POST localhost:8000/api/wallet/recharges/callback/ -d reference=$REF -d status=success
curl -X POST localhost:8000/api/wallet/recharges/callback/ -d reference=$REF -d status=success   # applied: false
```

## Billing

Billing is synchronous and can be triggered three ways:

- `POST /api/sessions/<id>/bill/`
- the session page in the UI calls the bill endpoint every 15 seconds while the session is running
- `python manage.py bill_sessions` bills every in-progress session (`--interval 30` keeps it running, handy as a Render worker or cron job)

Each call works out `completed_minutes = floor((now - started_at) / 60)` and charges minutes `billed_minutes + 1 … completed_minutes`, one at a time. After charging, if the remaining balance is less than one minute's rate, the session is ended by the system with reason `Insufficient balance`.

Example from the brief: rate ₹50, wallet ₹290 at start → after 5 minutes ₹250 is billed, ₹40 left, the next minute can't be paid → session completed, `ended_by=system`, wallet stays ₹40.

## Implementation notes

- **State machine in one place.** `consultations/services.py` has a `TRANSITIONS` table (`action → allowed from-states, to-state`). Every action checks it before doing anything, so views stay thin and the same rules apply to the API, the UI and the management command.
- **Row locking.** Every state change and billing run happens inside `transaction.atomic()` with `select_for_update()` on the session and then the wallet (always in that order, so no lock cycles). Two concurrent bill calls simply run one after another and the second sees the minutes already billed.
- **No negative balance.** `debit()` refuses to go below zero, and there's also a DB `CHECK (balance >= 0)` as a backstop.
- **Duplicate minutes can't be charged.** `billed_minutes` is the high-water mark, and every debit writes a ledger row with reference `session:<id>:minute:<n>`, which is `UNIQUE`. Even a bug in the counter couldn't charge the same minute twice.
- **Idempotent recharge callback.** The recharge row is locked; only a `pending` recharge can move to `success`/`failed`. Repeat callbacks return `applied: false` and do nothing. The credit also uses a unique ledger reference `recharge:<ref>`.
- **Rate is locked at start.** `rate_per_minute` is copied from the provider when the session starts, so changing the provider's rate later doesn't affect a running session.
- **One active session per user.** Checked when starting and enforced with a partial unique index on `(user) WHERE status = 'in_progress'`.
- **Minimum balance.** Starting needs `5 × rate` in the wallet (`MIN_BALANCE_MINUTES` in settings).
- **Partial minutes are free.** Only fully elapsed minutes are billed. Ending at 2m40s charges 2 minutes. Actual talk time is still saved in `talk_seconds`.
- **Ending a session bills first.** `end` charges any remaining completed minutes before closing. If the wallet can't pay for them, the session is recorded as ended by the system.
- **Ledger.** Every credit/debit is a `WalletTransaction` with `balance_after`, so the balance can always be explained.
- Cancellation (`cancelled`) is allowed by either participant any time before the session starts.

## Deploying on Render

The repo has a Render Blueprint (`render.yaml`) that creates a Postgres database and the web service, plus `build.sh` for the build step.

1. Push the repo to GitHub.
2. On Render: **New → Blueprint**, connect the repo and click **Apply**.
3. That's it. Render creates the `consultpay-db` database, wires `DATABASE_URL`, generates `SECRET_KEY`, and runs `build.sh` (install, `collectstatic`, `migrate`) followed by gunicorn. Health check is `/healthz`.

`DEBUG` defaults to `false` on Render, and the `*.onrender.com` hostname is picked up from `RENDER_EXTERNAL_HOSTNAME` for `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`. For a custom domain, add it to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (with `https://`).

Manual setup without the Blueprint: create a Postgres instance, then a Python web service with build command `./build.sh`, start command `gunicorn config.wsgi --bind 0.0.0.0:$PORT`, and env vars `DATABASE_URL` (internal URL of the database), `SECRET_KEY`, `PYTHON_VERSION=3.11.9`.

Notes:
- Free web services sleep after inactivity, so the first request can take ~30-60s.
- Free Postgres databases on Render expire after 30 days.
- For billing without the session page open, add a Render Cron Job running `python manage.py bill_sessions` (paid plans) or a background worker running `python manage.py bill_sessions --interval 30`.

## Project layout

```
config/          settings, urls, jinja2 environment
accounts/        custom User with USER / PROVIDER role, register + token endpoints
wallet/          Wallet, WalletTransaction (ledger), Recharge, credit/debit services
consultations/   ConsultationSession, state machine + billing services, API, bill_sessions command
web/             Jinja2 views for the browser UI
templates/       Jinja2 templates
static/          css
```
