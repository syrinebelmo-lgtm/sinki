import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import serve  # noqa: E402


class AuthDeliveryTests(unittest.TestCase):
    def test_signup_without_resend_uses_supabase_otp(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE": "test"}), \
             patch.object(serve.local_auth, "otp_send_status", return_value=(False, 0)), \
             patch.object(serve.local_auth, "email_has_account", return_value=False), \
             patch.object(serve.local_auth, "pseudo_taken", return_value=False), \
             patch.object(serve, "gotrue_user_exists", return_value=False), \
             patch.object(serve, "send_supabase_otp_mail") as send, \
             patch.object(serve.local_auth, "mark_pending_external") as pending, \
             patch.object(serve.local_auth, "record_otp_send"):
            result = serve.send_login_code({"email": "new@example.com", "mode": "signup", "nick": "New"})
        self.assertTrue(result["ok"])
        send.assert_called_once_with("new@example.com", create_user=True)
        pending.assert_called_once_with("new@example.com", "gotrue")

    def test_existing_login_does_not_create_auth_user(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE": "test"}), \
             patch.object(serve.local_auth, "otp_send_status", return_value=(False, 0)), \
             patch.object(serve.local_auth, "email_has_account", return_value=True), \
             patch.object(serve, "gotrue_user_exists", return_value=True), \
             patch.object(serve, "send_supabase_otp_mail") as send, \
             patch.object(serve.local_auth, "mark_pending_external"), \
             patch.object(serve.local_auth, "record_otp_send"):
            result = serve.send_login_code({"email": "old@example.com", "mode": "login"})
        self.assertTrue(result["ok"])
        send.assert_called_once_with("old@example.com", create_user=False)


if __name__ == "__main__":
    unittest.main()
