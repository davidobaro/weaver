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


class PersonalCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Literal['task', 'plan', 'reminder', 'goal']
    value: Value
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class PersonalCompletion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: Value
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    memories: list[Candidate] = Field(max_length=40)
    personal: list[PersonalCandidate] = Field(default_factory=list, max_length=40)
    completed_personal: list[PersonalCompletion] = Field(default_factory=list, max_length=40)


class ReminderTiming(BaseModel):
    model_config = ConfigDict(extra='forbid')
    due_date: date | None = None
    reset_due_date: bool = False
    snoozed_until: date | None = None


class ReminderRepeat(BaseModel):
    model_config = ConfigDict(extra='forbid')
    frequency: Literal['daily', 'weekly', 'monthly'] | None
    start_date: date | None = None


class EntryContent(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    kind: Literal['note', 'journal'] = 'note'
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=180)] = ''
    entry_date: date | None = None


class NoteInput(EntryContent):
    automatic: bool = True


class EntryEdit(EntryContent):
    expected_revision: int = Field(ge=1)


class EntryRestore(BaseModel):
    expected_revision: int = Field(ge=1)
    revision: int = Field(ge=1)


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
    stop_repeat: bool = False


class AliasInput(BaseModel):
    name: Name


class PersonPair(BaseModel):
    source_id: int = Field(gt=0)
    target_id: int = Field(gt=0)
