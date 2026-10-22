"""CAP-2.1: three ways a reviewed Terraform plan can be made unsafe. Your policy tests must fail on each.

    terraform -chdir=infra/aws show -json plan.out > plan.json
    python -m fernhill_enterprise mutate plan.json --mutation public_bucket --out mutated.json

Each mutation changes what the plan says will exist (``planned_values`` and ``resource_changes``), the two
places policy tests read. If the plan has nothing of the kind to change, a new unsafe resource is added, so
a mutation always leaves the plan worse than it found it.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator

MUTATIONS = ("public_bucket", "sse_s3_instead_of_kms", "iam_wildcard")
PUBLIC_FLAGS = ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")
WILDCARD = {"Sid": "ProjLabsMutation", "Effect": "Allow", "Action": "s3:*", "Resource": "*"}


def _planned(module: dict) -> Iterator[dict]:
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from _planned(child)


def resources(plan: dict, kind: str) -> list[dict]:
    """Every value block of resources of ``kind`` the plan will create or keep: one dict per place it appears
    (``planned_values`` and the ``after`` of ``resource_changes``)."""
    found = [r["values"] for r in _planned(plan.get("planned_values", {}).get("root_module", {})) if r.get("type") == kind and "values" in r]
    found += [c["change"]["after"] for c in plan.get("resource_changes", []) if c.get("type") == kind and (c.get("change") or {}).get("after")]
    return found


def _add(plan: dict, kind: str, name: str, values: dict) -> None:
    address = f"{kind}.{name}"
    root = plan.setdefault("planned_values", {}).setdefault("root_module", {})
    root.setdefault("resources", []).append(
        {"address": address, "mode": "managed", "type": kind, "name": name, "provider_name": "registry.terraform.io/hashicorp/aws", "values": copy.deepcopy(values)}
    )
    plan.setdefault("resource_changes", []).append(
        {"address": address, "mode": "managed", "type": kind, "name": name, "change": {"actions": ["create"], "before": None, "after": copy.deepcopy(values)}}
    )


def mutate(plan: dict, mutation: str) -> dict:
    """A copy of ``plan`` with one unsafe change."""
    if mutation not in MUTATIONS:
        raise ValueError(f"unknown mutation {mutation!r}; choose one of {', '.join(MUTATIONS)}")
    plan = copy.deepcopy(plan)
    if mutation == "public_bucket":
        blocks = resources(plan, "aws_s3_bucket_public_access_block")
        for values in blocks:
            if values.get("bucket") == (blocks[0].get("bucket")):  # one bucket, wherever the plan mentions it
                values.update(dict.fromkeys(PUBLIC_FLAGS, False))
        if not blocks:
            _add(plan, "aws_s3_bucket", "projlabs_mutation", {"bucket": "projlabs-mutation-public", "force_destroy": False})
            _add(plan, "aws_s3_bucket_public_access_block", "projlabs_mutation", {"bucket": "projlabs-mutation-public", **dict.fromkeys(PUBLIC_FLAGS, False)})
    elif mutation == "sse_s3_instead_of_kms":
        configs = resources(plan, "aws_s3_bucket_server_side_encryption_configuration")
        for values in configs:
            if values.get("bucket") == configs[0].get("bucket"):
                for rule in values.get("rule", []):
                    for default in rule.get("apply_server_side_encryption_by_default", []):
                        default.update(sse_algorithm="AES256", kms_master_key_id=None)
        if not configs:
            _add(plan, "aws_s3_bucket_server_side_encryption_configuration", "projlabs_mutation",
                 {"bucket": "projlabs-mutation", "rule": [{"apply_server_side_encryption_by_default": [{"sse_algorithm": "AES256", "kms_master_key_id": None}], "bucket_key_enabled": False}]})  # fmt: skip
    else:
        changed = False
        for kind in ("aws_iam_policy", "aws_iam_role_policy"):
            for values in resources(plan, kind):
                if isinstance(values.get("policy"), str) and not changed:
                    document = json.loads(values["policy"])
                    statements = document.get("Statement", [])
                    document["Statement"] = [*(statements if isinstance(statements, list) else [statements]), WILDCARD]
                    target = values["policy"]
                    for other in resources(plan, kind):
                        if other.get("policy") == target:
                            other["policy"] = json.dumps(document)
                    changed = True
        if not changed:  # policies not known until apply, or none at all
            _add(plan, "aws_iam_role_policy", "projlabs_mutation",
                 {"name": "projlabs-mutation", "role": "projlabs-mutation", "policy": json.dumps({"Version": "2012-10-17", "Statement": [WILDCARD]})})  # fmt: skip
    return plan
