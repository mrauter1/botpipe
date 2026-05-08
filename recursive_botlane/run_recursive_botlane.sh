#!/usr/bin/env bash
set -Eeuo pipefail

# Recursive Botlane driver for workflow-driven framework evolution.
#
# This wrapper intentionally targets the globally installed Botlane CLI contract:
#
#   botlane --workspace <workspace> --task-id <task-id> --intent <message> --pairs <pairs>
#   botlane --workspace <workspace> --task-id <task-id> --resume
#
# What it does:
# 1) Establishes standing framework-evolution memory and recursive ledgers.
# 2) Bootstraps the roadmap when a seed is provided.
# 3) Runs bounded recursive cycles that default toward convergence:
#    - consolidation
#    - authoring-surface improvement
#    - portfolio shaping
#    - expansion only when justified
# 4) Resumes nonterminal bootstrap/cycle runs instead of silently starting over.
# 5) Injects architecture-improvement examples and cycle controls into prompts.
# 6) Optionally runs a validation command after bootstrap/cycle tasks.
#
# Boundary:
# - This wrapper is intentionally repo-root oriented and expects the global Botlane CLI.
# - Repository reconnaissance still belongs in the task prompt and the agent's inspection work, not hard-coded wrapper logic.
#
# Requirements:
# - botlane CLI installed and on PATH
# - run from repo root or pass --workspace
# - prompt templates available under --templates-dir or next to this script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
ORIGINAL_ARGV=("$@")
INITIAL_CWD="$(pwd)"
WORKSPACE="$INITIAL_CWD"

# Default is a bounded recursive run: enough cycles to let consolidation/refinement compound,
# but not the old open-ended 100-cycle expansion default.
CYCLES="${CYCLES:-10}"

BASE_TASK_ID="${BASE_TASK_ID:-recursive-framework-evolution-$(date +%Y%m%dT%H%M%S)}"
STATE_DIR_NAME=".botlane_recursive"

SEED_INPUT=""
TEMPLATES_DIR="${TEMPLATES_DIR:-$SCRIPT_DIR/run_recursive_botlane_templates}"

# Cycle policy controls.
CYCLE_MODE="${CYCLE_MODE:-auto}"                 # auto|consolidate|authoring-surface|portfolio-shaping|expand
ALLOW_NEW_WORKFLOWS="${ALLOW_NEW_WORKFLOWS:-0}" # 0|1, false|true, no|yes, off|on
VALIDATION_COMMAND="${VALIDATION_COMMAND:-}"    # optional shell command run after each successful bootstrap/cycle

STATE_ROOT=""
STATE_TASKS_DIR=""
FRAMEWORK_CHARTER_FILE=""
FRAMEWORK_ROADMAP_FILE=""
FRAMEWORK_GAP_LEDGER_FILE=""
WORKFLOW_CANDIDATE_LEDGER_FILE=""
VALIDATION_DEBT_LEDGER_FILE=""
BOOTSTRAP_SEED_FILE=""
RESOLVED_SEED_FILE=""
RECOVERY_LOG_FILE=""
LAST_ACTION_FILE=""
LAST_RERUN_COMMAND_FILE=""
LOCKS_DIR=""
LOCK_DIR=""
LOCK_HELD="0"
CURRENT_ACTION=""
CURRENT_TASK_ID=""
CURRENT_MESSAGE_FILE=""
CURRENT_PAIR_SELECTION=""
CURRENT_BOTLANE_MODE=""
BOTLANE_GIT_DIR=""
BOTLANE_GIT_WORK_TREE=""
BOTLANE_WORKFLOW_NAME="${BOTLANE_WORKFLOW_NAME:-company_operation_to_recursive_improvement_cycle}"

FRAMEWORK_CHARTER_TEMPLATE=""
FRAMEWORK_ROADMAP_TEMPLATE=""
FRAMEWORK_GAP_LEDGER_TEMPLATE=""
WORKFLOW_CANDIDATE_LEDGER_TEMPLATE=""
VALIDATION_DEBT_LEDGER_TEMPLATE=""
WORKFLOW_AUTHORING_DOCTRINE_TEMPLATE=""
WORKFLOW_EXAMPLES_TEMPLATE=""
ARCHITECTURE_IMPROVEMENT_EXAMPLES_TEMPLATE=""
BOOTSTRAP_TASK_TEMPLATE=""
CYCLE_TASK_TEMPLATE=""

