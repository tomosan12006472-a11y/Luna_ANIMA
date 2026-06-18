from __future__ import annotations

from pydantic import BaseModel


class I2IFromHistoryRequest(BaseModel):
    history_id: str
