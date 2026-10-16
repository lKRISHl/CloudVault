from typing import Literal

from pydantic import BaseModel


class StorageUsage(BaseModel):
    plan: Literal["free", "team"]
    limit_bytes: int
    retained_bytes: int
    reserved_bytes: int
    derivative_bytes: int
    orphan_bytes: int
    allocated_bytes: int
    available_bytes: int
    unresolved_references: int
    over_quota: bool
    reconciliation_required: bool