fatal() {
  local message="$1"
  local exit_code="${2:-1}"
  echo "FATAL: $message" >&2
  exit "$exit_code"
}

append_recovery_log() {
  local level="$1"
  local message="$2"
  local ts=""

  [[ -n "$RECOVERY_LOG_FILE" ]] || return 0

  mkdir -p "$(dirname "$RECOVERY_LOG_FILE")"
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  printf '%s [%s] %s\n' "$ts" "$level" "$message" >> "$RECOVERY_LOG_FILE"
}

write_atomic_file() {
  local destination="$1"
  local temp_file=""

  mkdir -p "$(dirname "$destination")"
  temp_file="${destination}.tmp.$$"
  cat > "$temp_file"
  mv "$temp_file" "$destination"
}

write_rerun_command_file() {
  [[ -n "$LAST_RERUN_COMMAND_FILE" ]] || return 0

  {
    printf 'bash %q' "$SCRIPT_PATH"
    for arg in "${ORIGINAL_ARGV[@]}"; do
      printf ' %q' "$arg"
    done
    printf '\n'
  } | write_atomic_file "$LAST_RERUN_COMMAND_FILE"
}

record_current_action() {
  local mode="$1"
  local task_id="$2"
  local message_file="${3:-}"
  local pair_selection="${4:-}"

  CURRENT_BOTLANE_MODE="$mode"
  CURRENT_TASK_ID="$task_id"
  CURRENT_MESSAGE_FILE="$message_file"
  CURRENT_PAIR_SELECTION="$pair_selection"
  CURRENT_ACTION="${mode}:${task_id}"

  [[ -n "$LAST_ACTION_FILE" ]] || return 0

  {
    printf 'mode=%q\n' "$mode"
    printf 'task_id=%q\n' "$task_id"
    printf 'message_file=%q\n' "$message_file"
    printf 'pair_selection=%q\n' "$pair_selection"
    printf 'cycle_mode=%q\n' "$CYCLE_MODE"
    printf 'allow_new_workflows=%q\n' "$ALLOW_NEW_WORKFLOWS"
    printf 'validation_command=%q\n' "$VALIDATION_COMMAND"
  } | write_atomic_file "$LAST_ACTION_FILE"
}

clear_current_action() {
  CURRENT_BOTLANE_MODE=""
  CURRENT_TASK_ID=""
  CURRENT_MESSAGE_FILE=""
  CURRENT_PAIR_SELECTION=""
  CURRENT_ACTION=""

  if [[ -n "$LAST_ACTION_FILE" ]]; then
    rm -f "$LAST_ACTION_FILE"
  fi
}

emit_recovery_guidance() {
  local exit_code="${1:-1}"
  local task_id="${CURRENT_TASK_ID}"

  [[ -n "$LAST_RERUN_COMMAND_FILE" ]] || return 0

  echo "[!] Recovery hint: rerun the wrapper using:" >&2
  cat "$LAST_RERUN_COMMAND_FILE" >&2

  if [[ -n "$CURRENT_TASK_ID" ]] && [[ "$CURRENT_BOTLANE_MODE" != "start-seeded-bootstrap" ]]; then
    echo "[!] Direct Botlane resume hint: botlane --workspace \"$WORKSPACE\" --task-id \"$task_id\" --resume" >&2
  fi

  if [[ -n "$RECOVERY_LOG_FILE" ]]; then
    echo "[!] Recovery log: $RECOVERY_LOG_FILE" >&2
  fi
  echo "[!] Exit code: $exit_code" >&2
}

acquire_lock() {
  local lock_pid=""

  mkdir -p "$LOCKS_DIR"
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_HELD="1"
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    return 0
  fi

  if [[ -f "$LOCK_DIR/pid" ]]; then
    lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    if [[ -n "$lock_pid" ]] && ! kill -0 "$lock_pid" 2>/dev/null; then
      rm -f "$LOCK_DIR/pid"
      rmdir "$LOCK_DIR" 2>/dev/null || true
      if mkdir "$LOCK_DIR" 2>/dev/null; then
        LOCK_HELD="1"
        printf '%s\n' "$$" > "$LOCK_DIR/pid"
        append_recovery_log "recovery" "removed stale lock for base_task_id=${BASE_TASK_ID} stale_pid=${lock_pid}"
        return 0
      fi
    fi
    fatal "another run_recursive_botlane.sh process appears to be active for base_task_id=${BASE_TASK_ID} (pid=${lock_pid:-unknown})."
  fi

  fatal "another run_recursive_botlane.sh process appears to be active for base_task_id=${BASE_TASK_ID}."
}

