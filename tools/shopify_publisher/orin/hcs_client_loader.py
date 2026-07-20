#!/usr/bin/env python3
"""
HCS Gadgets Client Loader

Loads HCS client configuration from the shared ORIN client registry.
Provides client-specific path resolution and identity for the ORIN pipeline.

Usage:
    from hcs_client_loader import get_hcs_client_config
    config = get_hcs_client_config()  # returns dict or raises
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

REGISTRY_PATH = Path(__file__).parent / "client_registry.json"

# ─── Registry Loader ──────────────────────────────────────────────────────────

def load_registry() -> dict:
    """Load the shared ORIN client registry."""
    if not REGISTRY_PATH.exists():
        raise RuntimeError(f"ORIN client registry not found: {REGISTRY_PATH}")
    with open(REGISTRY_PATH) as f:
        return json.load(f)

def get_client_config(client_id: str) -> dict:
    """
    Load configuration for a specific client from the registry.

    Returns the client config dict.

    Raises:
        FileNotFoundError: registry not found
        KeyError: client_id not in registry
    """
    registry = load_registry()
    if client_id not in registry.get("clients", {}):
        raise KeyError(f"Unknown client_id: {client_id!r}. Available: {list(registry.get('clients', {}).keys())}")
    return registry["clients"][client_id]

# ─── HCS Client Config ────────────────────────────────────────────────────────

def get_hcs_client_config() -> dict:
    """Load HCS Gadgets client configuration. Fail-closed if unavailable."""
    try:
        config = get_client_config("hcs_gadgets")
    except (FileNotFoundError, KeyError, RuntimeError) as e:
        # RuntimeError: registry file missing
        # FileNotFoundError: registry file missing (older Python behaviour)
        # KeyError: client_id not in registry
        return {
            "client_id": "hcs_gadgets",
            "loaded": False,
            "error": str(e),
            "writer_ready": False,
            "validation_status": "PRODUCT_TRUTH_INVALID",
            "validation_reason": "CLIENT_CONFIG_UNAVAILABLE",
        }

    client_id = config.get("client_id")
    pt_adapter_path = config.get("product_truth_adapter")
    pt_normalised_path = config.get("product_truth_normalised")
    pt_link_map_path = config.get("product_truth_link_map")
    pt_max_age = config.get("product_truth_max_age_hours")
    queue_path = config.get("queue_path")

    result = {
        **config,
        "loaded": True,
        "error": None,
    }

    # ── Product-Truth Gate ─────────────────────────────────────────────────
    pt_valid, pt_reason, pt_status = check_product_truth_gate(
        pt_adapter_path, pt_normalised_path, pt_link_map_path, pt_max_age
    )
    result["product_truth_valid"] = pt_valid
    result["product_truth_reason"] = pt_reason
    result["product_truth_status"] = pt_status
    result["writer_ready"] = pt_valid
    result["validation_status"] = pt_status
    result["validation_reason"] = pt_reason

    # ── Queue Integrity ───────────────────────────────────────────────────
    if queue_path:
        qp = Path(queue_path)
        if qp.exists():
            result["queue_exists"] = True
            result["queue_sha256"] = sha256_file(qp)
        else:
            result["queue_exists"] = False
            result["queue_sha256"] = None
    else:
        result["queue_exists"] = False

    return result

def check_product_truth_gate(adapter_path: str, normalised_path: str,
                              link_map_path: str, max_age_hours: int) -> tuple:
    """
    Run the HCS product-truth gate.

    Returns (writer_ready, reason, status):
        (True,  None,                      "PRODUCT_TRUTH_FRESH")  → gate passed
        (False, "PRODUCT_TRUTH_CONFIG_MISSING", ...)               → config missing
        (False, "PRODUCT_TRUTH_STALE",      "PRODUCT_TRUTH_STALE")  → stale
        (False, "PRODUCT_TRUTH_INVALID",     "PRODUCT_TRUTH_INVALID") → invalid
        (False, "PRODUCT_TRUTH_GATE_BLOCKED", ...)                 → adapter check failed
    """
    if not adapter_path:
        return False, "PRODUCT_TRUTH_GATE_NOT_CONFIGURED", "PRODUCT_TRUTH_INVALID"

    adapter_file = Path(adapter_path)
    if not adapter_file.exists():
        return False, "PRODUCT_TRUTH_ADAPTER_NOT_FOUND", "PRODUCT_TRUTH_INVALID"

    # Load normalised catalogue
    if normalised_path:
        norm_file = Path(normalised_path)
    else:
        return False, "PRODUCT_TRUTH_NORMALISED_NOT_CONFIGURED", "PRODUCT_TRUTH_INVALID"

    if not norm_file.exists():
        return False, "PRODUCT_TRUTH_NORMALISED_FILE_MISSING", "PRODUCT_TRUTH_INVALID"

    try:
        with open(norm_file) as f:
            norm = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"PRODUCT_TRUTH_NORMALISED_PARSE_ERROR: {e}", "PRODUCT_TRUTH_INVALID"

    freshness_status = norm.get("freshness_status", "PRODUCT_TRUTH_INVALID")
    fetched_at = norm.get("fetched_at")
    writer_ready = norm.get("writer_ready", False)
    validation_status = norm.get("validation_status", "PRODUCT_TRUTH_INVALID")

    # Time-based freshness check (defence-in-depth)
    if freshness_status != "PRODUCT_TRUTH_FRESH":
        reason_map = {
            "PRODUCT_TRUTH_STALE": "PRODUCT_TRUTH_STALE",
            "PRODUCT_TRUTH_INVALID": "PRODUCT_TRUTH_INVALID",
        }
        reason = reason_map.get(freshness_status, f"PRODUCT_TRUTH_UNKNOWN_STATUS: {freshness_status}")
        return False, reason, freshness_status

    # Config-validated writer_ready from the adapter
    if not writer_ready:
        return False, validation_status or "PRODUCT_TRUTH_WRITER_NOT_READY", validation_status or "PRODUCT_TRUTH_INVALID"

    # Verify client identity in catalogue
    client_id_in_catalogue = norm.get("client_id", "")
    if client_id_in_catalogue != "hcs_gadgets":
        return False, f"PRODUCT_TRUTH_CLIENT_MISMATCH: expected hcs_gadgets, got {client_id_in_catalogue!r}", "PRODUCT_TRUTH_INVALID"

    # Verify store domain
    source_store = norm.get("source_store", "")
    expected_store = "hcsgadgets-com.myshopify.com"
    if source_store != expected_store:
        return False, f"PRODUCT_TRUTH_STORE_MISMATCH: expected {expected_store}, got {source_store!r}", "PRODUCT_TRUTH_INVALID"

    return True, None, freshness_status

def sha256_file(path: Path) -> str:
    """Compute SHA256 of a file."""
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()

# ─── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = get_hcs_client_config()
    print(json.dumps(config, indent=2, default=str))
