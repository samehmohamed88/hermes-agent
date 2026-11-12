"""Pure-data defaults for session retention and history maintenance."""

SESSION_DEFAULTS = {
    # Prune ENDED sessions inactive for retention_days (activity = freshest of live activity /
    # latest message / creation) about once per min_interval_hours at CLI/gateway/cron startup.
    # Open, pinned, or mid-turn sessions are never deleted; stale automation sessions whose
    # process died are *closed*, then get a full retention window before removal.
    # Off by default (deleting history is opt-in). While the user's config.yaml has no
    # auto_prune key, every surface asks once the disk holding state.db runs low
    # (hermes_cli/prune_advisor.py); either answer writes the key and ends the question.
    "auto_prune": False,
    # Inactive days of ended-session history to keep (= `hermes sessions prune`).
    "retention_days": 90,
    # Auto-archive (soft-hide, never delete) sessions with no activity for auto_archive_days,
    # once per min_interval_hours. Pinned sessions are exempt.
    "auto_archive": False,
    # Idle days before auto-archive hides a session (only when auto_archive is true).
    "auto_archive_days": 3,
    # List delegate_task subagent runs in session lists (desktop sidebar, dashboard, session.list),
    # nested under their parent. Off by default: they are machinery, not conversations.
    "show_subagents": False,
    # VACUUM after a prune that deleted rows (SQLite never reclaims disk on DELETE, #54189). It blocks
    # writes (~seconds per 100MB): only at startup, only when ≥1 session went AND freelist/page_count > 25%.
    "vacuum_after_prune": True,
    # Minimum days between VACUUM rewrites; pruning keeps its normal cadence.
    "min_vacuum_interval_days": 30,
    # Minimum hours between auto-maintenance runs (tracked in state.db state_meta, shared across
    # processes).
    "min_interval_hours": 24,

    # Notice about the compact FTS layout (reclaims ~60%+ of state.db). OPT-IN: legacy indexes
    # stay until `hermes sessions optimize-storage` runs, since the rebuild is disk-heavy on
    # large DBs. advise = `hermes update` prints a one-line notice with reclaimable size when a
    # legacy index is detected (a later layout change gets a rebuild notice without a size estimate);
    # require = the same notices worded as REQUIRED (tooling may gate on it); off = none.
    "fts_optimize_notice": "advise",
    # Slow session-search threshold (ms): searches at/above it log one INFO line with the
    # routing path (fts5 / trigram / like_scan). 0 logs every search. Bridged to
    # HERMES_SEARCH_SLOW_MS.
    "search_slow_ms": 1000,
    # Transcript guards (a runaway 100k+ row session can exhaust memory when materialized at
    # once; 0 disables). Max active messages (across the compression lineage) for interactive
    # resume.
    "max_resume_messages": 20000,
    # Max active messages per session for in-memory export (`hermes sessions export`); checked
    # per session, so full-DB backups of small sessions work.
    "max_export_messages": 20000,
    # Seconds before a local session with no viewer is ended (resumable) once its turn settles; 0 = never; after a
    # restart also >= 6h idle. Unset: dashboard.ws_orphan_reap_grace_s: 0 / startup_orphan_sweep: false opt out.
    "orphan_end_grace_s": 300.0,
}
