import os
import unittest
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from services import tariff_service


class TariffOverrideTests(unittest.TestCase):
    def test_friend_device_rules_keep_tariff_price_and_duration(self):
        rules = {
            565660788: {"promo": 3, "lite": 3},
            824142682: {"promo": 2, "lite": 2},
        }
        with patch.object(tariff_service, "DEVICE_LIMIT_OVERRIDES", rules):
            first_lite = tariff_service.get_tariff_for_user(565660788, tariff_service.get_tariff_by_code("lite"))
            second_demo = tariff_service.get_tariff_for_user(824142682, tariff_service.get_tariff_by_code("promo"))
            second_lite = tariff_service.get_tariff_for_user(824142682, tariff_service.get_tariff_by_code("lite"))
            second_family = tariff_service.get_tariff_for_user(824142682, tariff_service.get_tariff_by_code("family"))

        self.assertEqual((first_lite.devices, first_lite.price_rub), (3, 129))
        self.assertEqual((second_demo.devices, second_demo.price_rub), (2, 50))
        self.assertEqual((second_lite.devices, second_lite.price_rub), (2, 129))
        self.assertEqual((second_family.devices, second_family.price_rub), (5, 279))


if __name__ == "__main__":
    unittest.main()