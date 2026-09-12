"""Portable schema inventory identity, separate from deployment template locks."""
import hashlib
import json


def inventory(template):
    return {"schema":"agentlab.template-inventory.v1", **{
        name:sorted(template[name]["tables"], key=lambda table:table["path"])
        for name in ("session", "ownerGlobal")}}


def inventory_digest(template):
    body=json.dumps(inventory(template), sort_keys=True,
                    separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(body).hexdigest()
