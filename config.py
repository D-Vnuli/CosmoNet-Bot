import json
import os
from dotenv import load_dotenv

load_dotenv()


def get_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()

    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(
            f"{name} РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ С†РµР»С‹Рј РїРѕР»РѕР¶РёС‚РµР»СЊРЅС‹Рј С‡РёСЃР»РѕРј"
        ) from error

    if value <= 0:
        raise RuntimeError(
            f"{name} РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ С†РµР»С‹Рј РїРѕР»РѕР¶РёС‚РµР»СЊРЅС‹Рј С‡РёСЃР»РѕРј"
        )

    return value


def get_int_list(name: str) -> list[int]:
    raw_value = os.getenv(name, "").strip()

    if not raw_value:
        return []

    values = []

    for item in raw_value.split(","):
        item = item.strip()

        if not item:
            continue

        if not item.isdigit():
            raise RuntimeError(
                f"{name} Р Т‘Р С•Р В»Р В¶Р ВµР Р… РЎРѓР С•Р Т‘Р ВµРЎР‚Р В¶Р В°РЎвЂљРЎРЉ ID inbound РЎвЂЎР ВµРЎР‚Р ВµР В· Р В·Р В°Р С—РЎРЏРЎвЂљРЎС“РЎР‹"
            )

        values.append(int(item))

    return values


def get_device_limit_overrides(name: str) -> dict[int, dict[str, int]]:
    raw_value = os.getenv(name, "{}").strip()

    try:
        source = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{name} must be valid JSON") from error

    if not isinstance(source, dict):
        raise RuntimeError(f"{name} must contain an object")

    overrides: dict[int, dict[str, int]] = {}
    for raw_telegram_id, raw_tariffs in source.items():
        if not str(raw_telegram_id).isdigit() or not isinstance(raw_tariffs, dict):
            raise RuntimeError(f"{name} contains an invalid user rule")

        tariff_limits: dict[str, int] = {}
        for tariff_code, devices in raw_tariffs.items():
            if not isinstance(tariff_code, str) or not isinstance(devices, int) or devices <= 0:
                raise RuntimeError(f"{name} contains an invalid device limit")
            tariff_limits[tariff_code] = devices

        overrides[int(raw_telegram_id)] = tariff_limits

    return overrides

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN РЅРµ РЅР°Р№РґРµРЅ РІ .env")

ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in ADMIN_IDS_RAW.split(",")
    if admin_id.strip().isdigit()
]

XUI_BASE_URL = os.getenv("XUI_BASE_URL")
XUI_API_TOKEN = os.getenv("XUI_API_TOKEN")
XUI_SUB_BASE_URL = os.getenv("XUI_SUB_BASE_URL")
XUI_INBOUND_ID_RAW = os.getenv("XUI_INBOUND_ID", "")
XUI_INBOUND_ID = (
    int(XUI_INBOUND_ID_RAW)
    if XUI_INBOUND_ID_RAW.isdigit()
    else None
)
XUI_PROVISIONING_INBOUND_IDS = get_int_list(
    "XUI_PROVISIONING_INBOUND_IDS"
)

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "").strip()
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_URL = os.getenv(
    "YOOKASSA_RETURN_URL",
    "https://cosmonet.shop/",
).strip()

DEVICE_LIMIT_OVERRIDES = get_device_limit_overrides("DEVICE_LIMIT_OVERRIDES")
STARS_PRICE_PROMO = get_positive_int("STARS_PRICE_PROMO", 30)
STARS_PRICE_LITE = get_positive_int("STARS_PRICE_LITE", 79)
STARS_PRICE_STANDARD = get_positive_int("STARS_PRICE_STANDARD", 119)
STARS_PRICE_FAMILY = get_positive_int("STARS_PRICE_FAMILY", 169)

APP_API_HOST = os.getenv("APP_API_HOST", "127.0.0.1").strip()
APP_API_PORT = get_positive_int("APP_API_PORT", 8080)
PAY_SUPPORT_CONTACT = os.getenv(
    "PAY_SUPPORT_CONTACT",
    ""
).strip()
