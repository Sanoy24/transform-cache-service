"""Database tables."""

import uuid

from sqlmodel import Field, SQLModel


class TransformCacheEntry(SQLModel, table=True):
    """One transformer result, shared by every payload that contains the input."""

    __tablename__ = "transform_cache"

    # The input is the lookup key, so it is the primary key: unique and indexed
    # without a surrogate id we would never query by.
    input: str = Field(primary_key=True)
    output: str


class Payload(SQLModel, table=True):
    __tablename__ = "payload"

    # Non-sequential, so public ids don't reveal how many payloads exist.
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # Unique so concurrent requests for the same input cannot store it twice.
    payload_key: str = Field(unique=True)
    output: str
