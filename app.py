# app.py
import os
import json
import logging
from flask import Flask, jsonify
# If you are testing locally, ensure you have 'python-dotenv' installed and uncomment the next line:
# from dotenv import load_dotenv 
from azure.identity import ClientSecretCredential
from azure.mgmt.costmanagement import CostManagementClient
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage

# load_dotenv() # Uncomment this line if you need to load .env variables locally

# --- Configuration and Initialization ---

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load environment variables (App Service or local shell will provide these)
TENANT_ID = os.environ.get("TENANT_ID")
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
SUBSCRIPTION_ID = os.environ.get("SUBSCRIPTION_ID")

EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD") # Use App Password for Gmail
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")
THRESHOLD = float(os.environ.get("THRESHOLD", 5.0)) # Default threshold is $5.00

# --- Azure Authentication and API Client ---

# Authenticate with Azure AD
try:
    credential = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    cost_client = CostManagementClient(credential)
    logger.info("Azure AD ClientSecretCredential established.")
except Exception as e:
    logger.error(f"Error establishing Azure Credential: {e}. Check TENANT/CLIENT IDs.")
    cost_client = None 

# --- Functions ---

def send_alert(cost):
    """Sends an email alert using SMTP. Returns True on success, False on failure."""
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        logger.warning("Email credentials missing. Cannot send alert.")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"🚨 Cost Anomaly Alert! Azure Cost: ${cost:.2f}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    body = f"""
    The Azure Month-To-Date cost for subscription '{SUBSCRIPTION_ID}' has exceeded the set threshold.
    
    Current Total Cost: ${cost:.2f}
    Configured Threshold: ${THRESHOLD:.2f}
    
    Action required: Check resource usage and identify cost contributors.
    """
    msg.set_content(body)

    try:
        # Use port 465 for SSL/TLS (Gmail SMTP)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        logger.info(f"Alert Email Sent successfully to {EMAIL_RECEIVER}. Current cost: ${cost:.2f}")
        return True
    except Exception as e:
        # Log the detailed SMTP error for debugging (e.g., authentication failure)
        logger.error(f"Failed to send email alert. Check sender/password/2FA settings: {e}")
        return False

def get_current_cost():
    """Fetches the latest cost data from Azure Cost Management API."""
    if not cost_client or not SUBSCRIPTION_ID:
        logger.error("Cost client or Subscription ID is not configured.")
        return 0.0, "USD" 

    # Define the time frame for Month-to-Date cost (MTD)
    today = datetime.now().date()
    first_day_of_month = today.replace(day=1)

    query_definition = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {
            "from": first_day_of_month.isoformat() + "T00:00:00Z",
            "to": (today + timedelta(days=1)).isoformat() + "T00:00:00Z" 
        },
        "dataset": {
            "granularity": "None", 
            "aggregation": {
                "totalCost": {
                    "name": "Cost",
                    "function": "Sum"
                }
            }
        }
    }

    try:
        # Querying usage for the entire subscription scope
        result = cost_client.query.usage(
            scope=f"/subscriptions/{SUBSCRIPTION_ID}",
            parameters=query_definition
        )

        if result.rows and result.rows[0]:
            total_cost = float(result.rows[0][0])
            currency = result.rows[0][1]
            return total_cost, currency
        
        logger.warning("Azure Cost Management returned no rows.")
        return 0.0, "USD" 
    
    except Exception as e:
        logger.error(f"Error fetching Azure cost: {e}. Check credentials and role assignment.")
        # Return 0.0 with the API error in the currency field for display
        return 0.0, f"API Error: {str(e)}" 

# --- Flask Routes ---

@app.route("/")
def home():
    """Main dashboard route. Fetches cost and triggers alert check."""
    cost, currency = get_current_cost()
    alert_triggered_status = False
    
    # Check if cost exceeds the threshold
    threshold_breached = cost > THRESHOLD

    if threshold_breached:
        logger.info(f"Threshold breached! Cost: ${cost:.2f} > Threshold: ${THRESHOLD:.2f}. Attempting to send alert...")
        # Call send_alert and capture its return value (True/False)
        alert_triggered_status = send_alert(cost) 
    else:
        logger.info(f"Cost is below threshold. Cost: ${cost:.2f} | Threshold: ${THRESHOLD:.2f}")

    return jsonify({
        "status": "Running",
        "current_cost_mtd": f"{currency} {cost:.2f}",
        "cost_value": cost,
        "threshold_usd": THRESHOLD,
        # This now reports the success/failure status of the attempted alert
        "alert_triggered_now": alert_triggered_status, 
        "threshold_breached": threshold_breached,
        "last_checked_utc": datetime.utcnow().isoformat() + "Z",
        "scope": f"Subscription: {SUBSCRIPTION_ID}"
    })

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8000)