release_lock() {
  if [[ "$LOCK_HELD" == "1" ]] && [[ -n "$LOCK_DIR" ]] && [[ -d "$LOCK_DIR" ]]; then
    rm -f "$LOCK_DIR/pid"
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
  LOCK_HELD="0"
}

handle_interrupt() {
  local signal="$1"
  append_recovery_log "interrupt" "received ${signal} while current_action=${CURRENT_ACTION:-idle}"
  emit_recovery_guidance 130
  exit 130
}

handle_unexpected_error() {
  local exit_code="$1"
  local line_no="$2"
  local command="$3"

  append_recovery_log "error" "unexpected failure at line ${line_no}: ${command} (exit=${exit_code}, action=${CURRENT_ACTION:-idle})"
  emit_recovery_guidance "$exit_code"
  exit "$exit_code"
}

cleanup_on_exit() {
  release_lock
}

require_global_botlane_cli() {
  local help_text=""

  help_text="$(botlane --help 2>/dev/null || true)"
  [[ "$help_text" == *"--workspace"* ]] || fatal "botlane on PATH does not expose the global CLI surface required by recursive_botlane."
  [[ "$help_text" == *"--task-id"* ]] || fatal "botlane on PATH does not expose the global CLI surface required by recursive_botlane."
  [[ "$help_text" == *"--intent"* ]] || fatal "botlane on PATH does not expose the global CLI surface required by recursive_botlane."
  [[ "$help_text" == *"--intent-mode"* ]] || fatal "botlane on PATH does not expose the global CLI surface required by recursive_botlane."
  [[ "$help_text" == *"--pairs"* ]] || fatal "botlane on PATH does not expose the global CLI surface required by recursive_botlane."
  [[ "$help_text" == *"--resume"* ]] || fatal "botlane on PATH does not expose the global CLI surface required by recursive_botlane."
}

resolve_task_dir() {
  resolve_existing_dir "$1"
}

run_botlane_start_cli() {
  local task_id="$1"
  local message_file="$2"
  local pair_selection="$3"
  local message=""

  message="$(cat "$message_file")"

  run_botlane_cli \
    --workspace "$WORKSPACE" \
    --task-id "$task_id" \
    --intent "$message" \
    --intent-mode replace \
    --pairs "$pair_selection"
}

run_botlane_resume_cli() {
  local task_id="$1"

  run_botlane_cli \
    --workspace "$WORKSPACE" \
    --task-id "$task_id" \
    --resume
}

