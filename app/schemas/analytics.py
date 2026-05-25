from pydantic import BaseModel


class LatestAdaptionRun(BaseModel):
    id: str | None
    dataset_id: str | None
    run_id: str | None
    status: str | None
    error_message: str | None


class AnalyticsSummary(BaseModel):
    total_sessions: int
    total_results: int
    total_corrections: int
    total_dataset_rows: int
    total_exports: int
    escalation_required_count: int
    escalation_rate: float
    rows_by_language: dict[str, int]
    rows_by_label: dict[str, int]
    rows_by_source: dict[str, int]
    latest_adaption_run: LatestAdaptionRun


class DependencyStatus(BaseModel):
    ok: bool
    detail: str


class ReadinessSummary(BaseModel):
    status: str
    database: DependencyStatus
    export_directory: DependencyStatus
    livekit_config: DependencyStatus
    adaption_config: DependencyStatus
