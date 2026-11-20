# handoff — a durable agent bus for Hermes

**"Not delivered" becomes a state, not an error.**

Agent-to-agent delivery has a failure mode nobody talks about: if the receiver is mid-turn, the
message does not queue — it does not exist. `handoff` fixes that with three directories and one
atomic operation.

```
post ──rename──▶ queue/<key> ──take──▶ leased/<key> (lease_until) ──ack──▶ done/<key>
                                          │
                                   lease expired
                                          ▼
                                      sweep ──▶ queue/<key> (attempts += 1)
```

`rename` inside one filesystem is atomic, so two consumers racing for the same message cannot both
win. A consumer that dies mid-work does not swallow the message: its lease expires and `sweep`
returns it.

## Install

```bash
hermes plugins install kostyk348/hermes-handoff
hermes plugins enable handoff
```

Nothing else. No daemon, no port, no database — the queue is a directory
(`~/.local/share/handoff`, override with `HANDOFF_HOME`).

## Tools

| Tool | What it does |
|---|---|
| `handoff_post` | Publish a message. **Idempotent by key**: a second post with the same key changes nothing |
| `handoff_take` | Claim one message with a lease. Exclusive while the lease is alive; returns `null` when empty |
| `handoff_ack` | Finish it (move to `done`) |
| `handoff_nack` | Return it to the queue, or park it in `dead` after N attempts |
| `handoff_sweep` | Recover messages from consumers that died |
| `handoff_list` | Inspect `queue` / `leased` / `done` / `dead` |
| `handoff_stats` | Totals per channel and state |
| `handoff_wait` | Block briefly for the next message, already leased |

A dashboard panel ships too: the same queue, visible in the Hermes UI
(`GET /api/plugins/handoff/state`, plus `post`, `ack`, `sweep`).

## Example

```text
you: "tell careeressa to hold that application"
  → handoff_post(channel="inbox", to="careeressa", key="detmold", body="hold, do not send")

careeressa (whenever it is free):
  → handoff_take(channel="inbox", for="careeressa", lease=120)
  → handoff_ack(channel="inbox", key="detmold")
```

If careeressa never wakes up, the lease expires, `sweep` puts the message back, and it is delivered
on the next attempt — with `attempts=2` recorded, honestly.

## Semantics, exactly

- **post** — idempotent by key; keys are validated (no path traversal).
- **take** — exclusive; the queue is ordered by creation time; `to: "*"` matches any consumer.
- **delivery** — at-least-once. `ack` makes it exactly-once for the sender; the key makes it
  idempotent for the consumer.
- **recovery** — `sweep` returns expired leases; a message that keeps failing lands in `dead`
  rather than looping forever.

## Measured (12 unit tests, all passing)

```
idempotency      second post with the same key → duplicate=true, queue stays at 1
exclusivity      second take → null, message remains leased
recipient filter messages addressed to alpha are invisible to beta
delay            a message posted with delay=60 is not takeable yet
crash recovery   take(lease=1) without ack → sweep returns it, next take shows attempts=2
poison message   nack with max_attempts=1 → dead
wait             returns a posted message immediately; empty queue → null, no hang
interop          the Python plugin and the Rust `handoff` binary read the same queue
```

## Compatibility

The same on-disk protocol is implemented as a standalone Rust binary in
[kostyk348/tools](https://github.com/kostyk348/tools) (`handoff/`, std only, zero dependencies).
Use the plugin for agent tools and the binary for scripts and cron; both see one queue.

## Limits, stated plainly

- Atomicity holds **within one filesystem**. Across machines you need a network filesystem with
  correct `rename` semantics (NFS works; some FUSE mounts do not).
- At-least-once means a consumer must tolerate redelivery; the key is its idempotency token.
- Polling, not push: `wait` is a bounded blocking wrapper. There is no background watcher.
- Messages are plain text files: a bus for trusted local agents, not a secure transport.

## Licence

MIT © 2026 Konstantin Parashchuk
