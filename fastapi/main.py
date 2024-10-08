import asyncio
from fastapi import FastAPI, Header, Request, HTTPException, Query
import httpx
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re
import time
import logging
from fastapi.responses import JSONResponse, Response
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, RootModel
from supabase import create_client, Client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

class Text(BaseModel):
    body: str

class Audio(BaseModel):
    id: str
    mime_type: str

class Message(BaseModel):
    from_: Optional[str] = Field(None, alias='from')
    id: Optional[str] = None
    timestamp: Optional[str] = None
    text: Optional[Text] = None
    type: Optional[str] = None
    audio: Optional[Audio] = None


class Profile(BaseModel):
    name: str

class Contact(BaseModel):
    profile: Profile
    wa_id: str

class Metadata(BaseModel):
    display_phone_number: str
    phone_number_id: str

class Value(BaseModel):
    messaging_product: str
    metadata: Metadata
    contacts: List[Contact]
    messages: List[Message]

class Change(BaseModel):
    value: Value
    field: str

class Entry(BaseModel):
    id: str
    changes: List[Change]

class WhatsAppWebhookBody(BaseModel):
    object: str
    entry: List[Entry]


class AnyRequestModel(RootModel[Dict[str, Any]]):
    pass
    
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

def extract_folder_id_from_url(folder_url: str) -> str:
    match = re.search(r'[-\w]{25,}', folder_url)
    return match.group(0) if match else None

def init_drive_service():
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    return build('drive', 'v3', credentials=credentials)



@app.post('/db/insert')
async def insert_data(request: Request):
    print('Inserting data')
    logging.info('Inserting data')
    try:
        request = await request.json()
        print(request)
        table = request['table']
        data = request['data']
        print('Table:', table)
        print('title:', data)
    except Exception as e:
        print('Error:', str(e))
        return JSONResponse(content={"status": "error"}, status_code=500)
    if not table or not data:
        return JSONResponse(content={"status": "error"}, status_code=400)
    try:
        response = supabase.table(table).insert(data).execute()
        print('Response:', response)
        return JSONResponse(content={"status": "success", "data": response.data}, status_code=200)
    except Exception as e:
        print('Error:', str(e))
        return JSONResponse(content={"status": "error"}, status_code=500)



@app.post("/gdrive/webhook")
async def drive_webhook(
    request: Request,
):
    state = request.headers.get("X-Goog-Resource-State")
    drive = init_drive_service()
    if state != "sync":
        print(f'drive webhook {state} notification')
        folder = extract_folder_id_from_url(request.headers.get("X-Goog-resource-uri"))
        print('Folder:', folder)
        folder_id = request.headers.get("X-Goog-Resource-Id")
        print('Folder ID:', folder_id)
                                            
        try:
            print(request.headers)
            if state == "update":
                print('Update notification')
            elif state == "add":
                print('Add notification')
            elif state == "trash":
                print('Trash notification')
            elif state == "untrash":
                print('Untrash notification')
            elif state == "delete":
                print('Delete notification')
            elif state == "change":
                print('Change notification')
            print('the channel expires:', request.headers.get("X-Goog-Channel-Expiration"))
            try:
                query = f"'{folder}' in parents"
                allFiles = drive.files().list(q=query).execute()
                for file in allFiles.get("files", []):
                    print(f'Found file: {file.get("name")}, {file.get("id")}', {file.get("mimeType")})

            except Exception as e:
                print('Error listing files:', str(e))
            return {"status": "received"}
        except Exception as e:
            print('Error:', str(e))
            return JSONResponse(content={"status": "error"}, status_code=500)
    else:
        print('drive webhook SYNC notification')
        try:
            print(request.headers)
            return {"status": "received"}
        except Exception as e:
            print('Error:', str(e))
            return JSONResponse(content={"status": "error"}, status_code=500)
    

class SetupWatchRequest(BaseModel):
    folder_url: str

@app.post("/gdrive/setup-watch")
async def setup_watch(data: SetupWatchRequest):
    folder_id = extract_folder_id_from_url(data.folder_url)
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    drive_service = build('drive', 'v3', credentials=credentials)

    if not folder_id:
        raise HTTPException(status_code=400, detail="Invalid folder_url provided")

    print('Setting up watch for folder:', data.folder_url)
    try:
        watch_response = drive_service.files().watch(
            fileId=folder_id,
            body={
                "id": f"drive-watch-{int(time.time())}",
                "type": "web_hook",
                "address": "https://whatsappai-f2f3.onrender.com/fo/api/gdrive/webhook",
                "token": "1234",
            },
        ).execute()

        print('Watch setup successfully:', watch_response)
        return {"message": "Watch setup successfully", "data": watch_response}
    except Exception as e:
        print('Error setting up watch:', str(e))
        raise HTTPException(status_code=500, detail="Error setting up watch")





@app.post("/whatsapp/webhook")
async def webhook(body: WhatsAppWebhookBody):
    print('webhook post')
    # Attempt to read the Request
    print(body)
    try:
        message = body.entry[0].changes[0].value.messages[0]
    except IndexError:
        raise HTTPException(status_code=400, detail="Invalid message structure")

    if message.type == "text":
        business_phone_number_id = body.entry[0].changes[0].value.metadata.phone_number_id
        prompt = {"question": message.text.body}
        print(f"Received message: {message.text.body}")
        try:
            # Use an async client to make HTTP requests
            async with httpx.AsyncClient() as client:
                # Call to external service
                response = await client.post(
                    "https://whatsappai-f2f3.onrender.com/api/v1/prediction/18448d70-e618-4656-a1d0-45f1902e598d",
                    json=prompt,
                    headers={"Content-Type": "application/json"},
                )
                print(f"Response status: {response.status_code}")
                print(f"Response content: {response.text}")
                flowise_data = response.json()
                # Send a reply to the user
                await client.post(
                    f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {GRAPH_API_TOKEN}"},
                    json={
                        "messaging_product": "whatsapp",
                        "to": message.from_,
                        "text": {"body": f"{flowise_data['text']}"},
                        "context": {"message_id": message.id},
                    }
                )

                # Mark the incoming message as read
                await client.post(
                    f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {GRAPH_API_TOKEN}"},
                    json={
                        "messaging_product": "whatsapp",
                        "status": "read",
                        "message_id": message.id,
                    }
                )

        except Exception as e:
            print("Error querying the API:", str(e))
            raise HTTPException(status_code=500, detail="Error querying the API")

    return {"status": "success"}

