# Genera el archivo _target_tool_ids.txt (tuplas V2_TARGET_TOOL_IDS / _WRITE_IDS / _READ_IDS).
import json
from pathlib import Path

D = Path(__file__).resolve().parent
CAT = (D / ".." / ".." / ".." / ".." / "homi-orchestrator" / "catalog" / "homi-tools.v2.json").resolve()
OUT = D / "_target_tool_ids.txt"

doc = json.loads(CAT.read_text(encoding="utf-8"))
ids = sorted(t["tool_id"] for t in doc["tools"])
write_ids = sorted(t["tool_id"] for t in doc["tools"] if t["kind"] == "WRITE")
read_ids = sorted(t["tool_id"] for t in doc["tools"] if t["kind"] == "READ")

with OUT.open("w", encoding="utf-8") as f:
    f.write(f"# Generado desde homi-tools.v2.json (commit {doc['source_commit']})\n")
    f.write(f"# tools: {len(ids)}  write: {len(write_ids)}  read: {len(read_ids)}\n")
    f.write(f"V2_TARGET_TOOL_IDS: tuple[str, ...] = {tuple(ids)!r}\n\n")
    f.write(f"V2_TARGET_WRITE_IDS: tuple[str, ...] = {tuple(write_ids)!r}\n\n")
    f.write(f"V2_TARGET_READ_IDS: tuple[str, ...] = {tuple(read_ids)!r}\n")
print("wrote", OUT, len(ids), "ids")
