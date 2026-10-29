#!/bin/bash
# Probe: does Claude Code send agent_summary side-queries while a subagent works?
# Usage: agent-summary-probe.sh <out_dir> <label> <summaries 0|1>
# Tested with Claude Code 2.1.312, model haiku, on Windows 11 (Git Bash).
# The OpenTelemetry console output contains account identifiers: do not publish it raw.
OUT=$1; LABEL=$2; SUM=$3
mkdir -p "$OUT/work-$LABEL"; cd "$OUT/work-$LABEL" || exit 1
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=console
export OTEL_LOGS_EXPORT_INTERVAL=1000
export OTEL_METRICS_EXPORTER=none
if [ "$SUM" = "1" ]; then export CLAUDE_CODE_AGENT_PROGRESS_SUMMARIES=1; fi
PROMPT='Use the Agent tool exactly once. The subagent must run these Bash commands one at a time as 8 separate Bash calls, in order: `sleep 20` (eight times, each its own call), then reply with the single word done. After the subagent finishes, reply with the single word finished.'
claude -p --model haiku --allowedTools "Agent Bash" \
  --debug-file "$OUT/$LABEL.debug.log" "$PROMPT" > "$OUT/$LABEL.out.txt" 2> "$OUT/$LABEL.err.txt"
# Count side-queries: grep -c "Forking" "$OUT/$LABEL.debug.log"
