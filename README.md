# ifs08-can-spec

Source of truth for the IFS08 CAN wire contract across **AMS**, **VCU**, and **UDV**.

The Python files under [`spec/`](spec/) define every CAN message the team's ECUs emit or consume on FDCAN1 (and the boot trigger on FDCAN2). The generators under [`tools/`](tools/) emit:

- [`dist/ams.dbc`](dist/ams.dbc) / [`dist/vcu.dbc`](dist/vcu.dbc) / [`dist/udv.dbc`](dist/udv.dbc) — Vector DBC, one per ECU
- [`dist/combined.dbc`](dist/combined.dbc) — every frame on the bus, single file
- [`dist/ifs08_can_ids.h`](dist/ifs08_can_ids.h) — C header `#include`d by every firmware repo so they share frame IDs / DLCs / enum values

Every PR into `main` runs the verifier (`tools/check_ids.py` + a DBC-drift check + a cantools parse). Every `v*` tag publishes `dist/*` as release artifacts.

## Why a separate repo

When the wire format lives inside a single firmware repo, it's invisible to the other firmware teams (VCU, UDV) and to the tools that depend on it (pit-debug tool, data logger, dashboard). When that firmware repo changes a signal name, every consumer learns the hard way.

Pulling the spec into its own repo gives:

- **One commit history per wire-contract change.** Renaming a signal is a tiny PR whose diff every consumer can read in 30 seconds.
- **Cross-ECU collision detection at PR time.** `tools/check_ids.py` catches "two ECUs claim sender on the same ID" and "two messages disagree on DLC" — failures that previously only surfaced on the bus.
- **Pinned releases.** A pit-tool deployment targets `ifs08-can-spec v1.5.0`; the AMS firmware that flashed today also targets `v1.5.0`. Mismatch is impossible by construction.

## Repo layout

```
spec/                 source of truth, hand-edited
├── common.py         shared types: Message, Signal, BE/LE bit helpers
├── ams.py            AMS-emitted / AMS-consumed frames
├── vcu.py            VCU spec (stub; VCU team fills in)
└── udv.py            UDV spec (stub; UDV team fills in)

tools/                generators + audit
├── gen_dbc.py        emit per-ECU + combined DBC
├── gen_c_header.py   emit ifs08_can_ids.h
└── check_ids.py      cross-ECU audit (ID collisions, DLC mismatches,
                      unit drift)

dist/                 generated artifacts (committed for curl-able access)
├── ams.dbc
├── vcu.dbc
├── udv.dbc
├── combined.dbc
└── ifs08_can_ids.h
```

## Regenerate

```sh
python3 -m tools.gen_dbc          # writes dist/{ams,vcu,udv,combined}.dbc
python3 -m tools.gen_c_header     # writes dist/ifs08_can_ids.h
python3 -m tools.check_ids        # cross-ECU audit
```

Each tool also has a `--check` mode that the CI uses to verify the committed artifacts haven't drifted from the source:

```sh
python3 -m tools.gen_dbc --check
python3 -m tools.gen_c_header --check
```

## Editing the spec

To add or change a CAN frame:

1. Edit the relevant `spec/<ecu>.py`. The dataclasses in `spec/common.py` are typed; mypy / your IDE will catch most mistakes.
2. Run the generators (`python3 -m tools.gen_dbc && python3 -m tools.gen_c_header`).
3. Run the audit (`python3 -m tools.check_ids`).
4. Commit `spec/*.py` and the updated `dist/*` in the same PR. CI re-runs both as a guardrail.

The byte-order conventions for `BE` and `LE` helpers in `spec/common.py` match Vector DBC's Motorola/Intel bit numbering — see the docstring there for the arithmetic.

## Consuming the spec from a firmware repo

Recommended pattern: **git submodule**.

```sh
git submodule add https://github.com/isc-fs/ifs08-can-spec.git can-spec
```

Then in CMake:

```cmake
target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
    can-spec/dist
)
# Firmware code uses the IDs from the spec:
#   #include "ifs08_can_ids.h"
#   if (frame.id == IFS08_VCU_VCU_dc_bus_heartbeat_ID) { ... }
```

Bump the submodule SHA in a PR when consuming a new wire-contract version. Firmware CI then re-builds against the pinned headers; any mismatch (renamed signal, changed DLC, etc.) shows up as a compile error.

Alternative pattern: **release-artifact download** at configure time. Pin a version in the firmware's `CMakeLists.txt`, fetch via `file(DOWNLOAD ... EXPECTED_HASH ...)`. Useful for external tools and hardware that don't want to clone the spec repo.

## Versioning

- `VERSION` file at the repo root carries the current spec version. Bump on a wire-contract change.
- `v*` git tags trigger a release; the workflow publishes `dist/*` as assets.
- Firmware repos pin to a specific version (submodule SHA or release-asset hash). Tag bumps are coordination events — discuss in the AMS / VCU / UDV channels before bumping.

## Refs

- AMS firmware that consumes from here: [`isc-fs/IFS08-CE-AMS`](https://github.com/isc-fs/IFS08-CE-AMS)
- Pit-debug tool that consumes from here: [`isc-fs/can-flasher`](https://github.com/isc-fs/can-flasher)
- Spec-repo RFC: [`isc-fs/IFS08-CE-AMS#256`](https://github.com/isc-fs/IFS08-CE-AMS/issues/256)
