"""Shared Pydantic models for MCP client and tools."""

from typing import Any

from pydantic import BaseModel, Field

# Schedule Request Models


class CreateScheduleRequest(BaseModel):
    """Request payload for creating a schedule."""

    agent_name: str = Field(description="Target agent name")
    function_name: str = Field(description="Function to invoke on each trigger")
    cron_expression: str = Field(
        description="Cron expression (e.g., '0 9 * * MON-FRI' for weekdays at 9am, '*/5 * * * *' for every 5 minutes)"
    )
    timezone: str = Field(
        default="UTC",
        description="Timezone for the cron expression (e.g., 'America/New_York', 'Europe/London')",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Static payload to pass to the function on each invocation",
    )
    description: str | None = Field(
        default=None, description="Human-readable description of the schedule"
    )
    timeout_seconds: int | None = Field(
        default=None,
        description="Timeout for each invocation in seconds (1-86400, max 24 hours)",
    )
    namespace: str = Field(description="Dispatch namespace")


class ListSchedulesRequest(BaseModel):
    """Request payload for listing schedules."""

    agent_name: str | None = Field(
        default=None, description="Filter schedules by agent name"
    )
    namespace: str = Field(description="Dispatch namespace")


class GetScheduleRequest(BaseModel):
    """Request payload for getting a schedule."""

    schedule_id: str = Field(description="Schedule ID to retrieve")
    namespace: str = Field(description="Dispatch namespace")


class UpdateScheduleRequest(BaseModel):
    """Request payload for updating a schedule."""

    schedule_id: str = Field(description="Schedule ID to update")
    cron_expression: str | None = Field(default=None, description="New cron expression")
    timezone: str | None = Field(default=None, description="New timezone")
    payload: dict[str, Any] | None = Field(default=None, description="New payload")
    description: str | None = Field(default=None, description="New description")
    is_paused: bool | None = Field(
        default=None, description="Set to true to pause, false to resume"
    )
    namespace: str = Field(description="Dispatch namespace")


class DeleteScheduleRequest(BaseModel):
    """Request payload for deleting a schedule."""

    schedule_id: str = Field(description="Schedule ID to delete")
    namespace: str = Field(description="Dispatch namespace")


# Schedule Response Models


class CreateScheduleResponse(BaseModel):
    """Response from creating a schedule."""

    schedule_id: str = Field(description="Unique identifier for the created schedule")
    message: str = Field(description="Success message")


class ScheduleInfo(BaseModel):
    """Information about a schedule."""

    schedule_id: str = Field(description="Unique schedule identifier")
    agent_name: str = Field(description="Target agent name")
    function_name: str = Field(description="Function to invoke")
    cron_expression: str = Field(description="Cron expression")
    timezone: str = Field(description="Timezone for the cron expression")
    payload: dict[str, Any] = Field(description="Payload passed on each invocation")
    is_paused: bool = Field(description="Whether the schedule is paused")
    next_run: str | None = Field(default=None, description="Next scheduled run time")
    last_run: str | None = Field(default=None, description="Last run time")
    last_run_status: str | None = Field(
        default=None,
        description="Status of the last run (PENDING, RUNNING, COMPLETED, ERROR)",
    )
    last_run_trace_id: str | None = Field(
        default=None, description="Trace ID of the last run"
    )
    description: str | None = Field(default=None, description="Schedule description")


class ListSchedulesResponse(BaseModel):
    """Response from listing schedules."""

    schedules: list[ScheduleInfo] = Field(description="List of schedules")
    total: int = Field(description="Total number of schedules")


class GetScheduleResponse(ScheduleInfo):
    """Response from getting a schedule (same as ScheduleInfo)."""

    pass


class UpdateScheduleResponse(ScheduleInfo):
    """Response from updating a schedule (same as ScheduleInfo)."""

    pass


class DeleteScheduleResponse(BaseModel):
    """Response from deleting a schedule."""

    message: str = Field(description="Confirmation message")
