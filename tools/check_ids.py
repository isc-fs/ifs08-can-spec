#!/usr/bin/env python3
# SPDX-License-Identifier: proprietary
"""Cross-ECU wire-contract audit.

Catches the failures that a single-ECU DBC can't see:
  - Same can_id sent by two different ECUs (ambiguous on the bus)
  - DLC mismatch between same-ID messages (one side expects 4 bytes,
    the other emits 6 -- silent data corruption depending on which
    gets there first)
  - Message sender not in the NODES list (typo or missing node)
  - Signal name reused WITH DIFFERENT UNITS (semantic drift -- two
    things should not be called dc_bus_V if one is volts and the
    other deciamps)

Signal-name reuse across messages with consistent units is allowed
(DBC namespaces signals per-message, and the same physical quantity
appearing in multiple frames -- e.g. dc_bus_V on 0x100 and 0x4A2 --
is a feature, not a collision).

Exits non-zero on any finding. Meant for CI; called from verify.yml.
"""

from __future__ import annotations

import pathlib
import sys
from collections import defaultdict
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from spec import ams, vcu, udv                       # noqa: E402
from spec.common import NODES, Message               # noqa: E402


ALL = [("AMS", ams.MESSAGES),
       ("VCU", vcu.MESSAGES),
       ("UDV", udv.MESSAGES)]


def audit() -> List[str]:
    errors: List[str] = []

    # Sender ID collisions: same can_id sent by two ECUs.
    senders_by_id = defaultdict(list)   # id -> [(file, message)]
    # DLC by id, sender-agnostic: any mismatch is a bug.
    dlc_by_id    = {}
    # Signal-name unit consistency: same name should mean the same
    # physical quantity, no matter which message it lives in.
    units_by_signal = {}    # signal_name -> first (unit, owner, message)

    for owner, msgs in ALL:
        for m in msgs:
            senders_by_id[m.can_id].append((owner, m))
            if m.can_id in dlc_by_id:
                prev_owner, prev_dlc = dlc_by_id[m.can_id]
                if prev_dlc != m.dlc:
                    errors.append(
                        f"DLC mismatch on 0x{m.can_id:03X}: "
                        f"{prev_owner}={prev_dlc} vs {owner}={m.dlc}"
                    )
            else:
                dlc_by_id[m.can_id] = (owner, m.dlc)

            if m.sender not in NODES:
                errors.append(
                    f"{owner}::{m.name} has sender '{m.sender}' not in "
                    f"NODES {NODES}"
                )

            for s in m.signals:
                if s.name not in units_by_signal:
                    units_by_signal[s.name] = (s.unit, owner, m.name)
                else:
                    prev_unit, prev_owner, prev_msg = units_by_signal[s.name]
                    if prev_unit != s.unit:
                        errors.append(
                            f"Signal '{s.name}' unit drift: "
                            f"{prev_owner}::{prev_msg} uses '{prev_unit}', "
                            f"{owner}::{m.name} uses '{s.unit}'"
                        )

    # Sender collisions: same can_id sent by 2+ distinct ECUs.
    for can_id, entries in senders_by_id.items():
        # AMS sender of 0x100 (RX dispatch) + VCU sender of 0x100 (real
        # transmitter) IS a collision -- but in our spec, the AMS files
        # the message under sender="VCU" already (it's "what AMS
        # consumes from VCU"). If two specs both list the same ID with
        # different senders, flag it.
        unique_senders = {m.sender for _owner, m in entries}
        if len(unique_senders) > 1:
            errors.append(
                f"0x{can_id:03X} has conflicting senders: "
                f"{sorted(unique_senders)} (across {[o for o, _ in entries]})"
            )

    return errors


def main() -> int:
    errors = audit()
    if not errors:
        total_msgs = sum(len(m) for _, m in ALL)
        print(f"OK -- {total_msgs} messages audited, no collisions.")
        return 0
    for e in errors:
        print(f"  ERROR: {e}", file=sys.stderr)
    print(f"\n{len(errors)} cross-ECU audit failure(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
