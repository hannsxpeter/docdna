# Ledger API

The service exposes 11 endpoints under `/v1`. Every request needs the internal service token
in the `X-Service-Token` header.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/v1/accounts` | List accounts |
| GET | `/v1/accounts/{id}` | Fetch one account |
| GET | `/v1/accounts/{id}/balance` | Current balance in minor units |
| GET | `/v1/journals` | List journals |
| POST | `/v1/journals` | Create a journal |
| GET | `/v1/journals/{id}` | Fetch one journal |
| POST | `/v1/journals/{id}/post` | Post a journal |
| GET | `/v1/transfers` | List transfers |
| GET | `/v1/transfers/{id}` | Fetch one transfer |
| GET | `/v1/reconciliations` | List reconciliation runs |
| GET | `/v1/statements` | List statements |

Routing lives in `config/urls.py` and the handlers in `ledger/views.py`.
