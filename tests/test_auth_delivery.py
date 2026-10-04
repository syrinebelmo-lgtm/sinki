import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import serve  # noqa: E402


class AuthDeliveryTests(unittest.TestCase):
    def test_signup_without_resend_uses_supabase_otp(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE": "test"}, clear=False), \
             patch.object(serve, "has_resend_key", return_value=False), \
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
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE": "test"}, clear=False), \
             patch.object(serve, "has_resend_key", return_value=False), \
             patch.object(serve.local_auth, "otp_send_status", return_value=(False, 0)), \
             patch.object(serve.local_auth, "email_has_account", return_value=True), \
             patch.object(serve, "gotrue_user_exists", return_value=True), \
             patch.object(serve, "send_supabase_otp_mail") as send, \
             patch.object(serve.local_auth, "mark_pending_external"), \
             patch.object(serve.local_auth, "record_otp_send"):
            result = serve.send_login_code({"email": "old@example.com", "mode": "login"})
        self.assertTrue(result["ok"])
        send.assert_called_once_with("old@example.com", create_user=False)

    def test_resend_preferred_over_gotrue(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE": "test"}, clear=False), \
             patch.object(serve, "has_resend_key", return_value=True), \
             patch.object(serve, "running_on_render", return_value=True), \
             patch.object(serve.local_auth, "otp_send_status", return_value=(False, 0)), \
             patch.object(serve.local_auth, "email_has_account", return_value=True), \
             patch.object(serve, "gotrue_user_exists", return_value=True), \
             patch.object(serve, "send_supabase_otp_mail") as gotrue_send, \
             patch.object(serve.local_auth, "request_code", return_value="123456") as request_code, \
             patch.object(serve, "send_sinki_mail", return_value=(True, "")), \
             patch.object(serve.local_auth, "record_otp_send") as record:
            result = serve.send_login_code({"email": "old@example.com", "mode": "login"})
        self.assertTrue(result["ok"])
        gotrue_send.assert_not_called()
        request_code.assert_called_once()
        record.assert_called_once()

    def test_gotrue_rate_limit_maps_to_two_minute_message(self):
        err = urllib_error_429()
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE": "test"}, clear=False), \
             patch.object(serve, "has_resend_key", return_value=False), \
             patch.object(serve.local_auth, "otp_send_status", return_value=(False, 0)), \
             patch.object(serve.local_auth, "email_has_account", return_value=True), \
             patch.object(serve, "gotrue_user_exists", return_value=True), \
             patch.object(serve, "send_supabase_otp_mail", side_effect=err), \
             patch.object(serve.local_auth, "record_otp_send") as record:
            with self.assertRaises(ValueError) as ctx:
                serve.send_login_code({"email": "old@example.com", "mode": "login"})
        self.assertIn("2 minutes", str(ctx.exception))
        record.assert_not_called()

    def test_failed_send_does_not_record_rate_stamp(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE": "test"}, clear=False), \
             patch.object(serve, "has_resend_key", return_value=True), \
             patch.object(serve, "running_on_render", return_value=True), \
             patch.object(serve.local_auth, "otp_send_status", return_value=(False, 0)), \
             patch.object(serve.local_auth, "email_has_account", return_value=True), \
             patch.object(serve, "gotrue_user_exists", return_value=True), \
             patch.object(serve.local_auth, "request_code", return_value="123456"), \
             patch.object(serve, "send_sinki_mail", return_value=(False, "fail")), \
             patch.object(serve.local_auth, "record_otp_send") as record:
            with self.assertRaises(ValueError):
                serve.send_login_code({"email": "old@example.com", "mode": "login"})
        record.assert_not_called()


def urllib_error_429():
    import io
    import urllib.error

    body = b'{"error_code":"over_email_send_rate_limit","msg":"email rate limit exceeded","code":429}'
    return urllib.error.HTTPError(
        "https://example.supabase.co/auth/v1/otp",
        429,
        "Too Many Requests",
        {"Content-Type": "application/json"},
        io.BytesIO(body),
    )


if __name__ == "__main__":
    unittest.main()
