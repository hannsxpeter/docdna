from django.http import JsonResponse


def healthz(request):
    return JsonResponse({"status": "ok"})


def readyz(request):
    return JsonResponse({"status": "ready"})


def account_list(request):
    return JsonResponse({"accounts": []})


def account_detail(request, account_id):
    return JsonResponse({"id": str(account_id)})


def account_balance(request, account_id):
    return JsonResponse({"id": str(account_id), "balance_minor": 0})


def account_entries(request, account_id):
    return JsonResponse({"id": str(account_id), "entries": []})


def journal_list(request):
    return JsonResponse({"journals": []})


def journal_detail(request, journal_id):
    return JsonResponse({"id": str(journal_id)})


def journal_post(request, journal_id):
    return JsonResponse({"id": str(journal_id), "posted": True})


def journal_reverse(request, journal_id):
    return JsonResponse({"id": str(journal_id), "reversed": True})


def transfer_list(request):
    return JsonResponse({"transfers": []})


def transfer_detail(request, transfer_id):
    return JsonResponse({"id": str(transfer_id)})


def reconciliation_list(request):
    return JsonResponse({"reconciliations": []})


def reconciliation_latest(request):
    return JsonResponse({"reconciliation": None})


def statement_list(request):
    return JsonResponse({"statements": []})


def statement_detail(request, period):
    return JsonResponse({"period": period})


def webhook_replay(request):
    return JsonResponse({"replayed": 0})
