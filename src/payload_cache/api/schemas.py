import uuid
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Request size limits are part of the API contract (they show up in the OpenAPI schema),
# not deployment tuning: one request must not be able to trigger an unbounded number of
# (potentially paid) transformer calls or exhaust memory.
MAX_ITEMS_PER_LIST = 1_000
MAX_STRING_LENGTH = 10_000

BoundedString = Annotated[str, Field(max_length=MAX_STRING_LENGTH)]
BoundedList = Annotated[list[BoundedString], Field(min_length=1, max_length=MAX_ITEMS_PER_LIST)]


class PayloadCreate(BaseModel):
    # Unknown fields are rejected so a typo like "list1" fails loudly instead of being ignored.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "list_1": ["first string", "second string", "third string"],
                    "list_2": ["other string", "another string", "last string"],
                }
            ]
        },
    )

    list_1: BoundedList
    list_2: BoundedList

    @model_validator(mode="after")
    def _lists_have_equal_length(self) -> Self:
        if len(self.list_1) != len(self.list_2):
            raise ValueError(
                f"list_1 and list_2 must have the same length "
                f"(got {len(self.list_1)} and {len(self.list_2)})"
            )
        return self


class PayloadCreated(BaseModel):
    id: uuid.UUID
    message: str


class PayloadRead(BaseModel):
    output: str


class HealthStatus(BaseModel):
    status: str
