from __future__ import annotations

"""Compatibility wrapper for the on-chain blob-field probe.

The swarm task specs refer to `src/etl/l1_rpc_probe_blob_fields.py` (T087A).
The implementation lives in `src/etl/l1_probe_blob_ready.py`.
"""

import sys

from src.etl.l1_probe_blob_ready import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

