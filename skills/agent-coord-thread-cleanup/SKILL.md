---
name: agent-coord-thread-cleanup
description: Clean up Agent Coord threads by closing clearly completed finite assignments and assigning every ungrouped thread to an existing or new group. Use when the user requests thread cleanup or organization; preserve uncertain and unfinished work.
---

# Thread cleanup

Carry out the authorized cleanup and return the complete list of confirmed closures and newly created groups. A request to close obviously completed threads and group ungrouped threads authorizes those actions without a separate confirmation for each thread.

Use the installed Agent Coord CLI and the `agent-coord:manage-threads` skill when available. Preserve the inherited coordination database and caller identity. Do not edit database tables or use private HTTP routes.

## Review completion

Inventory globally with `agent-coord thread list`, then read `thread list --archived` and `project list`. The CLI calls named groups “projects”. The inventory's `project_cwd` identifies the directory project that owns a thread; `cwd` identifies its execution directory and can differ. Match groups to `project_cwd`, and verify the saved membership rather than inferring it from the execution directory. Do not limit discovery to the current working directory unless the user requests that scope.

Keep a before snapshot and action receipts outside repositories, under the local Agent Coord state directory. Preserve thread identifiers, titles, original groups and placement so results can be verified and parent-to-child group changes can be reconciled.

Compare the original request and latest relevant request with the current checkpoint, final response, and delivered artifacts. Use `thread show --session-id ID` and `activity history --thread-id ID` for additional evidence. Follow history cursors with exactly the same filters when more context is needed.

Close a thread only when its finite requested outcome was delivered and no required action remains for that thread. Read owner assignments for standing duties: completing the latest subtask does not end an ongoing responsibility. A completed implementation with appropriate validation qualifies. A specialist's completed report, review, or explicit ownership handoff can also qualify even while its parent's larger project continues. Confirm the handoff has occurred and the retired worker has no remaining responsibility.

Keep uncertain cases open. In particular, an ended turn, idle process, old timestamp, “finished” label, or `next_actor: nobody` alone does not establish delivery. Preserve paused campaign owners, recurring responsibilities, unfinished deployment or acceptance, outstanding decisions or approvals, failed or interrupted work without independent completion evidence, and threads with missing or stale evidence. A proposal does not satisfy an implementation request. Do not classify an empty draft as completed work solely because it is empty.

Exclude the cleanup conversation itself from automatic closure. Re-read candidates immediately before acting; if a request, checkpoint, turn, pending input, or activity changed, reassess or leave the thread open.

## Close and group

Use lifecycle closure:

```bash
agent-coord thread close --session-id ID
agent-coord thread close-status --session-id ID
```

Check each receipt and confirm closure. `queued` and `closing` are pending states. Preserve and report failures; do not substitute an archived placement update, terminate processes, or change another thread's progress checkpoint. Closing preserves conversation history and does not certify the underlying project complete.

After closures, assign all ungrouped threads in the requested scope, including newly closed threads. Include previously closed history unless the user limits organization to open threads. Preserve Now, Later, Closed, pins, titles, and unrelated established memberships.

Infer groups from the substantive task, repository, directory project, and existing group vocabulary. A routing prefix or the fact that a voice assistant created a conversation does not establish its subject. Prefer an existing coherent group in the same directory project; create a concise professional group only when needed. Resolve duplicate group names by their IDs and directory ownership.

```bash
agent-coord project create --name 'Group name' --cwd /absolute/project/directory
agent-coord thread update --session-id ID --project GROUP_ID
```

Group assignments propagate to orchestration descendants and attached delegates. Apply parent assignments before children, then reconcile intended memberships against a fresh inventory so unrelated established groups are preserved. Group assignment does not change an execution directory. Directory moves are separate work and are not part of this cleanup procedure.

## Verify and report

Read open threads, closed threads, and groups again. Confirm every reported closure is closed, every in-scope thread has a group, existing placements are preserved except authorized closures, and each new group has its intended directory and members. Distinguish concurrent changes from this cleanup's results.

Return the full closed-thread list and new-group list with recognizable titles, disambiguating directories or identifiers when necessary. For a large inventory, provide a linked local report containing the complete lists and concise counts in the response. Report pending requests and operational limits separately. Save the cleanup thread's factual checkpoint with the actual remaining action, or mark it finished and clear the next step when all authorized work is complete.
