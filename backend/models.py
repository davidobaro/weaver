from typing import Literal
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Value = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Category = Literal['birthday', 'interest', 'plan', 'commitment', 'relationship', 'context']


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    person: Name
    category: Category
    value: Value
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    replaces_id: int | None = Field(default=None, gt=0)
    duplicate_of: int | None = Field(default=None, gt=0)


class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    memories: list[Candidate] = Field(max_length=40)


class NoteInput(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30000)]
    automatic: bool = True
    kind: Literal['note', 'journal'] = 'note'
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=180)] = ''
    entry_date: date | None = None


class MemoryEdit(BaseModel):
    person: Name
    category: Category
    value: Value


class ReviewedMemory(BaseModel):
    candidate_index: int = Field(ge=0)
    person: Name
    category: Category
    value: Value
    replaces_id: int | None = Field(default=None, gt=0)


class ReviewInput(BaseModel):
    memories: list[ReviewedMemory] = Field(max_length=40)


class SuggestionAction(BaseModel):
    status: Literal['done', 'dismissed', 'open']


class AliasInput(BaseModel):
    name: Name


class PersonPair(BaseModel):
    source_id: int = Field(gt=0)
    target_id: int = Field(gt=0)
