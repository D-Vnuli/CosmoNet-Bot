import argparse
import asyncio
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.xui_service import XUIService


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or toggle one test client's Reality access while keeping "
            "WS enabled, to test client-side failover."
        )
    )
    parser.add_argument("--email", default="cosmonet-fallback-test")
    parser.add_argument("--reality-inbound-id", type=int, default=6)
    parser.add_argument("--ws-inbound-id", type=int, default=3)
    parser.add_argument(
        "action",
        choices=["status", "disable-reality", "enable-reality"]
    )
    return parser.parse_args()


def parse_settings(inbound: dict) -> dict:
    settings = inbound.get("settings", {})

    if isinstance(settings, str):
        return json.loads(settings)

    return settings if isinstance(settings, dict) else {}


async def get_inbounds_by_id(xui: XUIService, inbound_ids: set[int]):
    result = await xui.get_inbounds()

    if not result["success"]:
        raise RuntimeError(result["error"])

    return {
        inbound.get("id"): inbound
        for inbound in result["inbounds"] or []
        if isinstance(inbound, dict) and inbound.get("id") in inbound_ids
    }


def find_client(inbound: dict, email: str) -> dict | None:
    settings = parse_settings(inbound)

    for client in settings.get("clients", []):
        if isinstance(client, dict) and str(client.get("email")) == email:
            return client

    return None


def find_client_stats(inbound: dict, email: str) -> dict:
    for item in inbound.get("clientStats") or []:
        if isinstance(item, dict) and str(item.get("email")) == email:
            return item

    return {}


async def set_reality_enabled(
    xui: XUIService,
    *,
    inbound: dict,
    email: str,
    enabled: bool
):
    settings = parse_settings(inbound)
    changed = False

    for client in settings.get("clients", []):
        if isinstance(client, dict) and str(client.get("email")) == email:
            client["enable"] = enabled
            changed = True

    if not changed:
        raise RuntimeError(f"Client {email} not found.")

    payload = copy.deepcopy(inbound)
    payload.pop("clientStats", None)
    payload["settings"] = json.dumps(
        settings,
        ensure_ascii=False,
        separators=(",", ":")
    )
    result = await xui._request_json(
        "POST",
        f"/panel/api/inbounds/update/{inbound['id']}",
        payload=payload
    )

    if not result["success"]:
        raise RuntimeError(result["error"])


async def print_status(
    *,
    xui: XUIService,
    email: str,
    reality_inbound_id: int,
    ws_inbound_id: int
):
    inbounds = await get_inbounds_by_id(
        xui,
        {reality_inbound_id, ws_inbound_id}
    )

    for inbound_id, role in [
        (reality_inbound_id, "REALITY"),
        (ws_inbound_id, "WS")
    ]:
        inbound = inbounds.get(inbound_id)

        if not inbound:
            print(f"{role}: inbound {inbound_id} not found")
            continue

        client = find_client(inbound, email)
        stats = find_client_stats(inbound, email)

        if not client:
            print(f"{role}: client {email} not found")
            continue

        print(
            f"{role}: enabled={client.get('enable')} "
            f"up={stats.get('up', 0)} down={stats.get('down', 0)} "
            f"flow={client.get('flow', '')}"
        )


async def main():
    args = parse_args()
    xui = XUIService()

    if args.action == "status":
        await print_status(
            xui=xui,
            email=args.email,
            reality_inbound_id=args.reality_inbound_id,
            ws_inbound_id=args.ws_inbound_id
        )
        return

    inbounds = await get_inbounds_by_id(xui, {args.reality_inbound_id})
    reality_inbound = inbounds.get(args.reality_inbound_id)

    if not reality_inbound:
        raise SystemExit(f"Inbound {args.reality_inbound_id} not found.")

    await set_reality_enabled(
        xui,
        inbound=reality_inbound,
        email=args.email,
        enabled=args.action == "enable-reality"
    )
    await print_status(
        xui=xui,
        email=args.email,
        reality_inbound_id=args.reality_inbound_id,
        ws_inbound_id=args.ws_inbound_id
    )


if __name__ == "__main__":
    asyncio.run(main())
