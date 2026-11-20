# catalog: add `handoff` — a durable agent bus on the filesystem

## What it is

`handoff` gives agents a queue that cannot silently lose a message. Agent-to-agent delivery today
has a failure mode nobody names: if the receiver is mid-turn, the message is not queued — it does
not exist. Here it becomes a state.

```
post ──rename──▶ queue/<key> ──take──▶ leased/<key> (lease_until) ──ack──▶ done/<key>
                                          │
                                   lease expired
                                          ▼
                                      sweep ──▶ queue/<key> (attempts += 1)
```

Messages are files, transitions are one atomic `rename`, and the queue is a directory — no daemon,
no port, no database. `HANDOFF_HOME` lets two profiles or two machines share a channel.

## Tools (8)

| Tool | Behaviour |
|---|---|
| `handoff_post` | idempotent by key — a second post with the same key changes nothing |
| `handoff_take` | exclusive claim with a lease; `null` when the queue is empty (a state, not an error) |
| `handoff_ack` | move to `done` |
| `handoff_nack` | return to the queue, or park in `dead` after N attempts |
| `handoff_sweep` | recover messages from consumers that died mid-work |
| `handoff_list` | inspect `queue` / `leased` / `done` / `dead` |
| `handoff_stats` | totals per channel and state |
| `handoff_wait` | bounded blocking wait, returns the message already leased |

A dashboard panel ships with it (`GET /api/plugins/handoff/state`, plus `post`, `ack`, `sweep`), so a
human sees the same queue the agent works from.

## Verification performed

```
hermes plugins validate        → Validation passed
                                 (loadable · capability probe · declared tools match ·
                                  security scan · no core override)
hermes plugins install kostyk348/hermes-handoff   → installed into a clean HERMES_HOME
hermes plugins enable handoff  → tools live in the next session
handoff_stats from a fresh session → real JSON: queue 6, channel human
unit tests                     → 12/12, including an interop test where the Python plugin and
                                 the Rust binary read and write the same queue
```

The interop test matters: the same on-disk protocol is implemented as a zero-dependency Rust binary
([kostyk348/tools](https://github.com/kostyk348/tools)), so scripts, cron and agents share one queue.

## Disclosure

- Messages are plain text files readable by anything with access to that directory — this is a bus
  for trusted local agents, not a secure transport.
- Delivery is **at-least-once**: a consumer must tolerate redelivery; the key is its idempotency
  token.
- Atomicity holds within a single filesystem; across machines you need a network filesystem with
  correct `rename` semantics (NFS is fine, some FUSE mounts are not).
- No push notifications: `take` polls, `wait` is a bounded blocking wrapper.

## Repo

https://github.com/kostyk348/hermes-handoff — MIT, no dependencies, `plugin.yaml` at the root,
tests included.
