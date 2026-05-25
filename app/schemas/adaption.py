from pydantic import BaseModel, Field


class AdaptionRunCreate(BaseModel):
    artifact_id: str | None = None
    dataset_name: str = "argus-awaaz-multilingual-support-qa"
    estimate: bool = False
    max_rows: int | None = Field(default=None, ge=1)


class AdaptionStatusRequest(BaseModel):
    run_record_id: str


class AdaptionDownloadRequest(BaseModel):
    run_record_id: str
    file_format: str = "jsonl"


class AdaptionRunRead(BaseModel):
    id: str
    dataset_id: str | None
    run_id: str | None
    status: str
    request_payload: dict
    result_summary: dict
    exported_file_path: str | None
    error_message: str | None

    model_config = {"from_attributes": True}
