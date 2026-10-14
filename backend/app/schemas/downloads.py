from datetime import datetime

from pydantic import BaseModel

from app.schemas.files import FileRead


class DownloadTicket(BaseModel):
    file: FileRead
    download_url: str
    expires_at: datetime
