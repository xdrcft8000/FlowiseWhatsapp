from fastapi import FastAPI, Request, HTTPException, Query
from pydantic import BaseModel
import httpx
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re
import time
import logging
from fastapi.responses import Response

# from dotenv import load_dotenv
# load_dotenv()

app = FastAPI()


WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")
GRAPH_API_TOKEN = os.getenv("GRAPH_API_TOKEN")

service_account_info = {
    "type": os.getenv("google_type"),
    "project_id": os.getenv("google_project_id"),
    "private_key_id": os.getenv("google_private_key_id"),
    "private_key": os.getenv("google_private_key").replace('\\n', '\n').replace('"', ''),
    "client_email": os.getenv("google_client_email"),
    "client_id": os.getenv("google_client_id"),
    "auth_uri": os.getenv("google_auth_uri"),
    "token_uri": os.getenv("google_token_uri"),
    "auth_provider_x509_cert_url": os.getenv("google_auth_provider_x509_cert_url"),
    "client_x509_cert_url": os.getenv("google_client_x509_cert_url"),
}
logging.info(service_account_info)
credentials = service_account.Credentials.from_service_account_info(service_account_info)
drive_service = build('drive', 'v3', credentials=credentials)

def extract_folder_id_from_url(folder_url: str) -> str:
    match = re.search(r'[-\w]{25,}', folder_url)
    return match.group(0) if match else None

@app.post("/gdrive/webhook")
async def drive_webhook(request: Request):
    body = await request.json()
    logging.info('Webhook received:', body)
    if body.get("resourceId"):
        print('Change detected in resource ID:', body["resourceId"])
    return {"status": "received"}

class SetupWatchRequest(BaseModel):
    folder_url: str

@app.post("/gdrive/setup-watch")
async def setup_watch(data: SetupWatchRequest):
    folder_id = extract_folder_id_from_url(data.folder_url)

    if not folder_id:
        raise HTTPException(status_code=400, detail="Invalid folder_url provided")

    logging.info('Setting up watch for folder:', data.folder_url)
    try:
        watch_response = drive_service.files().watch(
            fileId=folder_id,
            body={
                "id": f"drive-watch-{int(time.time())}",
                "type": "web_hook",
                "address": "https://whatsappai-f2f3.onrender.com/fo/api/gdrive/webhook",
            },
        ).execute()

        print('Watch setup successfully:', watch_response)
        return {"message": "Watch setup successfully", "data": watch_response}
    except Exception as e:
        print('Error setting up watch:', str(e))
        raise HTTPException(status_code=500, detail="Error setting up watch")

@app.post("/whatsapp/webhook")
async def webhook(request: Request):
    body = await request.json()
    print("Incoming webhook message:", body)

    message = body.get("entry", [])[0].get("changes", [])[0].get("value", {}).get("messages", [])[0]
    
    if message and message.get("type") == "text":
        business_phone_number_id = body["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
        prompt = {"question": message["text"]["body"]}

        try:
            flowise_response = await httpx.post(
                "https://whatsappai-f2f3.onrender.com/api/v1/prediction/17bbeae4-f50b-43ca-8eb0-2aeea69d5359",
                json=prompt,
                headers={"Content-Type": "application/json"},
            )

            response_text = f"Here's a joke about '{message['text']['body']}': {flowise_response.json()['text']}"

            await httpx.post(
                f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages",
                headers={"Authorization": f"Bearer {GRAPH_API_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": message["from"],
                    "text": {"body": response_text},
                    "context": {"message_id": message["id"]},
                }
            )

            await httpx.post(
                f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages",
                headers={"Authorization": f"Bearer {GRAPH_API_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": message["id"],
                }
            )
        except Exception as e:
            print("Error querying the API:", str(e))
            raise HTTPException(status_code=500, detail="Error querying the API")

    return {"status": "success"}

@app.get("/whatsapp/webhook")
async def verify_webhook(request: Request):
    logging.info('Verifying webhook', WEBHOOK_VERIFY_TOKEN)
    print('Verifying webhook', WEBHOOK_VERIFY_TOKEN)
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        print("Webhook verified successfully!")
        print('returning challenge:', challenge)
        res = Response(content=challenge, media_type="text/plain")
        print(res.body)
        return res
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    

@app.get("/")
async def root():
    return {"message": "Nothing to see here. Checkout README.md to start."}

