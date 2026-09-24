"""Recorded JSONL Codex app-server fixture used by contract tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

TRANSCRIPT = Path(os.environ["BOTPIPE_FAKE_TRANSCRIPT"])
SCENARIO = os.environ.get("BOTPIPE_FAKE_SCENARIO", "complete")


def receive() -> dict:
    value = json.loads(sys.stdin.readline())
    with TRANSCRIPT.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
    return value


def send(value: dict) -> None:
    print(json.dumps(value, separators=(",", ":")), flush=True)


def spawn_descendant(*, new_session: bool = False) -> subprocess.Popen:
    marker = Path(os.environ["BOTPIPE_FAKE_DESCENDANT_MARKER"])
    pid_file = Path(os.environ["BOTPIPE_FAKE_DESCENDANT_PID"])
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import pathlib,sys,time; time.sleep(1); pathlib.Path(sys.argv[1]).write_text('escaped')",
            str(marker),
        ],
        start_new_session=new_session,
    )
    pid_file.write_text(str(child.pid), encoding="utf-8")
    return child


request = receive()
assert request["method"] == "initialize"
send({"id": request["id"], "result": {"userAgent": "botpipe-contract-fixture"}})
assert receive()["method"] == "initialized"

turn_number = 0
background_child = None
while True:
    request = receive()
    method = request.get("method")
    if method == "thread/backgroundTerminals/clean":
        if background_child is not None:
            background_child.terminate()
            background_child.wait(timeout=2)
        send({"id": request["id"], "result": {}})
        continue
    if SCENARIO == "native_background" and method == "turn/interrupt":
        send({"id": request["id"], "result": {}})
        send({
            "method": "turn/completed",
            "params": {
                "threadId": request["params"]["threadId"],
                "turn": {"id": request["params"]["turnId"], "status": "interrupted"},
            },
        })
        continue
    if method == "mcpServerStatus/list":
        send({"id": request["id"], "result": {"data": []}})
        continue
    if method == "thread/unsubscribe":
        send({"id": request["id"], "result": {"status": "unsubscribed"}})
        continue
    if SCENARIO == "concurrent_stall" and method == "turn/interrupt":
        send({"id": request["id"], "result": {}})
        continue
    if method in {"thread/start", "thread/resume"}:
        time.sleep(float(os.environ.get("BOTPIPE_FAKE_THREAD_DELAY", "0")))
        thread_id = request["params"].get("threadId", "thread-fixture")
        send({"id": request["id"], "result": {"thread": {"id": thread_id}}})
        continue
    if method != "turn/start":
        # The stall scenario intentionally never acknowledges interruption.
        if SCENARIO == "stall_tree" and method == "turn/interrupt":
            while True:
                time.sleep(60)
        raise AssertionError(f"unexpected method: {method}")

    turn_number += 1
    time.sleep(float(os.environ.get("BOTPIPE_FAKE_TURN_START_DELAY", "0")))
    thread_id = request["params"]["threadId"]
    turn_id = f"turn-{turn_number}"
    if SCENARIO in {
        "stall_turn_start",
        "stall_turn_start_complete",
        "stall_turn_start_disallowed",
    }:
        # The native turn may already be executing even though its RPC response
        # was lost. With no turn id available, only transport-tree teardown can
        # establish quiescence.
        if SCENARIO == "stall_turn_start":
            spawn_descendant(new_session=True)
        elif SCENARIO == "stall_turn_start_disallowed":
            send(
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "item": {
                            "type": "commandExecution",
                            "id": "pre-ack-forbidden-command",
                        },
                    },
                }
            )
        else:
            send(
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "item": {
                            "type": "agentMessage",
                            "id": "pre-ack-answer",
                            "text": "completed before acknowledgement",
                        },
                    },
                }
            )
            send(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {"id": turn_id, "status": "completed"},
                    },
                }
            )
        while True:
            time.sleep(60)
    send(
        {
            "id": request["id"],
            "result": {"turn": {"id": turn_id, "status": "inProgress", "items": []}},
        }
    )

    if SCENARIO == "concurrent_stall":
        # Keep accepting JSON-RPC so distinct resumed threads can have active
        # turns at the same time. The test tears down this shared transport.
        continue

    if SCENARIO == "stall_tree":
        # Match Codex's native sandbox helper: it has its own process group and
        # is reparented when app-server teardown wins the interruption race.
        spawn_descendant(new_session=True)
        continue
    if SCENARIO == "native_background":
        background_child = spawn_descendant(new_session=True)
        continue

    if SCENARIO == "disallowed_shell":
        send(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {
                        "type": "commandExecution",
                        "id": "forbidden-command",
                        "command": "python -c write_workspace",
                    },
                },
            }
        )

    send(
        {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "tokenUsage": {"inputTokens": 7, "outputTokens": 3},
            },
        }
    )
    send(
        {
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {"type": "agentMessage", "id": "answer", "text": "fixture answer"},
            },
        }
    )
    # Current Codex nests the turn id in the terminal notification.
    send(
        {
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed", "items": []},
            },
        }
    )
