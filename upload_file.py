import os.path
import argparse
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.json.
# Using 'drive.file' scope allows the app to view and manage Google Drive files
# and folders that you have opened or created with this app.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_credentials():
    """Gets valid user credentials from file or initiates authorization flow."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        except Exception as e:
            print(f"Error loading token.json: {e}")
            creds = None

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing credentials: {e}")
                creds = None

        if not creds:
            if os.path.exists("credentials.json"):
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
            else:
                print("No credentials.json found. Attempting to use Application Default Credentials (ADC)...")
                try:
                    creds, _ = google.auth.default(scopes=SCOPES)
                except Exception as e:
                    print(f"Failed to load Application Default Credentials: {e}")
                    print("\nTo set up authentication, please do one of the following:")
                    print("1. Download OAuth 2.0 client credentials JSON from Google Cloud Console,")
                    print("   save it as 'credentials.json' in this directory, and run this script.")
                    print("2. Set up Application Default Credentials (ADC) by running:")
                    print("   gcloud auth application-default login")
                    return None
    return creds

def upload_file(file_path, folder_id=None, mime_type=None):
    """Uploads a file to Google Drive.
    
    Args:
        file_path (str): Path to the local file to upload.
        folder_id (str, optional): The ID of the Google Drive folder to upload into.
        mime_type (str, optional): MIME type of the file. If not specified, Google Drive will try to detect it.
    """
    if not os.path.exists(file_path):
        print(f"Error: Local file '{file_path}' does not exist.")
        return None

    creds = get_credentials()
    if not creds:
        print("Failed to authenticate with Google Drive API.")
        return None

    try:
        service = build("drive", "v3", credentials=creds)

        file_name = os.path.basename(file_path)
        file_metadata = {"name": file_name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        # Use resumable=True for larger files and reliable uploads
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        
        print(f"Uploading '{file_name}' to Google Drive...")
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, mimeType, webViewLink"
        ).execute()

        print("\nUpload Successful!")
        print(f"File Name: {file.get('name')}")
        print(f"File ID: {file.get('id')}")
        print(f"MIME Type: {file.get('mimeType')}")
        print(f"View Link: {file.get('webViewLink')}")
        return file.get("id")

    except HttpError as error:
        print(f"An HTTP error occurred: {error}")
        return None
    except Exception as error:
        print(f"An unexpected error occurred: {error}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a file to Google Drive.")
    parser.add_argument("file_path", help="Path to the local file to upload")
    parser.add_argument("--folder-id", help="Optional Google Drive folder ID to upload the file into")
    parser.add_argument("--mime-type", help="Optional MIME type of the file (e.g., 'text/csv')")
    args = parser.parse_args()
    
    upload_file(args.file_path, folder_id=args.folder_id, mime_type=args.mime_type)
