import argparse
import asyncio
import json

from config import XUI_PROVISIONING_INBOUND_IDS
from services.xui_service import XUIService


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Sync existing 3X-UI clients into all configured provisioning "
            "inbounds, e.g. Reality primary + WS fallback."
        )
    )
    parser.add_argument(
        "--source-inbound-id",
        type=int,
        default=None,
        help=(
            "Inbound to read existing clients from. Defaults to the second "
            "XUI_PROVISIONING_INBOUND_IDS item when available."
        )
    )
    parser.add_argument(
        "--email",
        action="append",
        default=[],
        help="Client email to sync. Can be passed multiple times."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync every client from the source inbound."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update 3X-UI. Without this flag the script is dry-run."
    )
    return parser.parse_args()


def parse_settings(inbound: dict) -> dict:
    settings = inbound.get("settings", {})

    if isinstance(settings, str):
        return json.loads(settings)

    return settings if isinstance(settings, dict) else {}


async def main():
    args = parse_args()

    if not XUI_PROVISIONING_INBOUND_IDS:
        raise SystemExit(
            "Set XUI_PROVISIONING_INBOUND_IDS first, for example: 6,3"
        )

    if not args.all and not args.email:
        raise SystemExit("Pass --email USER, or --all for the source inbound.")

    source_inbound_id = args.source_inbound_id

    if source_inbound_id is None:
        source_inbound_id = (
            XUI_PROVISIONING_INBOUND_IDS[1]
            if len(XUI_PROVISIONING_INBOUND_IDS) > 1
            else XUI_PROVISIONING_INBOUND_IDS[0]
        )

    xui = XUIService()
    inbounds_result = await xui.get_inbounds()

    if not inbounds_result["success"]:
        raise SystemExit(inbounds_result["error"])

    source_inbound = next(
        (
            inbound
            for inbound in inbounds_result["inbounds"] or []
            if inbound.get("id") == source_inbound_id
        ),
        None
    )

    if not source_inbound:
        raise SystemExit(f"Inbound {source_inbound_id} not found.")

    source_settings = parse_settings(source_inbound)
    source_clients = [
        client
        for client in source_settings.get("clients", [])
        if isinstance(client, dict)
    ]
    selected_emails = {str(email) for email in args.email}

    if args.all:
        clients_to_sync = source_clients
    else:
        clients_to_sync = [
            client
            for client in source_clients
            if str(client.get("email")) in selected_emails
        ]

    if not clients_to_sync:
        raise SystemExit("No matching clients found.")

    action = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{action}: {len(clients_to_sync)} clients from inbound "
        f"{source_inbound_id} -> {XUI_PROVISIONING_INBOUND_IDS}"
    )

    if not args.apply:
        for client in clients_to_sync:
            print(f"- {client.get('email')}")
        return

    for client in clients_to_sync:
        result = await xui._sync_client_across_inbounds(
            email=str(client.get("email")),
            telegram_id=client.get("tgId", 0),
            devices=client.get("limitIp", 0),
            expiry_time_ms=client.get("expiryTime", 0),
            existing_client=client
        )

        if result["success"]:
            print(f"OK  {client.get('email')}")
        else:
            print(f"ERR {client.get('email')}: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
