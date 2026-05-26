# SPDX-License-Identifier: proprietary
"""IFS08 CAN-spec source-of-truth.

Each per-ECU module exposes a `MESSAGES: list[Message]`. Generators
import them and emit Vector DBC + C headers under dist/.
"""
