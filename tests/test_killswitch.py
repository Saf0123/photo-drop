import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import killswitch_main as ks


def event(cost, budget):
    payload = base64.b64encode(json.dumps({"costAmount": cost, "budgetAmount": budget}).encode()).decode()
    return SimpleNamespace(data={"message": {"data": payload}})


def test_under_budget_does_nothing(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT", "p")
    build = MagicMock()
    monkeypatch.setattr(ks.discovery, "build", build)
    ks.stop_billing(event(0.5, 1.0))
    build.assert_not_called()


def test_over_budget_unlinks_billing(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT", "p")
    monkeypatch.delenv("DRY_RUN", raising=False)
    api = MagicMock()
    api.projects().getBillingInfo().execute.return_value = {"billingEnabled": True}
    monkeypatch.setattr(ks.discovery, "build", lambda *a, **k: api)
    ks.stop_billing(event(1.5, 1.0))
    api.projects().updateBillingInfo.assert_called_with(name="projects/p", body={"billingAccountName": ""})


def test_dry_run_never_unlinks(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT", "p")
    monkeypatch.setenv("DRY_RUN", "true")
    build = MagicMock()
    monkeypatch.setattr(ks.discovery, "build", build)
    ks.stop_billing(event(5, 1))
    build.assert_not_called()
