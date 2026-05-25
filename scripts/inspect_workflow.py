#!/usr/bin/env python3
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
workflow = json.loads(path.read_text())
print(f"\n{'ID':<8} {'Class':<35} {'Title'}")
print("-" * 70)
for node_id, node in sorted(workflow.items(), key=lambda x: int(x[0])):
    title = node.get("_meta", {}).get("title", "")
    print(f"{node_id:<8} {node['class_type']:<35} {title}")