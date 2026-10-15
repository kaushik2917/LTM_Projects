"""Allowlisted response executor.

Only the action types below exist. Commands are fixed argv templates with
strictly validated parameters; nothing from prediction text, technique names
or free-form input is ever placed in a command. No subprocess is imported:
this build supports DRY_RUN only (project decision), so it records exactly
what would run and how to undo it, without touching any host.
"""
import ipaddress
import re

from app.defense.store import config

ACCOUNT = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
PROCESS = re.compile(r"^[A-Za-z0-9 ._()-]{1,128}\.exe$", re.IGNORECASE)


def validate(action_type, parameters):
    """Return (clean_parameters, None) or (None, refusal_reason); malformed values are refused, never raised."""
    try:
        return _validate(action_type, parameters)
    except (ValueError, TypeError) as exc:
        return None, f"Invalid parameters: {exc}"


def _validate(action_type, parameters):
    settings = config()
    catalogue = settings["response"]["containment_actions"]
    policy = settings["policy"]
    if action_type not in catalogue:
        return None, f"Action {action_type!r} is not allowlisted"
    missing = [k for k in catalogue[action_type]["requires"] if parameters.get(k) in (None, "")]
    if missing:
        return None, f"Missing required parameters: {missing}"
    if action_type == "BLOCK_DESTINATION_IP":
        address = ipaddress.ip_address(str(parameters["destination_ip"]))
        if any(address in ipaddress.ip_network(net) for net in policy["protected_networks"]) or address.is_unspecified or address.is_multicast:
            return None, f"Destination {address} is in a protected network"
        return {"destination_ip": str(address)}, None
    if action_type == "TERMINATE_PROCESS":
        name, pid = str(parameters["process_name"]).lower(), int(parameters["process_id"])
        if pid <= 4 or not PROCESS.match(name):
            return None, "Invalid process identity"
        if name in policy["protected_processes"]:
            return None, f"Process {name} is protected"
        return {"process_id": pid, "process_name": name}, None
    if action_type == "DISABLE_LOCAL_ACCOUNT":
        user = str(parameters["user"]).split("\\")[-1]
        if not ACCOUNT.match(user) or user.lower() in policy["protected_accounts"]:
            return None, f"Account {user!r} is protected or invalid"
        return {"user": user}, None
    return None, "No validator for action"


def plan(action_type, parameters, response_id):
    """Fixed argv templates and their rollback (None when irreversible)."""
    rule = f"FAPT-Guard-{response_id}"
    if action_type == "BLOCK_DESTINATION_IP":
        return (["netsh", "advfirewall", "firewall", "add", "rule", f"name={rule}", "dir=out", "action=block", f"remoteip={parameters['destination_ip']}"],
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"])
    if action_type == "TERMINATE_PROCESS":
        return ["taskkill", "/PID", str(parameters["process_id"]), "/F"], None
    if action_type == "DISABLE_LOCAL_ACCOUNT":
        return ["net", "user", parameters["user"], "/active:no"], ["net", "user", parameters["user"], "/active:yes"]
    raise ValueError("Action is not allowlisted")


def execute(response):
    """Execute an approved response in the configured mode. Only DRY_RUN is implemented."""
    mode = config()["response"]["execution_mode"]
    if mode not in config()["response"]["supported_execution_modes"] or mode != "DRY_RUN":
        return {"state": "REFUSED", "execution_mode": mode, "host_action_executed": False,
                "result": "Real execution backend is not enabled in this build (dry-run only)."}
    return {"state": "EXECUTED_DRY_RUN", "execution_mode": "DRY_RUN", "host_action_executed": False,
            "planned_command": response["planned_command"], "rollback_command": response["rollback_command"],
            "result": "Dry run: command recorded, not executed. No host state was changed."}
