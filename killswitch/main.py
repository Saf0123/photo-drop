"""Cloud Run function: when spend passes the budget, unlink billing from the project.
Triggered by the Pub/Sub topic that the Cloud Billing budget publishes to."""
import base64
import json
import os

import functions_framework
from googleapiclient import discovery


@functions_framework.cloud_event
def stop_billing(cloud_event):
    data = json.loads(base64.b64decode(cloud_event.data["message"]["data"]).decode())
    if data["costAmount"] <= data["budgetAmount"]:
        print("Under budget, nothing to do.")
        return

    project = f"projects/{os.environ['GCP_PROJECT']}"
    if os.environ.get("DRY_RUN", "false").lower() == "true":
        print(f"DRY RUN: would disable billing for {project}")
        return

    billing = discovery.build("cloudbilling", "v1", cache_discovery=False)
    if not billing.projects().getBillingInfo(name=project).execute().get("billingEnabled"):
        print("Billing already disabled.")
        return
    billing.projects().updateBillingInfo(name=project, body={"billingAccountName": ""}).execute()
    print(f"Billing disabled for {project}")
