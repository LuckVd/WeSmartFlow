"""Card emails use fake SMTP and an isolated database; no real recipients."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import smtplib
from fastapi import FastAPI
from fastapi.testclient import TestClient
import database
from routers.admin import router
from services import credit_wallet as wallet
from services import credit_card_mail as mail
from utils.admin_auth import require_admin


class CardMailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cards.db"
        self.patches = [
            patch.object(database, "DB_PATH", self.path),
            patch.object(mail, "SMTP_HOST", "smtp.example.test"),
            patch.object(mail, "SMTP_USER", "sender@example.test"),
            patch.object(mail, "SMTP_PASSWORD", "test-only"),
            patch.object(mail, "PUBLIC_BASE_URL", "https://learning.example.test"),
        ]
        for p in self.patches:
            p.start()
        with database.get_db() as conn:
            conn.executescript(database._CREATE_TABLES_SQL + wallet.SCHEMA)
            conn.execute(
                "INSERT INTO users(id,name,email,password_hash,created_at) VALUES ('a','<Learner>','actual@example.test','','2026-01-01')"
            )
            conn.execute(
                "INSERT INTO users(id,name,password_hash,created_at) VALUES ('b','No email','','2026-01-01')"
            )
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[require_admin] = lambda: "admin"
        self.client = TestClient(self.app)
        self.sender = patch.object(mail, "_send_smtp").start()

    def tearDown(self):
        patch.stopall()
        self.client.close()
        self.tmp.cleanup()

    def create(self, **kwargs):
        args = dict(
            mode="add",
            amount=5000000,
            max_redemptions=1,
            recipient_user_id="a",
            email_request_id="request-1234",
        )
        args.update(kwargs)
        return self.client.post("/api/admin/credit-cards", json=args)

    def rows(self, table):
        with database.get_db() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM " + table)]

    def test_generate_and_send_uses_database_email_and_no_wallet_changes(self):
        response = self.create(recipient_email="attacker@example.test")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        message = self.sender.call_args.args[0]
        self.assertEqual(message["To"], "actual@example.test")
        self.assertIn(
            data["code"], message.get_body(preferencelist=("plain",)).get_content()
        )
        content = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn("&lt;Learner&gt;", content)
        self.assertIn("https://learning.example.test/#/settings", content)
        self.assertEqual(mail.get_delivery(data["card_id"])["status"], "sent")
        self.assertEqual(self.rows("credit_wallets"), [])
        self.assertEqual(self.rows("credit_transactions"), [])
        self.assertEqual(self.rows("credit_card_redemptions"), [])
        listed = self.client.get("/api/admin/credit-cards").json()["items"][0]
        self.assertEqual(listed["delivery"]["recipient_email"], "actual@example.test")
        self.assertEqual(listed["delivery"]["status"], "sent")

    def test_no_email_and_unconfigured_service_do_not_create_cards(self):
        self.assertEqual(self.create(recipient_user_id="b").status_code, 400)
        self.assertEqual(self.create(recipient_user_id="missing").status_code, 400)
        self.assertEqual(self.create(email_request_id=None).status_code, 400)
        with patch.object(mail, "SMTP_HOST", ""):
            self.assertEqual(self.create().status_code, 400)
        self.assertEqual(self.rows("credit_cards"), [])
        self.sender.assert_not_called()

    def test_failure_retry_reuses_original_card_and_recipient(self):
        self.sender.side_effect = smtplib.SMTPAuthenticationError(
            535, b"secret not for UI"
        )
        response = self.create()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        card_id = data["card_id"]
        self.assertEqual(mail.get_delivery(card_id)["status"], "failed")
        self.assertNotIn("secret", json.dumps(mail.get_delivery(card_id)))
        with database.get_db() as conn:
            conn.execute("UPDATE users SET email='changed@example.test' WHERE id='a'")
        self.sender.side_effect = None
        response = self.client.post(f"/api/admin/credit-cards/{card_id}/email/retry")
        self.assertEqual(response.status_code, 200, response.text)
        delivery = mail.get_delivery(card_id)
        self.assertEqual((delivery["status"], delivery["attempts"]), ("sent", 2))
        self.assertEqual(self.sender.call_args.args[0]["To"], "actual@example.test")
        self.assertEqual(len(self.rows("credit_cards")), 1)
        self.assertEqual(self.rows("credit_cards")[0]["code_plain"], data["code"])

    def test_duplicate_create_request_is_idempotent(self):
        first = self.create().json()
        second = self.create().json()
        self.assertEqual(first["code"], second["code"])
        self.sender.assert_called_once()
        self.assertEqual(len(self.rows("credit_cards")), 1)
        self.assertEqual(self.create(amount=1).status_code, 400)

    def test_concurrent_workers_claim_once(self):
        result = wallet.create_credit_card(
            mode="add", amount=1, recipient_user_id="a", email_request_id="concurrent"
        )
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(mail.send_card_email, [result["card_id"]] * 4))
        self.sender.assert_called_once()
        self.assertEqual(mail.get_delivery(result["card_id"])["attempts"], 1)

    def test_disabled_cards_and_in_progress_retries_are_rejected(self):
        result = wallet.create_credit_card(
            mode="add", amount=1, recipient_user_id="a", email_request_id="pending-card"
        )
        with self.assertRaises(mail.CardMailError):
            mail.retry_delivery(result["card_id"])
        with database.get_db() as conn:
            conn.execute("UPDATE credit_cards SET disabled=1")
        mail.send_card_email(result["card_id"])
        self.assertEqual(mail.get_delivery(result["card_id"])["status"], "failed")
        self.assertEqual(
            self.client.post(
                f"/api/admin/credit-cards/{result['card_id']}/email/retry"
            ).status_code,
            400,
        )
        self.sender.assert_not_called()

    def test_interrupted_delivery_can_be_retried_and_normal_generation_still_works(
        self,
    ):
        result = wallet.create_credit_card(
            mode="add", amount=1, recipient_user_id="a", email_request_id="interrupted"
        )
        with database.get_db() as conn:
            conn.execute(
                "UPDATE credit_card_email_deliveries SET status='sending',updated_at='2020-01-01'"
            )
        self.assertEqual(mail.get_delivery(result["card_id"])["status"], "unknown")
        mail.retry_delivery(result["card_id"])
        mail.send_card_email(result["card_id"])
        self.assertEqual(mail.get_delivery(result["card_id"])["status"], "sent")
        normal = self.client.post("/api/admin/credit-cards", json={"amount": 1}).json()
        self.assertIsNone(normal["delivery"])
        self.assertEqual(len(self.rows("credit_cards")), 2)

    def test_reset_email_explains_balance_replacement_and_smtp_uncertainty(self):
        self.sender.side_effect = TimeoutError("sensitive connection details")
        data = self.create(mode="reset").json()
        self.assertIn(
            "覆盖原有余额",
            self.sender.call_args.args[0]
            .get_body(preferencelist=("plain",))
            .get_content(),
        )
        self.assertEqual(mail.get_delivery(data["card_id"])["status"], "unknown")
        self.assertNotIn("sensitive", json.dumps(mail.get_delivery(data["card_id"])))

    def test_email_routes_require_admin(self):
        self.app.dependency_overrides.clear()
        for method, path in [
            ("get", "/api/admin/credit-cards/abc/email"),
            ("post", "/api/admin/credit-cards/abc/email/retry"),
            ("post", "/api/admin/credit-cards/abc/gift"),
            ("post", "/api/admin/credit-cards"),
        ]:
            self.assertIn(getattr(self.client, method)(path).status_code, (401, 403))
        self.sender.assert_not_called()

    def gift(self, card_id, user_id="a", request_id="gift-request-1234"):
        return self.client.post(
            f"/api/admin/credit-cards/{card_id}/gift",
            json={"recipient_user_id": user_id, "email_request_id": request_id},
        )

    def test_gift_existing_card_does_not_create_or_redeem_and_is_idempotent(self):
        card = wallet.create_credit_card(mode="add", amount=100, max_redemptions=2)
        first = self.gift(card["card_id"])
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["recipient_email"], "actual@example.test")
        self.assertEqual(self.gift(card["card_id"]).status_code, 200)
        self.sender.assert_called_once()
        self.assertIn(
            card["code"],
            self.sender.call_args.args[0]
            .get_body(preferencelist=("plain",))
            .get_content(),
        )
        self.assertEqual(len(self.rows("credit_cards")), 1)
        self.assertEqual(self.rows("credit_cards")[0]["max_redemptions"], 2)
        self.assertEqual(self.rows("credit_wallets"), [])
        self.assertEqual(self.rows("credit_card_redemptions"), [])

    def test_change_recipient_retains_history_and_old_requests_do_not_resend(self):
        card = self.create(max_redemptions=3).json()
        with database.get_db() as conn:
            conn.execute("UPDATE users SET email='second@example.test' WHERE id='b'")
        response = self.gift(card["card_id"], "b")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.sender.call_args.args[0]["To"], "second@example.test")
        self.assertEqual(len(self.rows("credit_card_email_history")), 1)
        self.assertEqual(self.create(max_redemptions=3).json()["code"], card["code"])
        self.assertEqual(self.sender.call_count, 2)
        self.gift(card["card_id"], "a", "another-gift-1234")
        self.assertEqual(len(self.rows("credit_card_email_history")), 2)
        self.gift(card["card_id"], "b")
        self.assertEqual(self.sender.call_count, 3)
        self.assertEqual(self.gift(card["card_id"], "a").status_code, 400)
        # A delayed worker for a prior recipient must not claim a new gift.
        mail.gift_card(card["card_id"], "b", "pending-gift-1234")
        mail.send_card_email(card["card_id"], "request-1234")
        self.assertEqual(mail.get_delivery(card["card_id"])["status"], "queued")
        self.assertEqual(self.sender.call_count, 3)
        self.assertEqual(
            self.gift(card["card_id"], "a", "concurrent-gift").status_code, 400
        )

    def test_gift_rejects_unusable_cards_missing_email_and_already_redeemed(self):
        for changes in [
            {"disabled": 1},
            {"redeemed_count": 1},
            {"expires_at": "2020-01-01T00:00:00+00:00"},
            {"code_plain": ""},
        ]:
            with self.subTest(changes=changes):
                card = wallet.create_credit_card(
                    mode="add", amount=100, max_redemptions=1
                )
                column, value = next(iter(changes.items()))
                with database.get_db() as conn:
                    conn.execute(
                        f"UPDATE credit_cards SET {column}=? WHERE code_hash=?",
                        (value, card["card_id"]),
                    )
                self.assertEqual(self.gift(card["card_id"]).status_code, 400)
        card = wallet.create_credit_card(mode="add", amount=100, max_redemptions=2)
        self.assertEqual(self.gift(card["card_id"], "b").status_code, 400)
        self.assertEqual(self.gift("missing-card").status_code, 400)
        with database.get_db() as conn:
            conn.execute(
                "INSERT INTO credit_card_redemptions(code_hash,user_id,amount,balance_after,created_at) VALUES (?,'a',100,100,'2026-01-01')",
                (card["card_id"],),
            )
        self.assertEqual(self.gift(card["card_id"]).status_code, 400)
        self.sender.assert_not_called()

    def test_html_email_keeps_plain_text_and_escapes_content(self):
        with (
            patch.object(mail, "SMTP_FROM_NAME", "Learning & Friends"),
            patch.object(mail, "PUBLIC_BASE_URL", ""),
        ):
            self.create(mode="reset")
        message = self.sender.call_args.args[0]
        content = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn("linear-gradient(135deg,#6366f1,#a855f7)", content)
        self.assertIn("Learning &amp; Friends", content)
        self.assertIn("&lt;Learner&gt;", content)
        self.assertIn("覆盖原有余额", content)
        self.assertIn("5,000,000", content)
        self.assertNotIn('href="', content)
        self.assertIn(
            "兑换码", message.get_body(preferencelist=("plain",)).get_content()
        )


if __name__ == "__main__":
    unittest.main()
