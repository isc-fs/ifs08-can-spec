#!/usr/bin/env python3
# SPDX-License-Identifier: proprietary
"""Generate Vector DBC files for each ECU + a combined DBC.

Usage:
  python3 -m tools.gen_dbc                          # write dist/*.dbc
  python3 -m tools.gen_dbc --check                  # CI: fail on drift
  python3 -m tools.gen_dbc --stdout --ecu ams       # print one ECU
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import sys
from typing import Iterable, List, Optional

# Allow running as `python3 tools/gen_dbc.py` from the repo root as
# well as `python3 -m tools.gen_dbc`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from spec import ams, vcu, udv               # noqa: E402
from spec.common import Message, Signal, NODES   # noqa: E402


ECU_SPECS = {
    "ams":      ams.MESSAGES,
    "vcu":      vcu.MESSAGES,
    "udv":      udv.MESSAGES,
    "combined": ams.MESSAGES + vcu.MESSAGES + udv.MESSAGES,
}


# --- DBC emission ----------------------------------------------------------

_NS_ITEMS = [
    "NS_DESC_", "CM_", "BA_DEF_", "BA_", "VAL_", "CAT_DEF_", "CAT_",
    "FILTER", "BA_DEF_DEF_", "EV_DATA_", "ENVVAR_DATA_", "SGTYPE_",
    "SGTYPE_VAL_", "BA_DEF_SGTYPE_", "BA_SGTYPE_", "SIG_TYPE_REF_",
    "VAL_TABLE_", "SIG_GROUP_", "SIG_VALTYPE_", "SIGTYPE_VALTYPE_",
    "BO_TX_BU_", "BA_DEF_REL_", "BA_REL_", "BA_DEF_DEF_REL_",
    "BU_SG_REL_", "BU_EV_REL_", "BU_BO_REL_", "SG_MUL_VAL_",
]


def _resolve_minmax(s: Signal) -> tuple:
    """Default the [min|max] range to the full physical extent of the
    signal type when the caller left it as the [0|0] sentinel. Strict
    DBC parsers (cantools) reject values outside the declared range,
    and [0|0] is *not* the universal 'unrestricted' marker."""
    if s.maximum != s.minimum:
        return s.minimum, s.maximum
    if s.field.sign == "+":
        raw_max = (1 << s.field.length) - 1
        return 0, raw_max * s.factor + s.offset
    raw_max = (1 << (s.field.length - 1)) - 1
    raw_min = -(1 << (s.field.length - 1))
    return raw_min * s.factor + s.offset, raw_max * s.factor + s.offset


def _fmt_num(v: float) -> str:
    return f"{int(v)}" if float(v).is_integer() else f"{v}"


def emit_dbc(messages: List[Message]) -> str:
    lines: List[str] = []
    lines.append('VERSION ""')
    lines.append("")
    lines.append("NS_ :")
    for it in _NS_ITEMS:
        lines.append(f"\t{it}")
    lines.append("")
    lines.append("BS_:")
    lines.append("")
    lines.append("BU_: " + " ".join(NODES))
    lines.append("")

    for m in messages:
        lines.append(f"BO_ {m.can_id} {m.name}: {m.dlc} {m.sender}")
        for s in m.signals:
            smin, smax = _resolve_minmax(s)
            recv = ",".join(s.receivers)
            lines.append(
                f" SG_ {s.name} : "
                f"{s.field.start_bit}|{s.field.length}@{s.field.byte_order}{s.field.sign}"
                f" ({s.factor},{s.offset}) [{_fmt_num(smin)}|{_fmt_num(smax)}]"
                f' "{s.unit}" {recv}'
            )
        lines.append("")

    # CM_ message comments
    for m in messages:
        if m.comment:
            lines.append(f'CM_ BO_ {m.can_id} "{m.comment}";')
        for s in m.signals:
            if s.comment:
                lines.append(f'CM_ SG_ {m.can_id} {s.name} "{s.comment}";')

    # VAL_ enum tables (so importers like cantools or PCAN-View show names
    # instead of raw integers).
    for m in messages:
        for s in m.signals:
            if not s.enum:
                continue
            pairs = " ".join(f'{k} "{v}"' for k, v in sorted(s.enum.items()))
            lines.append(f"VAL_ {m.can_id} {s.name} {pairs} ;")

    lines.append("")
    return "\n".join(lines) + "\n"


# --- CLI -------------------------------------------------------------------

def _dist_path(ecu: str) -> pathlib.Path:
    repo = pathlib.Path(__file__).resolve().parents[1]
    return repo / "dist" / f"{ecu}.dbc"


def cmd_write(ecus: Iterable[str]) -> int:
    for ecu in ecus:
        out = emit_dbc(ECU_SPECS[ecu])
        path = _dist_path(ecu)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(out)
        print(f"wrote {path}  ({len(out.splitlines())} lines, "
              f"{len(ECU_SPECS[ecu])} messages)")
    return 0


def cmd_check(ecus: Iterable[str]) -> int:
    failed = []
    for ecu in ecus:
        fresh = emit_dbc(ECU_SPECS[ecu])
        path = _dist_path(ecu)
        if not path.exists():
            print(f"error: {path} missing -- run gen_dbc without --check first",
                  file=sys.stderr)
            failed.append(ecu)
            continue
        committed = path.read_text()
        if committed == fresh:
            print(f"OK -- {path} matches generator "
                  f"({len(fresh.splitlines())} lines)")
            continue
        failed.append(ecu)
        print(f"error: {path} drifted from generator", file=sys.stderr)
        diff = difflib.unified_diff(
            committed.splitlines(keepends=True),
            fresh.splitlines(keepends=True),
            fromfile=f"{path} (committed)",
            tofile=f"{path} (generator output)",
            n=3,
        )
        sys.stderr.write("".join(diff))
    if failed:
        print(f"\nRegenerate with: python3 -m tools.gen_dbc",
              file=sys.stderr)
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify committed dist/*.dbc match the generator")
    ap.add_argument("--stdout", action="store_true",
                    help="print one ECU's DBC to stdout (requires --ecu)")
    ap.add_argument("--ecu", choices=list(ECU_SPECS),
                    help="restrict to a single ECU (default: all)")
    args = ap.parse_args(argv)

    ecus = [args.ecu] if args.ecu else list(ECU_SPECS)

    if args.stdout:
        if len(ecus) != 1:
            ap.error("--stdout requires --ecu <name>")
        sys.stdout.write(emit_dbc(ECU_SPECS[ecus[0]]))
        return 0

    return cmd_check(ecus) if args.check else cmd_write(ecus)


if __name__ == "__main__":
    raise SystemExit(main())
