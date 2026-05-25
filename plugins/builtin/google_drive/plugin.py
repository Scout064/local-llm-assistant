from __future__ import annotations

import json

from src.plugins.base import Plugin, ToolDefinition
from plugins.builtin.google_drive.service import GoogleDriveService


class GoogleDrivePlugin(Plugin):
    name = "google_drive"
    display_name = "Google Drive"
    version = "0.1.0"
    description = "List, upload, and download files from Google Drive."
    config_key = "google_drive"

    def __init__(self):
        self.service: GoogleDriveService | None = None

    async def setup(self, config: dict) -> None:
        self.service = GoogleDriveService(
            credentials_file=config.get("credentials_file", "~/.config/assistant/gdrive_credentials.json"),
            token_file=config.get("token_file", "~/.config/assistant/gdrive_token.json"),
        )

    async def health_check(self) -> bool:
        return await self.service.health_check()

    def get_tools(self) -> list[ToolDefinition]:
        list_schema = {
            "type": "function",
            "function": {
                "name": "google_drive_list_files",
                "description": "List files in Google Drive. Optionally filter by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to filter files by name",
                        },
                    },
                    "required": [],
                },
            },
        }

        async def list_handler(query: str = "", **kwargs) -> str:
            files = await self.service.list_files(query)
            return json.dumps(files)

        upload_schema = {
            "type": "function",
            "function": {
                "name": "google_drive_upload_file",
                "description": "Upload a file to Google Drive.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Local path of the file to upload",
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "Google Drive folder ID to upload into (optional)",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        }

        async def upload_handler(file_path: str, parent_id: str | None = None, **kwargs) -> str:
            result = await self.service.upload_file(file_path, parent_id)
            return json.dumps(result)

        return [
            ToolDefinition(schema=list_schema, handler=list_handler),
            ToolDefinition(schema=upload_schema, handler=upload_handler),
        ]

    async def teardown(self) -> None:
        pass


PLUGIN_CLASS = GoogleDrivePlugin