"""Request and response models of the public API."""

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class PayloadCreate(BaseModel):
    """Input for generating a payload from two lists of strings."""

    # Reject unknown fields so typos such as "list1" fail explicitly
    # instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")

    list_1: list[str]
    list_2: list[str]

    @model_validator(mode="after")
    def check_equal_length(self) -> Self:
        if len(self.list_1) != len(self.list_2):
            raise ValueError("list_1 and list_2 must have the same length")
        return self


class PayloadCreated(BaseModel):
    id: uuid.UUID
    message: str


class PayloadOutput(BaseModel):
    output: str