@app.get("/whatsapp/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        print("Webhook verified successfully!")
        res = Response(content=challenge, media_type="text/plain")
        return res
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    








# ++++++++++++++++++++++++++++++
# ++++++++++ MOODIFY ++++++++++
# ++++++++++++++++++++++++++++++

from openai import OpenAI
from pydub import AudioSegment
from io import BytesIO


MOODIFY_WEBHOOK_VERIFY_TOKEN = os.getenv("MOODIFY_WEBHOOK_VERIFY_TOKEN")
MOODIFY_WHATSAPP_GRAPH_API_TOKEN = os.getenv("MOODIFY_WHATSAPP_GRAPH_API_TOKEN")


def init_openai():
    return OpenAI(os.getenv("MOODIFY_OPENAI_API_KEY"))


#  SPEECH TO TEXT:
# The best way to do this is to use a service that supports OGG
# Current implementation is quicker but not the best way to do it

def convert_ogg_to_wav(ogg_data: bytes) -> BytesIO:
    print('Converting OGG to WAV')
    try:
        audio = AudioSegment.from_file(BytesIO(ogg_data), format="ogg")
        wav_data = BytesIO()
        audio.export(wav_data, format="wav")
        wav_data.seek(0)
        return wav_data
    except Exception as e:
        print("Error converting OGG to WAV:", str(e))
        return None

# Send to OpenAI's API
async def transcribe_audio(ogg_file: bytes):
    print('Transcribing audio')
    try:
        openai = init_openai()
        wav_data = convert_ogg_to_wav(ogg_file)
        response = openai.audio.transcriptions.create(
            model="whisper-1",
            file=wav_data,
            response_format="text"
        )
        print('transcription:', response.text)
        return response.text
    except Exception as e:
        print("Error transcribing audio:", str(e))
        return None



@app.get("/moodify/whatsapp/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == MOODIFY_WEBHOOK_VERIFY_TOKEN:
        print("Webhook verified successfully!")
        res = Response(content=challenge, media_type="text/plain")
        return res
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/moodify/whatsapp/webhook")
async def webhook(body: WhatsAppWebhookBody):
    print('webhook post')
    # Attempt to read the Request
    print(body)
    try:
        message = body.entry[0].changes[0].value.messages[0]
    except IndexError:
        raise HTTPException(status_code=400, detail="Invalid message structure")

    if message.type == "text":
        business_phone_number_id = body.entry[0].changes[0].value.metadata.phone_number_id
        prompt = {"question": message.text.body}
        print(f"Received message: {message.text.body}")
        try:
            # Use an async client to make HTTP requests
            async with httpx.AsyncClient() as client:
                # Call to external service
                response = await client.post(
                    "http://localhost:10000/api/v1/prediction/17bbeae4-f50b-43ca-8eb0-2aeea69d5359",
                    json=prompt,
                    headers={"Content-Type": "application/json"},
                )
                flowise_data = response.json()
                # Send a reply to the user
                await client.post(
                    f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {MOODIFY_WHATSAPP_GRAPH_API_TOKEN}"},
                    json={
                        "messaging_product": "whatsapp",
                        "to": message.from_,
                        "text": {"body": f"Here's a joke about '{message.text.body}': {flowise_data['text']}"},
                        "context": {"message_id": message.id},
                    }
                )

                # Mark the incoming message as read
                await client.post(
                    f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {MOODIFY_WHATSAPP_GRAPH_API_TOKEN}"},
                    json={
                        "messaging_product": "whatsapp",
                        "status": "read",
                        "message_id": message.id,
                    }
                )
                return {"status": "success"}

        except Exception as e:
            print("Error querying the API:", str(e))
            raise HTTPException(status_code=500, detail="Error querying the API")
    elif message.type == "audio":
        print('Audio message')
        print(message.audio.id)
        print(message.audio.mime_type)
        try:
            # Use an async client to make HTTP requests
            async with httpx.AsyncClient() as client:
                # Call to external service
                response = await client.get(
                    f"https://graph.facebook.com/v20.0/{message.audio.id}/",
                    headers={"Authorization": f"Bearer {MOODIFY_WHATSAPP_GRAPH_API_TOKEN}"},
                )
                audio_data = response.json()
                print(audio_data)
                print(audio_data['url'])

                audio_binary_data = await client.get(
                    audio_data['url'],
                    headers={"Authorization": f"Bearer {MOODIFY_WHATSAPP_GRAPH_API_TOKEN}"},)
                print('audio_binary_data:', audio_binary_data.headers)
                print('audio_binary_data:', audio_binary_data)
                text = await transcribe_audio(audio_binary_data.content)
                print(text)
                return {"status": "success"}
        except Exception as e:
            print("Error querying the API:", str(e))
            raise HTTPException(status_code=500, detail="Error getting media location")


    else:
        print('Message type:', message.type)
        return {"status": "success"}


@app.get("/")
async def root():
    return {"message": "Nothing to see here. Checkout README.md to start."}