resolve_existing_dir() {
  local raw_path="$1"
  local workspace_candidate=""
  local cwd_candidate=""
  local script_candidate=""

  if [[ -z "$raw_path" ]]; then
    return 1
  fi

  if [[ "$raw_path" = /* ]]; then
    [[ -d "$raw_path" ]] || return 1
    printf '%s\n' "$raw_path"
    return 0
  fi

  workspace_candidate="$WORKSPACE/$raw_path"
  if [[ -d "$workspace_candidate" ]]; then
    printf '%s\n' "$workspace_candidate"
    return 0
  fi

  cwd_candidate="$INITIAL_CWD/$raw_path"
  if [[ -d "$cwd_candidate" ]]; then
    printf '%s\n' "$cwd_candidate"
    return 0
  fi

  script_candidate="$SCRIPT_DIR/$raw_path"
  if [[ -d "$script_candidate" ]]; then
    printf '%s\n' "$script_candidate"
    return 0
  fi

  return 1
}

resolve_seed_file() {
  local raw_path="$1"
  local workspace_candidate=""
  local cwd_candidate=""

  if [[ -z "$raw_path" ]]; then
    return 1
  fi

  if [[ "$raw_path" = /* ]]; then
    [[ -f "$raw_path" ]] || return 1
    printf '%s\n' "$raw_path"
    return 0
  fi

  workspace_candidate="$WORKSPACE/$raw_path"
  if [[ -f "$workspace_candidate" ]]; then
    printf '%s\n' "$workspace_candidate"
    return 0
  fi

  cwd_candidate="$INITIAL_CWD/$raw_path"
  if [[ -f "$cwd_candidate" ]]; then
    printf '%s\n' "$cwd_candidate"
    return 0
  fi

  return 1
}

init_botlane_git_env() {
  local repo_toplevel=""
  local git_dir=""

  [[ -d "$WORKSPACE" ]] || return 0
  command -v git >/dev/null 2>&1 || return 0

  repo_toplevel="$(git -C "$WORKSPACE" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$repo_toplevel" ]] || return 0
  repo_toplevel="$(cd "$repo_toplevel" && pwd)"

  if [[ "$repo_toplevel" == "$WORKSPACE" ]]; then
    return 0
  fi

  case "$WORKSPACE/" in
    "$repo_toplevel"/*)
      ;;
    *)
      return 0
      ;;
  esac

  git_dir="$(git -C "$WORKSPACE" rev-parse --absolute-git-dir 2>/dev/null || true)"
  [[ -n "$git_dir" ]] || return 0

  BOTLANE_GIT_DIR="$git_dir"
  BOTLANE_GIT_WORK_TREE="$WORKSPACE"
}

run_botlane_cli() {
  if [[ -n "$BOTLANE_GIT_DIR" ]] && [[ -n "$BOTLANE_GIT_WORK_TREE" ]]; then
    GIT_DIR="$BOTLANE_GIT_DIR" GIT_WORK_TREE="$BOTLANE_GIT_WORK_TREE" botlane "$@"
    return
  fi

  botlane "$@"
}

latest_botlane_run_dir() {
  local task_id="$1"
  local runs_dir="$WORKSPACE/.botlane/tasks/${task_id}/runs"
  local latest_run_dir=""
  local candidate=""

  [[ -d "$runs_dir" ]] || return 1

  shopt -s nullglob
  for candidate in "$runs_dir"/run-*; do
    [[ -d "$candidate" ]] || continue
    if [[ -z "$latest_run_dir" || "${candidate##*/}" > "${latest_run_dir##*/}" ]]; then
      latest_run_dir="$candidate"
    fi
  done
  shopt -u nullglob

  [[ -n "$latest_run_dir" ]] || return 1
  printf '%s\n' "$latest_run_dir"
}

latest_botlane_run_status() {
  local task_id="$1"
  local run_dir=""
  local events_file=""

  run_dir="$(latest_botlane_run_dir "$task_id")" || return 1
  events_file="$run_dir/events.jsonl"
  [[ -f "$events_file" ]] || return 0

  if command -v python3 >/dev/null 2>&1; then
    python3 - "$events_file" <<'PY'
import json
import sys

last_status = None
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "run_finished" and isinstance(event.get("status"), str):
                last_status = event["status"]
except OSError:
    pass

if last_status is not None:
    print(last_status)
PY
    return 0
  fi

  grep -F '"event_type": "run_finished"' "$events_file" \
    | tail -n 1 \
    | sed -n 's/.*"status": "\([^"]*\)".*/\1/p'
}

task_is_resumable() {
  local task_id="$1"
  local task_dir="$WORKSPACE/.botlane/tasks/$task_id"
  local run_dir=""
  local status=""

  [[ -d "$task_dir" ]] || return 1

  run_dir="$(latest_botlane_run_dir "$task_id")" || return 1
  [[ -f "$run_dir/request.md" ]] || return 1

  status="$(latest_botlane_run_status "$task_id" || true)"
  case "$status" in
    success|blocked|failed|fatal_error|interrupted)
      return 1
      ;;
  esac

  return 0
}

init_template_paths() {
  FRAMEWORK_CHARTER_TEMPLATE="$TEMPLATES_DIR/framework_evolution_charter.md.tmpl"
  FRAMEWORK_ROADMAP_TEMPLATE="$TEMPLATES_DIR/framework_roadmap.md.tmpl"
  FRAMEWORK_GAP_LEDGER_TEMPLATE="$TEMPLATES_DIR/framework_gap_ledger.md.tmpl"
  WORKFLOW_CANDIDATE_LEDGER_TEMPLATE="$TEMPLATES_DIR/workflow_candidate_ledger.md.tmpl"
  VALIDATION_DEBT_LEDGER_TEMPLATE="$TEMPLATES_DIR/validation_debt_ledger.md.tmpl"
  WORKFLOW_AUTHORING_DOCTRINE_TEMPLATE="$TEMPLATES_DIR/workflow_authoring_doctrine.md.tmpl"
  WORKFLOW_EXAMPLES_TEMPLATE="$TEMPLATES_DIR/workflow_examples.md.tmpl"
  ARCHITECTURE_IMPROVEMENT_EXAMPLES_TEMPLATE="$TEMPLATES_DIR/architecture_improvement_examples.md.tmpl"
  BOOTSTRAP_TASK_TEMPLATE="$TEMPLATES_DIR/bootstrap_task.md.tmpl"
  CYCLE_TASK_TEMPLATE="$TEMPLATES_DIR/cycle_task.md.tmpl"
}

ensure_template_files() {
  local template_file=""

  for template_file in \
    "$FRAMEWORK_CHARTER_TEMPLATE" \
    "$FRAMEWORK_ROADMAP_TEMPLATE" \
    "$FRAMEWORK_GAP_LEDGER_TEMPLATE" \
    "$WORKFLOW_CANDIDATE_LEDGER_TEMPLATE" \
    "$VALIDATION_DEBT_LEDGER_TEMPLATE" \
    "$WORKFLOW_AUTHORING_DOCTRINE_TEMPLATE" \
    "$WORKFLOW_EXAMPLES_TEMPLATE" \
    "$ARCHITECTURE_IMPROVEMENT_EXAMPLES_TEMPLATE" \
    "$BOOTSTRAP_TASK_TEMPLATE" \
    "$CYCLE_TASK_TEMPLATE"; do
    [[ -f "$template_file" ]] || fatal "required template file not found: $template_file"
  done
}

render_template_to_file() {
  local template_file="$1"
  local destination_file="$2"
  local cycle_number="${3:-}"

  mkdir -p "$(dirname "$destination_file")"

  awk \
    -v cycle_number="$cycle_number" \
    -v cycle_mode="$CYCLE_MODE" \
    -v allow_new_workflows="$ALLOW_NEW_WORKFLOWS" \
    -v doctrine_file="$WORKFLOW_AUTHORING_DOCTRINE_TEMPLATE" \
    -v examples_file="$WORKFLOW_EXAMPLES_TEMPLATE" \
    -v architecture_examples_file="$ARCHITECTURE_IMPROVEMENT_EXAMPLES_TEMPLATE" '
      function slurp(path,   line, text) {
        text = ""
        if (path == "") {
          return text
        }
        while ((getline line < path) > 0) {
          text = text line ORS
        }
        close(path)
        return text
      }
      BEGIN {
        doctrine_text = slurp(doctrine_file)
        examples_text = slurp(examples_file)
        architecture_examples_text = slurp(architecture_examples_file)
      }
      {
        gsub(/\{\{CYCLE_NUMBER\}\}/, cycle_number)
        gsub(/\{\{CYCLE_MODE\}\}/, cycle_mode)
        gsub(/\{\{ALLOW_NEW_WORKFLOWS\}\}/, allow_new_workflows)
        if ($0 == "{{WORKFLOW_AUTHORING_DOCTRINE}}") {
          printf "%s", doctrine_text
          next
        }
        if ($0 == "{{WORKFLOW_EXAMPLES}}") {
          printf "%s", examples_text
          next
        }
        if ($0 == "{{ARCHITECTURE_IMPROVEMENT_EXAMPLES}}") {
          printf "%s", architecture_examples_text
          next
        }
        print
      }
    ' "$template_file" > "$destination_file"
}

write_if_missing_from_template() {
  local destination="$1"
  local template_file="$2"

  if [[ -e "$destination" ]]; then
    return
  fi

  render_template_to_file "$template_file" "$destination"
}

write_framework_charter() {
  render_template_to_file "$FRAMEWORK_CHARTER_TEMPLATE" "$FRAMEWORK_CHARTER_FILE"
}

ensure_recursive_memory_files() {
  mkdir -p "$STATE_TASKS_DIR"

  # The charter is intentionally rewritten from the current template so standing policy evolves with the wrapper.
  write_framework_charter

  # Ledgers are created once and then preserved as living recursive memory.
  write_if_missing_from_template "$FRAMEWORK_ROADMAP_FILE" "$FRAMEWORK_ROADMAP_TEMPLATE"
  write_if_missing_from_template "$FRAMEWORK_GAP_LEDGER_FILE" "$FRAMEWORK_GAP_LEDGER_TEMPLATE"
  write_if_missing_from_template "$WORKFLOW_CANDIDATE_LEDGER_FILE" "$WORKFLOW_CANDIDATE_LEDGER_TEMPLATE"
  write_if_missing_from_template "$VALIDATION_DEBT_LEDGER_FILE" "$VALIDATION_DEBT_LEDGER_TEMPLATE"

  if [[ -n "$RESOLVED_SEED_FILE" ]]; then
    cp "$RESOLVED_SEED_FILE" "$BOOTSTRAP_SEED_FILE"
  fi
}

write_bootstrap_task() {
  local task_md="$1"
  render_template_to_file "$BOOTSTRAP_TASK_TEMPLATE" "$task_md"
}

write_cycle_task() {
  local cycle="$1"
  local task_md="$2"
  render_template_to_file "$CYCLE_TASK_TEMPLATE" "$task_md" "$cycle"
}

run_validation_command() {
  local label="$1"
  local task_id="${2:-}"
  local exit_code=0

  [[ -n "$VALIDATION_COMMAND" ]] || return 0

  echo
  echo "=== [Validation] ${label} ==="
  echo "Command: $VALIDATION_COMMAND"

  record_current_action "validate-${label}" "$task_id"
  append_recovery_log "validation" "starting validation for ${label}: ${VALIDATION_COMMAND}"

  if (cd "$WORKSPACE" && bash -lc "$VALIDATION_COMMAND"); then
    exit_code=0
  else
    exit_code=$?
  fi

  if [[ "$exit_code" == "0" ]]; then
    append_recovery_log "validation" "completed validation for ${label}"
    clear_current_action
    return 0
  fi

  append_recovery_log "error" "validation failed for ${label} exit=${exit_code}"
  emit_recovery_guidance "$exit_code"
  fatal "validation failed for ${label} (exit=${exit_code})." "$exit_code"
}

run_botlane_start() {
  local task_id="$1"
  local message_file="$2"
  local pair_selection="$3"
  local mode_label="start"
  local exit_code=0

  if [[ -n "$RESOLVED_SEED_FILE" ]] && [[ "$message_file" == "$BOOTSTRAP_SEED_FILE" ]]; then
    mode_label="start-seeded-bootstrap"
  fi

  record_current_action "$mode_label" "$task_id" "$message_file" "$pair_selection"
  append_recovery_log "run" "starting ${mode_label} for task=${task_id} workflow=${BOTLANE_WORKFLOW_NAME} pairs=${pair_selection}"

  if run_botlane_start_cli "$task_id" "$message_file" "$pair_selection"; then
    exit_code=0
  else
    exit_code=$?
  fi

  if [[ "$exit_code" == "0" ]]; then
    append_recovery_log "run" "completed ${mode_label} for task=${task_id}"
    clear_current_action
    return 0
  fi

  append_recovery_log "error" "botlane ${mode_label} failed for task=${task_id} exit=${exit_code}"
  emit_recovery_guidance "$exit_code"
  fatal "botlane ${mode_label} failed for task ${task_id} (exit=${exit_code})." "$exit_code"
}

run_botlane_resume() {
  local task_id="$1"
  local exit_code=0

  record_current_action "resume" "$task_id"
  append_recovery_log "run" "starting resume for task=${task_id}"

  if run_botlane_resume_cli "$task_id"; then
    exit_code=0
  else
    exit_code=$?
  fi

  if [[ "$exit_code" == "0" ]]; then
    append_recovery_log "run" "completed resume for task=${task_id}"
    clear_current_action
    return 0
  fi

  append_recovery_log "error" "botlane resume failed for task=${task_id} exit=${exit_code}"
  emit_recovery_guidance "$exit_code"
  fatal "botlane resume failed for task ${task_id} (exit=${exit_code})." "$exit_code"
}

run_framework_prd_bootstrap() {
  local task_id="${BASE_TASK_ID}-bootstrap"
  local task_md="$STATE_TASKS_DIR/${task_id}.md"
  local request_file="$task_md"
  local latest_status=""

  write_bootstrap_task "$task_md"

  if [[ -n "$RESOLVED_SEED_FILE" ]]; then
    request_file="$BOOTSTRAP_SEED_FILE"
  fi

  echo
  echo "=== [Bootstrap] task_id=${task_id} ==="
  if [[ -n "$RESOLVED_SEED_FILE" ]]; then
    echo "Bootstrap seed: $request_file"
  else
    echo "Bootstrap brief: $task_md"
  fi

  if [[ -z "$RESOLVED_SEED_FILE" ]] && task_is_resumable "$task_id"; then
    echo "Action: resume latest nonterminal bootstrap run"
    run_botlane_resume "$task_id"
    run_validation_command "bootstrap" "$task_id"
    return
  fi

  if [[ -n "$RESOLVED_SEED_FILE" ]]; then
    echo "Action: start a new seeded bootstrap run"
  elif [[ -d "$WORKSPACE/.botlane/tasks/$task_id" ]]; then
    latest_status="$(latest_botlane_run_status "$task_id" || true)"
    echo "Action: start a new bootstrap run for existing task (latest status: ${latest_status:-unknown})"
  else
    echo "Action: start a new bootstrap run"
  fi

  run_botlane_start "$task_id" "$request_file" "plan,implement,test"
  run_validation_command "bootstrap" "$task_id"
}

run_botlane_cycle() {
  local cycle="$1"
  local task_id="${BASE_TASK_ID}-c${cycle}"
  local task_md="$STATE_TASKS_DIR/${task_id}.md"
  local latest_status=""

  write_cycle_task "$cycle" "$task_md"

  echo
  echo "=== [Cycle ${cycle}/${CYCLES}] task_id=${task_id} ==="
  echo "Cycle mode: $CYCLE_MODE"
  echo "Allow new workflows: $ALLOW_NEW_WORKFLOWS"
  echo "Workflow brief: convergence-oriented workflow/framework improvement"
  echo "Task file: $task_md"

  if task_is_resumable "$task_id"; then
    echo "Action: resume latest nonterminal cycle run"
    run_botlane_resume "$task_id"
    run_validation_command "cycle-${cycle}" "$task_id"
    return
  fi

  if [[ -d "$WORKSPACE/.botlane/tasks/$task_id" ]]; then
    latest_status="$(latest_botlane_run_status "$task_id" || true)"
    echo "Action: start a new cycle run for existing task (latest status: ${latest_status:-unknown})"
  else
    echo "Action: start a new cycle run"
  fi

  run_botlane_start "$task_id" "$task_md" "plan,implement,test"
  run_validation_command "cycle-${cycle}" "$task_id"
}

normalize_bool() {
  local raw="$1"
  case "$raw" in
    1|true|TRUE|yes|YES|on|ON)
      printf '1\n'
      ;;
    0|false|FALSE|no|NO|off|OFF)
      printf '0\n'
      ;;
    *)
      return 1
      ;;
  esac
}

