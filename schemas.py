"""JSON-схемы инструментов плагина handoff."""

POST = {
    "name": "handoff_post",
    "description": "Publish a durable message to a handoff channel. Idempotent by key: posting the same key twice changes nothing. Unlike live agent-to-agent delivery, the message survives a busy or dead receiver.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "description": "Channel name, e.g. 'human' or 'inbox'"},
            "key": {"type": "string", "description": "Idempotency key, e.g. 'salary-expected'"},
            "body": {"type": "string", "description": "Message text shown to the receiver"},
            "to": {"type": "string", "description": "Recipient profile name, or '*' for any consumer", "default": "*"},
            "from": {"type": "string", "description": "Sender name recorded in the message"},
            "delay": {"type": "integer", "description": "Seconds before the message becomes due", "default": 0},
        },
        "required": ["channel", "key", "body"],
    },
}

TAKE = {
    "name": "handoff_take",
    "description": "Claim one message from a channel with a lease. Exclusive: while the lease is alive nobody else can take it. Returns null when the queue is empty — that is a state, not an error.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "for": {"type": "string", "description": "Consumer name; messages addressed to '*' or to this name are eligible"},
            "lease": {"type": "integer", "description": "Lease in seconds before the message returns to the queue", "default": 300},
        },
        "required": ["channel"],
    },
}

ACK = {
    "name": "handoff_ack",
    "description": "Finish a leased message: move it to 'done'. Without an ack the lease expires and the message is redelivered.",
    "parameters": {
        "type": "object",
        "properties": {"channel": {"type": "string"}, "key": {"type": "string"}},
        "required": ["channel", "key"],
    },
}

NACK = {
    "name": "handoff_nack",
    "description": "Return a leased message to the queue immediately, or move it to 'dead' once attempts reach the limit.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "key": {"type": "string"},
            "max_attempts": {"type": "integer", "default": 5},
        },
        "required": ["channel", "key"],
    },
}

SWEEP = {
    "name": "handoff_sweep",
    "description": "Return messages whose lease expired back to the queue. This is the recovery step for a consumer that died mid-work.",
    "parameters": {"type": "object", "properties": {"channel": {"type": "string"}}, "required": ["channel"]},
}

LIST = {
    "name": "handoff_list",
    "description": "List messages in a channel state (queue, leased, done, dead) with their keys, recipients and readiness.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "state": {"type": "string", "enum": ["queue", "leased", "done", "dead"], "default": "queue"},
        },
        "required": ["channel"],
    },
}

STATS = {
    "name": "handoff_stats",
    "description": "Totals per channel and state: pending, leased, done, dead.",
    "parameters": {"type": "object", "properties": {}},
}

WAIT = {
    "name": "handoff_wait",
    "description": "Block until a message arrives (short timeouts only), then return it already leased.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "for": {"type": "string"},
            "lease": {"type": "integer", "default": 300},
            "timeout": {"type": "integer", "description": "Seconds to wait; 0 means one immediate check", "default": 0},
        },
        "required": ["channel"],
    },
}
