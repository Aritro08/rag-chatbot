from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class ModelName(str, Enum):
    GPT5_NANO = "gpt-5-nano"
    GPT5_MINI = "gpt-5-mini"
    GPT4_1_NANO = "gpt-4.1-nano"
    GPT4_1_MINI = "gpt-4.1-mini"
    GPT4_O = "gpt-4o"
    GPT4_O_MINI = "gpt-4o-mini"

class QueryInput(BaseModel):
    question: str
    session_id: str = Field(default=None)
    model_name: ModelName = Field(default=ModelName.GPT4_O_MINI)

class QueryResponse(BaseModel):
    answer: str
    session_id: str
    model_name: str

class DocumentInfo(BaseModel):
    id: int
    file_name: str
    upload_timestamp: datetime

class DeleteFileRequest(BaseModel):
    file_id: int





