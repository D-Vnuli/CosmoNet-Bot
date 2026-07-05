import os
from dotenv import load_dotenv

load_dotenv()


def get_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()

    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(
            f"{name} должен быть целым положительным числом"
        ) from error

    if value <= 0:
        raise RuntimeError(
            f"{name} должен быть целым положительным числом"
        )

    return value


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

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

TEST_PAYMENTS_ENABLED = os.getenv(
    "TEST_PAYMENTS_ENABLED",
    "false"
).strip().lower() in {"1", "true", "yes", "on"}

STARS_PRICE_LITE = get_positive_int("STARS_PRICE_LITE", 79)
STARS_PRICE_STANDARD = get_positive_int("STARS_PRICE_STANDARD", 119)
STARS_PRICE_FAMILY = get_positive_int("STARS_PRICE_FAMILY", 169)

PAY_SUPPORT_CONTACT = os.getenv(
    "PAY_SUPPORT_CONTACT",
    ""
).strip()
