# SPDX-License-Identifier: proprietary
"""VCU-side wire contract -- STUB.

Owned by the VCU team. Currently lists only the frames the AMS already
relies on (0x100 heartbeat); rest is for the VCU team to fill in as
they grow their pit-diag stream.

When this file gains content, the AMS spec stops duplicating 0x100 (it
moves here as the single source of truth). For now the AMS spec keeps
it because nothing else owns it yet.
"""

from __future__ import annotations

from .common import LE, Message, Signal


# Placeholder so generators have something to emit. Replace with the
# VCU team's actual frames when they file their PR.
MESSAGES = []
