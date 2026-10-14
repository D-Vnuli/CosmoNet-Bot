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
    "https://api.example.invalid:18443/payments/yookassa/return",
).strip()

DEVICE_LIMIT_OVERRIDES = get_device_limit_overrides("DEVICE_LIMIT_OVERRIDES")
STARS_PRICE_PROMO = get_positive_int("STARS_PRICE_PROMO", 30)
STARS_PRICE_LITE = get_positive_int("STARS_PRICE_LITE", 79)
STARS_PRICE_STANDARD = get_positive_int("STARS_PRICE_STANDARD", 119)
STARS_PRICE_FAMILY = get_positive_int("STARS_PRICE_FAMILY", 169)

APP_API_HOST = os.getenv("APP_API_HOST", "127.0.0.1").strip()
APP_API_PORT = get_positive_int("APP_API_PORT", 8080)
SUBSCRIPTION_REMINDER_INTERVAL_SECONDS = get_positive_int(
    "SUBSCRIPTION_REMINDER_INTERVAL_SECONDS",
    3600
)
TRIAL_CHECK_INTERVAL_SECONDS = get_positive_int(
    "TRIAL_CHECK_INTERVAL_SECONDS",
    300,
)
PAY_SUPPORT_CONTACT = os.getenv(
    "PAY_SUPPORT_CONTACT",
    ""
).strip()

COSMONET_WINDOWS_RELEASE_MANIFEST_URL = os.getenv(
    "COSMONET_WINDOWS_RELEASE_MANIFEST_URL",
    "https://api.example.invalid:18443/downloads/latest.json",
).strip()
COSMONET_WINDOWS_FALLBACK_VERSION = os.getenv(
    "COSMONET_WINDOWS_FALLBACK_VERSION",
    "0.2.8",
).strip()
COSMONET_WINDOWS_FALLBACK_DOWNLOAD_URL = os.getenv(
    "COSMONET_WINDOWS_FALLBACK_DOWNLOAD_URL",
    "https://api.example.invalid:18443/downloads/CosmoNet-Setup-0.2.8.rar",
).strip()

# Isolated short-lived VPN used only while the Windows client opens Telegram
# for first-time authorization. It is deliberately disabled by default.
BOOTSTRAP_VPN_ENABLED = os.getenv("BOOTSTRAP_VPN_ENABLED", "false").strip().lower() == "true"
BOOTSTRAP_XUI_BASE_URL = os.getenv("BOOTSTRAP_XUI_BASE_URL", "").strip()
BOOTSTRAP_XUI_API_TOKEN = os.getenv("BOOTSTRAP_XUI_API_TOKEN", "").strip()
BOOTSTRAP_XUI_INBOUND_ID_RAW = os.getenv("BOOTSTRAP_XUI_INBOUND_ID", "").strip()
BOOTSTRAP_XUI_INBOUND_ID = int(BOOTSTRAP_XUI_INBOUND_ID_RAW) if BOOTSTRAP_XUI_INBOUND_ID_RAW.isdigit() else None
BOOTSTRAP_VPN_HOST = os.getenv("BOOTSTRAP_VPN_HOST", "").strip()
BOOTSTRAP_VPN_SNI = os.getenv("BOOTSTRAP_VPN_SNI", "").strip()
BOOTSTRAP_REALITY_PUBLIC_KEY = os.getenv("BOOTSTRAP_REALITY_PUBLIC_KEY", "").strip()
BOOTSTRAP_REALITY_SHORT_ID = os.getenv("BOOTSTRAP_REALITY_SHORT_ID", "").strip()
BOOTSTRAP_WS_XUI_INBOUND_ID_RAW = os.getenv("BOOTSTRAP_WS_XUI_INBOUND_ID", "").strip()
BOOTSTRAP_WS_XUI_INBOUND_ID = int(BOOTSTRAP_WS_XUI_INBOUND_ID_RAW) if BOOTSTRAP_WS_XUI_INBOUND_ID_RAW.isdigit() else None
BOOTSTRAP_WS_VPN_HOST = os.getenv("BOOTSTRAP_WS_VPN_HOST", "").strip()
BOOTSTRAP_WS_TLS_SERVER_NAME = os.getenv("BOOTSTRAP_WS_TLS_SERVER_NAME", "").strip()
BOOTSTRAP_WS_PATH = os.getenv("BOOTSTRAP_WS_PATH", "/cosmonet-auth").strip() or "/cosmonet-auth"
BOOTSTRAP_WS_PORT = get_positive_int("BOOTSTRAP_WS_PORT", 10444)
BOOTSTRAP_TCP_XUI_INBOUND_ID_RAW = os.getenv("BOOTSTRAP_TCP_XUI_INBOUND_ID", "").strip()
BOOTSTRAP_TCP_XUI_INBOUND_ID = int(BOOTSTRAP_TCP_XUI_INBOUND_ID_RAW) if BOOTSTRAP_TCP_XUI_INBOUND_ID_RAW.isdigit() else None
BOOTSTRAP_TCP_VPN_HOST = os.getenv("BOOTSTRAP_TCP_VPN_HOST", "").strip()
BOOTSTRAP_TCP_TLS_SERVER_NAME = os.getenv("BOOTSTRAP_TCP_TLS_SERVER_NAME", "").strip()
BOOTSTRAP_TCP_PORT = get_positive_int("BOOTSTRAP_TCP_PORT", 10445)
