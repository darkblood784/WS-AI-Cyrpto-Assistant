# WSAI API Contract (v1)

This document defines the canonical API paths and supported compatibility aliases.

## Auth

- Canonical:
  - `POST /auth/register`
  - `POST /auth/login`
  - `POST /auth/verify`
  - `POST /auth/verify-login`
  - `POST /auth/resend-verification`
  - `GET /auth/me`
- Alias:
  - `GET /me` -> same response as `GET /auth/me`

## Plans and Entitlements

- `GET /plans`
- `GET /entitlements`
  - Includes:
    - `plan_id`, `plan_code`, `plan_name`
    - `limits`:
      - `daily_messages_limit`
      - `monthly_messages_limit`
      - `per_minute_messages_limit`
      - `context_messages_limit`
      - `context_chars_limit`
    - `features`:
      - `chat_basic`
      - `indicators_basic`
      - `indicators_advanced`
      - `strategy_builder`
      - `exports`
      - `alerts`
      - `long_term_memory`
- `GET /usage`

## Chat

- `POST /chat`
- `POST /strategy` (compat route for strategy mode)
- `GET /chat/summary`
- `POST /chat/summary`

## Threads

- Canonical:
  - `POST /threads`
  - `GET /threads`
  - `GET /threads/{thread_id}`
  - `PATCH /threads/{thread_id}`
  - `DELETE /threads/{thread_id}`
- Aliases (supported for frontend compatibility):
  - `POST /chat/threads`
  - `GET /chat/threads`
  - `GET /chat/threads/{thread_id}`
  - `PATCH /chat/threads/{thread_id}`
  - `DELETE /chat/threads/{thread_id}`

## Admin

- `GET /admin/users`
- `GET /admin/users/{user_id}`
- `PATCH /admin/users/{user_id}`
- `POST /admin/users/{user_id}/verify-email`
- `GET /admin/audit`
