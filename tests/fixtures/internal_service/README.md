# ledger-service

Internal double-entry ledger for the payments platform. Django on PostgreSQL, deployed to the
platform team's PaaS account.

## Running it locally

```sh
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The service listens on port 8000 by default.

## Layout

- `config/urls.py` registers every route the service exposes.
- `ops/alerts.yml` holds the alert rules the monitoring stack loads.
- `docs/api.md` describes the public endpoints.

## On-call

Paging is configured in `.pagerduty.yml`. Escalation goes to the payments primary rotation.
