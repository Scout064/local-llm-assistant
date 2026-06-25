from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

log = structlog.get_logger()


class GoogleDriveService:
    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self._service = None

    async def health_check(self) -> bool:
        try:
            token_path = Path(self.token_file).expanduser()
            return token_path.exists()
        except Exception:
            return False

    def _get_service(self):
        if self._service is not None:
            return self._service

        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/drive"]
        creds_path = Path(self.credentials_file).expanduser()
        token_path = Path(self.token_file).expanduser()

        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())

        self._service = build("drive", "v3", credentials=creds)
        return self._service

    async def list_files(self, query: str = "") -> list[dict]:
        def _list():
            service = self._get_service()
            q = None
            if query:
                escaped = query.replace("'", "\\'")
                q = f"name contains '{escaped}'"
            results = service.files().list(q=q, pageSize=50).execute()
            return results.get("files", [])
        return await asyncio.to_thread(_list)

    async def upload_file(self, file_path: str, parent_id: str | None = None) -> dict:
        import os
        from googleapiclient.http import MediaFileUpload

        def _upload():
            service = self._get_service()
            file_metadata = {"name": os.path.basename(file_path)}
            if parent_id:
                file_metadata["parents"] = [parent_id]
            media = MediaFileUpload(file_path)
            result = service.files().create(
                body=file_metadata, media_body=media, fields="id, name"
            ).execute()
            return result
        return await asyncio.to_thread(_upload)

    async def download_file(self, file_id: str) -> bytes:
        def _download():
            service = self._get_service()
            content = service.files().get_media(fileId=file_id).execute()
            return content
        return await asyncio.to_thread(_download)