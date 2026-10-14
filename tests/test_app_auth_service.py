import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services.app_auth_service import AppAuthService


class AppAuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cosmonet.db"
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()
        database.init_db()
        self.service = AppAuthService()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_approved_session_is_single_use(self):
        session = self.service.create_login_session(
            device_id="device-1", device_name="PC", platform="windows"
        )
        self.assertTrue(self.service.approve_session(
            session_id=session["sessionId"], telegram_id=1001, display_name="User"
        ))

        first = self.service.get_status(
            device_id="device-1", session_id=session["sessionId"]
        )
        second = self.service.get_status(
            device_id="device-1", session_id=session["sessionId"]
        )

        self.assertTrue(first["isAuthorized"])
        self.assertTrue(first["authToken"])
        self.assertFalse(second["isAuthorized"])
        self.assertFalse(second["isPending"])


if __name__ == "__main__":
    unittest.main()