usage() {
  cat >&2 <<EOF
Usage: $0 [options]

Options:
  --workspace <path>             Workspace/repo root. Defaults to current directory.
  --cycles <n>                   Number of cycles. Defaults to \$CYCLES or 10.
  --task-id-prefix <slug>        Base task id prefix.
  --seed <file>                  Seed file for bootstrap.
  --templates-dir <path>         Template directory.

Convergence controls:
  --cycle-mode <mode>            auto|consolidate|authoring-surface|portfolio-shaping|expand.
                                  Defaults to \$CYCLE_MODE or auto.
  --allow-new-workflows          Allow expansion cycles to create new workflow packages.
  --no-allow-new-workflows       Disallow new workflow packages. Default.
  --validation-command <cmd>     Optional command to run after successful bootstrap/cycle.

The wrapper intentionally keeps the installed Botlane CLI signature unchanged.
The wrapper is repo-shape agnostic; repository reconnaissance is performed by the Botlane task itself.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace)
      [[ $# -ge 2 ]] || fatal "--workspace requires a value" 2
      WORKSPACE="$2"
      shift 2
      ;;
    --cycles)
      [[ $# -ge 2 ]] || fatal "--cycles requires a value" 2
      CYCLES="$2"
      shift 2
      ;;
    --task-id-prefix)
      [[ $# -ge 2 ]] || fatal "--task-id-prefix requires a value" 2
      BASE_TASK_ID="$2"
      shift 2
      ;;
    --seed)
      [[ $# -ge 2 ]] || fatal "--seed requires a value" 2
      SEED_INPUT="$2"
      shift 2
      ;;
    --templates-dir)
      [[ $# -ge 2 ]] || fatal "--templates-dir requires a value" 2
      TEMPLATES_DIR="$2"
      shift 2
      ;;
    --cycle-mode)
      [[ $# -ge 2 ]] || fatal "--cycle-mode requires a value" 2
      CYCLE_MODE="$2"
      shift 2
      ;;
    --allow-new-workflows)
      ALLOW_NEW_WORKFLOWS="1"
      shift
      ;;
    --no-allow-new-workflows)
      ALLOW_NEW_WORKFLOWS="0"
      shift
      ;;
    --validation-command)
      [[ $# -ge 2 ]] || fatal "--validation-command requires a value" 2
      VALIDATION_COMMAND="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if ! command -v botlane >/dev/null 2>&1; then
  fatal "botlane command not found in PATH."
fi

if [[ ! -d "$WORKSPACE" ]]; then
  fatal "workspace does not exist: $WORKSPACE"
fi

WORKSPACE="$(cd "$WORKSPACE" && pwd)"
init_botlane_git_env
require_global_botlane_cli
TEMPLATES_DIR="$(resolve_task_dir "$TEMPLATES_DIR")" || fatal "templates directory not found: $TEMPLATES_DIR"
init_template_paths
ensure_template_files

if ! [[ "$CYCLES" =~ ^[0-9]+$ ]] || [[ "$CYCLES" -lt 1 ]]; then
  fatal "--cycles must be a positive integer."
fi

case "$CYCLE_MODE" in
  auto|consolidate|authoring-surface|portfolio-shaping|expand)
    ;;
  *)
    fatal "--cycle-mode must be one of: auto, consolidate, authoring-surface, portfolio-shaping, expand."
    ;;
esac

ALLOW_NEW_WORKFLOWS="$(normalize_bool "$ALLOW_NEW_WORKFLOWS")" \
  || fatal "ALLOW_NEW_WORKFLOWS must be boolean-like: 0/1, true/false, yes/no, on/off."

STATE_ROOT="$WORKSPACE/$STATE_DIR_NAME"
STATE_TASKS_DIR="$STATE_ROOT/tasks"
FRAMEWORK_CHARTER_FILE="$STATE_ROOT/framework_evolution_charter.md"
FRAMEWORK_ROADMAP_FILE="$STATE_ROOT/framework_roadmap.md"
FRAMEWORK_GAP_LEDGER_FILE="$STATE_ROOT/framework_gap_ledger.md"
WORKFLOW_CANDIDATE_LEDGER_FILE="$STATE_ROOT/workflow_candidate_ledger.md"
VALIDATION_DEBT_LEDGER_FILE="$STATE_ROOT/validation_debt_ledger.md"
BOOTSTRAP_SEED_FILE="$STATE_ROOT/bootstrap_seed.md"
RECOVERY_LOG_FILE="$STATE_ROOT/recovery.log"
LAST_ACTION_FILE="$STATE_ROOT/last_action.env"
LAST_RERUN_COMMAND_FILE="$STATE_ROOT/rerun_command.sh"
LOCKS_DIR="$STATE_ROOT/locks"
LOCK_DIR="$LOCKS_DIR/${BASE_TASK_ID}.lock"

if [[ -n "$SEED_INPUT" ]]; then
  RESOLVED_SEED_FILE="$(resolve_seed_file "$SEED_INPUT")" \
    || fatal "seed file not found: $SEED_INPUT"
fi

mkdir -p "$STATE_ROOT"
write_rerun_command_file
acquire_lock
trap cleanup_on_exit EXIT
trap 'handle_unexpected_error $? $LINENO "$BASH_COMMAND"' ERR
trap 'handle_interrupt INT' INT
trap 'handle_interrupt TERM' TERM

mkdir -p "$STATE_TASKS_DIR"
ensure_recursive_memory_files

if [[ -n "$BOTLANE_GIT_DIR" ]] && [[ -n "$BOTLANE_GIT_WORK_TREE" ]]; then
  echo "[*] Nested Git workspace detected; constraining botlane git operations to $BOTLANE_GIT_WORK_TREE"
  append_recovery_log "git" "using nested git workspace env git_dir=${BOTLANE_GIT_DIR} work_tree=${BOTLANE_GIT_WORK_TREE}"
fi

echo
echo "=== Recursive Botlane Configuration ==="
echo "Workspace: $WORKSPACE"
echo "Templates: $TEMPLATES_DIR"
echo "Cycles: $CYCLES"
echo "Base task id: $BASE_TASK_ID"
echo "Cycle mode: $CYCLE_MODE"
echo "Allow new workflows: $ALLOW_NEW_WORKFLOWS"
echo "Validation command: ${VALIDATION_COMMAND:-<none>}"
echo "State root: $STATE_ROOT"

if [[ -n "$RESOLVED_SEED_FILE" ]]; then
  run_framework_prd_bootstrap
else
  echo
  echo "=== [Bootstrap] skipped ==="
  echo "No seed provided; starting directly at recursive cycles."
fi

cycle=1
while [[ "$cycle" -le "$CYCLES" ]]; do
  run_botlane_cycle "$cycle"
  cycle=$((cycle + 1))
done

echo
echo "Recursive botlane sequence finished."
