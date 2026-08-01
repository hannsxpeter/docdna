from django.urls import path

from ledger import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("v1/accounts", views.account_list, name="account-list"),
    path("v1/accounts/<uuid:account_id>", views.account_detail, name="account-detail"),
    path("v1/accounts/<uuid:account_id>/balance", views.account_balance, name="account-balance"),
    path("v1/accounts/<uuid:account_id>/entries", views.account_entries, name="account-entries"),
    path("v1/journals", views.journal_list, name="journal-list"),
    path("v1/journals/<uuid:journal_id>", views.journal_detail, name="journal-detail"),
    path("v1/journals/<uuid:journal_id>/post", views.journal_post, name="journal-post"),
    path("v1/journals/<uuid:journal_id>/reverse", views.journal_reverse, name="journal-reverse"),
    path("v1/transfers", views.transfer_list, name="transfer-list"),
    path("v1/transfers/<uuid:transfer_id>", views.transfer_detail, name="transfer-detail"),
    path("v1/reconciliations", views.reconciliation_list, name="reconciliation-list"),
    path("v1/reconciliations/latest", views.reconciliation_latest, name="reconciliation-latest"),
    path("v1/statements", views.statement_list, name="statement-list"),
    path("v1/statements/<str:period>", views.statement_detail, name="statement-detail"),
    path("v1/webhooks/replay", views.webhook_replay, name="webhook-replay"),
]
