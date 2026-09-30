from __future__ import annotations

from ...tool_inputs import (
    AgentJobIdInput,
    ApprovalDecisionInput,
    ApprovalIdInput,
    AuthProfileNameInput,
    CreateSessionRequest,
    DeleteMemoryProfileInput,
    EmptyInput,
    ExecuteActionInput,
    GetMemoryProfileInput,
    ListAgentJobsInput,
    ListApprovalsInput,
    ListAuthProfilesInput,
    ListDownloadsInput,
    ListTabsInput,
    ObserveInput,
    QueueAgentRunInput,
    QueueAgentStepInput,
    ResumeAgentJobInput,
    SaveAuthProfileInput,
    SaveAuthStateInput,
    SaveMemoryProfileInput,
    ScreenshotInput,
    SessionIdInput,
    SessionTailInput,
    SnapshotInput,
    TabActionInput,
    TakeoverInput,
)
from ..registry import ToolSpec


def register(registry, gateway):
    for spec in [
        ToolSpec(
            name="browser.create_session",
            description=(
                "Create a browser session, optionally at a start URL. "
                "Show the result `live_view` banner (session id and watch link) "
                "to the user verbatim."
            ),
            input_model=CreateSessionRequest,
            handler=gateway._create_session,
        ),
        ToolSpec(
            name="browser.save_memory_profile",
            description=(
                "Save a named memory profile with context from the current session. "
                "Loaded into future sessions via memory_profile=name in create_session."
            ),
            input_model=SaveMemoryProfileInput,
            handler=gateway._save_memory_profile,
            governed_kind="write",
        ),
        ToolSpec(
            name="browser.get_memory_profile",
            description="Retrieve a saved memory profile by name.",
            input_model=GetMemoryProfileInput,
            handler=gateway._get_memory_profile,
        ),
        ToolSpec(
            name="browser.list_memory_profiles",
            description="List all saved memory profiles.",
            input_model=EmptyInput,
            handler=gateway._list_memory_profiles,
        ),
        ToolSpec(
            name="browser.delete_memory_profile",
            description="Delete a named memory profile.",
            input_model=DeleteMemoryProfileInput,
            handler=gateway._delete_memory_profile,
            profiles=("full",),
            governed_kind="destructive",
        ),
        ToolSpec(
            name="browser.list_sessions",
            description="List live and persisted browser sessions.",
            input_model=EmptyInput,
            handler=gateway._list_sessions,
        ),
        ToolSpec(
            name="browser.get_session",
            description=(
                "Get the full record for one browser session by ID: the live session "
                "summary (status, current page, tabs) when the session is active, or the "
                "persisted session record when it has been closed."
            ),
            input_model=SessionIdInput,
            handler=gateway._get_session,
        ),
        ToolSpec(
            name="browser.observe",
            description=(
                "Observe the page: interactables, tabs, console, summary. "
                "Presets: text (cheapest, no screenshot/OCR), fast, "
                "normal (default), rich."
            ),
            input_model=ObserveInput,
            handler=gateway._observe,
        ),
        ToolSpec(
            name="browser.screenshot",
            description=(
                "Screenshot the page as viewable JPEG plus a text block; "
                "full PNG is saved. Options: image, format, scale, "
                "quality, full_page, selector."
            ),
            input_model=ScreenshotInput,
            handler=gateway._screenshot,
        ),
        ToolSpec(
            name="browser.snapshot",
            description=(
                "Compact text tree of the page: headings, links, fields, tables. "
                "Control refs work as element_id in execute_action. "
                "Narrow by selector/depth."
            ),
            input_model=SnapshotInput,
            handler=gateway._snapshot,
        ),
        ToolSpec(
            name="browser.get_console",
            description="Read recent browser console messages for an active session.",
            input_model=SessionTailInput,
            handler=gateway._get_console,
        ),
        ToolSpec(
            name="browser.get_page_errors",
            description="Read recent uncaught page errors for an active session.",
            input_model=SessionTailInput,
            handler=gateway._get_page_errors,
        ),
        ToolSpec(
            name="browser.get_request_failures",
            description="Read recent failed network requests for an active session.",
            input_model=SessionTailInput,
            handler=gateway._get_request_failures,
        ),
        ToolSpec(
            name="browser.stop_trace",
            description="Finalize the current Playwright trace for an active session and return its artifact path.",
            input_model=SessionIdInput,
            handler=gateway._stop_trace,
        ),
        ToolSpec(
            name="browser.list_auth_profiles",
            description="List reusable saved auth profiles that can be loaded into a new session.",
            input_model=ListAuthProfilesInput,
            handler=gateway._list_auth_profiles,
        ),
        ToolSpec(
            name="browser.get_auth_profile",
            description=(
                "Inspect one saved auth profile by name: its normalized name, on-disk "
                "profile directory, storage-state metadata, and any saved profile "
                "metadata. Discover names with browser.list_auth_profiles."
            ),
            input_model=AuthProfileNameInput,
            handler=gateway._get_auth_profile,
        ),
        ToolSpec(
            name="browser.list_downloads",
            description="List files captured from browser downloads for one session.",
            input_model=ListDownloadsInput,
            handler=gateway._list_downloads,
        ),
        ToolSpec(
            name="browser.list_tabs",
            description="List currently open tabs/pages for one session.",
            input_model=ListTabsInput,
            handler=gateway._list_tabs,
        ),
        ToolSpec(
            name="browser.activate_tab",
            description=(
                "Bring one tab to the foreground so subsequent observations and actions "
                "target it. Tab indexes come from browser.list_tabs."
            ),
            input_model=TabActionInput,
            handler=gateway._activate_tab,
        ),
        ToolSpec(
            name="browser.close_tab",
            description="Close one tab index if more than one tab is open.",
            input_model=TabActionInput,
            handler=gateway._close_tab,
            governed_kind="write",
        ),
        ToolSpec(
            name="browser.execute_action",
            description=(
                "Run one browser action (navigate, click, type, press, "
                "select, scroll, ...) in a session. Policy-checked; "
                "governed actions may need approval_id. Observe first for IDs."
            ),
            input_model=ExecuteActionInput,
            handler=gateway._execute_action,
            governed_kind="dynamic",
        ),
        ToolSpec(
            name="browser.save_auth_state",
            description="Save session storage state to the per-session auth-state root.",
            input_model=SaveAuthStateInput,
            handler=gateway._save_auth_state,
            profiles=("full",),
            governed_kind="account_change",
        ),
        ToolSpec(
            name="browser.save_auth_profile",
            description="Save the current session storage state into a reusable named auth profile.",
            input_model=SaveAuthProfileInput,
            handler=gateway._save_auth_profile,
            governed_kind="account_change",
        ),
        ToolSpec(
            name="browser.request_human_takeover",
            description="Ask for a human to take over the shared browser desktop.",
            input_model=TakeoverInput,
            handler=gateway._takeover,
            governed_kind="write",
        ),
        ToolSpec(
            name="browser.close_session",
            description="Close a session and finalize its trace/artifacts.",
            input_model=SessionIdInput,
            handler=gateway._close_session,
            governed_kind="write",
        ),
        ToolSpec(
            name="browser.list_approvals",
            description="List pending or historical approval items.",
            input_model=ListApprovalsInput,
            handler=gateway._list_approvals,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.approve_approval",
            description="Approve a pending approval item.",
            input_model=ApprovalDecisionInput,
            handler=gateway._approve_approval,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.reject_approval",
            description="Reject a pending approval item.",
            input_model=ApprovalDecisionInput,
            handler=gateway._reject_approval,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.execute_approval",
            description="Execute an already approved action.",
            input_model=ApprovalIdInput,
            handler=gateway._execute_approval,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.list_agent_jobs",
            description="List queued or completed browser-agent jobs.",
            input_model=ListAgentJobsInput,
            handler=gateway._list_agent_jobs,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.get_agent_job",
            description="Read one browser-agent job record.",
            input_model=AgentJobIdInput,
            handler=gateway._get_agent_job,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.resume_agent_job",
            description="Resume an interrupted, failed, or step-limited background agent run from checkpoints.",
            input_model=ResumeAgentJobInput,
            handler=gateway._resume_agent_job,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.discard_agent_job",
            description="Discard a queued or finished background agent job so operators can clear stale work.",
            input_model=AgentJobIdInput,
            handler=gateway._discard_agent_job,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.cancel_agent_job",
            description="Cancel a queued or running background agent job.",
            input_model=AgentJobIdInput,
            handler=gateway._cancel_agent_job,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.queue_agent_step",
            description="Queue one agent step for background execution.",
            input_model=QueueAgentStepInput,
            handler=gateway._queue_agent_step,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.queue_agent_run",
            description="Queue a short agent loop for background execution.",
            input_model=QueueAgentRunInput,
            handler=gateway._queue_agent_run,
            profiles=("full",),
        ),
        ToolSpec(
            name="browser.list_providers",
            description="List configured model providers for browser-agent orchestration.",
            input_model=EmptyInput,
            handler=gateway._list_providers,
            profiles=("full",),
        ),
    ]:
        registry.register(spec)
