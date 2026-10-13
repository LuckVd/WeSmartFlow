"""Offline wallet, migration, concurrency and OAuth reward regression tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import database
from services import credit_wallet as wallet
from services import credit_quota, usage_meter, github_reward
from migrate_credit_wallet import migrate


def at(month, day=1):
    return datetime(2026, month, day, 0, 0, tzinfo=timezone.utc)


class WalletTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "wallet.db"
        self.patches = [
            patch.object(database, "DB_PATH", self.path),
            patch.object(credit_quota, "CREDITS_ENFORCEMENT_ENABLED", True),
            patch.object(credit_quota, "get_setting", return_value=""),
        ]
        for p in self.patches:
            p.start()
        with database.get_db() as conn:
            conn.executescript(database._CREATE_TABLES_SQL + wallet.SCHEMA)
            conn.execute(
                "INSERT INTO users(id,name,password_hash,created_at,github_id) VALUES ('a','A','x','2025-01-01','123')"
            )
            conn.execute(
                "INSERT INTO users(id,name,password_hash,created_at,github_id) VALUES ('b','B','x','2025-01-01','456')"
            )

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def spend(self, user_id, amount, event_id="one", now=None):
        with database.get_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            wallet.debit(conn, user_id, amount, event_id, now)

    def entries(self, kind):
        with database.get_db() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM credit_transactions WHERE kind=?", (kind,)
                )
            ]

    def test_signup_exactly_once_and_next_month_only(self):
        self.assertEqual(wallet.balance("a", at(1)), 5_000_000)
        self.spend("a", 2_000_000, now=at(1))
        self.assertEqual(wallet.balance("a", at(1, 31)), 3_000_000)
        self.assertEqual(wallet.balance("a", at(2)), 4_000_000)
        self.assertEqual(wallet.balance("a", at(2, 20)), 4_000_000)
        self.assertEqual(len(self.entries("signup")), 1)
        self.assertEqual(len(self.entries("monthly")), 1)

    def test_monthly_cap_and_catchup(self):
        wallet.balance("a", at(1))
        self.spend("a", 400_000, now=at(1))
        self.assertEqual(wallet.balance("a", at(2)), 5_000_000)
        self.assertEqual(self.entries("monthly")[0]["amount"], 400_000)
        self.spend("a", 4_500_000, "two", at(2))
        self.assertEqual(wallet.balance("a", at(6)), 4_500_000)
        self.assertEqual(wallet.balance("a", at(12)), 5_000_000)

    def test_capped_months_are_not_claimed_again_after_spending(self):
        wallet.balance("a", at(1))
        wallet.balance("a", at(2))
        self.spend("a", 1_000_000, now=at(2))
        self.assertEqual(wallet.balance("a", at(2, 20)), 4_000_000)
        self.assertEqual(wallet.balance("a", at(3)), 5_000_000)

    def test_github_bonus_can_exceed_cap_and_only_once(self):
        self.assertTrue(wallet.grant_github("a", "123"))
        self.assertFalse(wallet.grant_github("a", "123"))
        self.assertEqual(wallet.balance("a"), 10_000_000)
        future = datetime(2028, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(wallet.balance("a", future), 10_000_000)
        with self.assertRaises(ValueError):
            wallet.grant_github("b", "123")
        # A GitHub ID cannot earn twice even if an account is later relinked.
        with database.get_db() as conn:
            conn.execute("UPDATE users SET github_id=NULL WHERE id='a'")
            conn.execute("UPDATE users SET github_id='123' WHERE id='b'")
        self.assertFalse(wallet.grant_github("b", "123"))
        self.assertEqual(wallet.balance("b"), 5_000_000)

    def test_concurrent_grants_and_debits(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            granted = list(
                pool.map(lambda _: wallet.grant_github("a", "123"), range(12))
            )
        self.assertEqual(sum(granted), 1)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: self.spend("a", 10_000, str(n)), range(20)))
        self.assertEqual(wallet.balance("a"), 9_800_000)
        self.assertEqual(len(self.entries("usage")), 20)

    def test_duplicate_debit_and_transaction_rollback(self):
        wallet.balance("a")
        self.spend("a", 100, "same")
        self.spend("a", 100, "same")
        self.assertEqual(wallet.balance("a"), 4_999_900)
        with self.assertRaises(RuntimeError):
            with database.get_db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                wallet.debit(conn, "a", 1000, "rollback")
                raise RuntimeError("rollback")
        self.assertEqual(wallet.balance("a"), 4_999_900)

    def test_usage_is_atomic_with_wallet_and_own_keys_excluded(self):
        usage_meter.record_usage("a", credits=100, counts_quota=True)
        usage_meter.record_usage("a", credits=200, counts_quota=False)
        usage_meter.record_usage("a", credits=300, is_system=True)
        self.assertEqual(wallet.balance("a"), 4_999_900)
        self.assertEqual(usage_meter.get_period_credits("a"), 100)
        self.assertEqual(len(self.entries("usage")), 1)

    def test_zero_and_negative_balance_block_but_personal_key_works(self):
        self.spend("a", 5_100_000)
        with self.assertRaises(credit_quota.CreditsExceeded):
            credit_quota.assert_available("a", platform_key=True)
        credit_quota.assert_available("a", platform_key=False)
        self.assertEqual(credit_quota.get_remaining("a"), 0)
        self.assertEqual(wallet.balance("a"), -100_000)

    def test_old_users_migration_does_not_charge_old_usage(self):
        with database.get_db() as conn:
            conn.execute("INSERT INTO usage_summary VALUES ('a','2026-01',9000000,10)")
        migrate()
        migrate()
        self.assertEqual(wallet.balance("a"), 5_000_000)
        self.spend("a", 500)
        migrate()
        self.assertEqual(wallet.balance("a"), 4_999_500)
        self.assertEqual(len(self.entries("signup")), 2)

    def test_github_204_404_failure_and_retry(self):
        from integrations.http import IntegrationHttpError

        for outcome in [False, IntegrationHttpError("GitHub unavailable")]:
            client = MagicMock()
            if isinstance(outcome, Exception):
                client.has_starred.side_effect = outcome
            else:
                client.has_starred.return_value = outcome
            result = github_reward.verify_and_grant(
                "a", "123", "fake-token", client=client
            )
            self.assertIn(result["status"], ("not_starred", "unavailable"))
            self.assertEqual(len(self.entries("github_star")), 0)
        client = MagicMock()
        client.has_starred.return_value = True
        self.assertEqual(
            github_reward.verify_and_grant("a", "123", "fake-token", client=client)[
                "status"
            ],
            "granted",
        )
        self.assertEqual(
            github_reward.verify_and_grant("a", "123", "fake-token", client=client)[
                "status"
            ],
            "already_claimed",
        )

    def test_oauth_state_one_use_and_expiry(self):
        from fastapi import HTTPException

        with patch.object(github_reward, "GITHUB_CLIENT_ID", "test"):
            state = github_reward.authorize("a", "reward")["state"]
            self.assertEqual(github_reward.consume_state(state)["user_id"], "a")
            with self.assertRaises(HTTPException):
                github_reward.consume_state(state)
            state = github_reward.authorize("a", "reward")["state"]
            with database.get_db() as conn:
                conn.execute(
                    "UPDATE github_oauth_states SET expires_at=0 WHERE nonce=?",
                    (state,),
                )
            with self.assertRaises(HTTPException):
                github_reward.consume_state(state)

    def test_email_registration_and_login_only_grant_once(self):
        import time
        from routers import auth

        email = "wallet-test@example.com"
        ids = []
        for _ in range(2):
            auth._verification_codes[email] = {
                "code": "123456",
                "expires_at": time.time() + 60,
                "attempts": 0,
            }
            result = auth.verify_code(
                auth.VerifyCodeRequest(email=email, code="123456")
            )
            ids.append(result.user_id)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(wallet.balance(ids[0]), 5_000_000)
        self.assertEqual(len(self.entries("signup")), 1)

    def test_wechat_registration_and_login_only_grant_once(self):
        from routers import auth

        client = MagicMock()
        client.exchange_code.return_value = "wallet-test-openid"
        with (
            patch.object(auth, "WECHAT_MP_APPID", "test"),
            patch.object(auth, "WECHAT_MP_SECRET", "test"),
            patch.object(auth, "get_wechat_client", return_value=client),
        ):
            a = auth.wechat_mp_login(auth.WechatMpLoginRequest(code="test"))
            b = auth.wechat_mp_login(auth.WechatMpLoginRequest(code="test"))
        self.assertEqual(a.user_id, b.user_id)
        self.assertEqual(wallet.balance(a.user_id), 5_000_000)
        self.assertEqual(len(self.entries("signup")), 1)

    def test_github_registration_receives_signup_and_star_bonus_once(self):
        from routers import auth

        client = MagicMock()
        client.exchange_code.return_value = "test-token"
        client.current_user.return_value = {
            "id": 789,
            "login": "new",
            "name": "New",
            "email": "github-wallet@example.com",
        }
        client.has_starred.return_value = True

        with (
            patch.object(auth, "GITHUB_CLIENT_ID", "test"),
            patch.object(auth, "GITHUB_CLIENT_SECRET", "test"),
            patch.object(github_reward, "GITHUB_CLIENT_ID", "test"),
            patch.object(auth, "get_github_client", return_value=client),
        ):
            results = []
            for _ in range(2):
                state = github_reward.authorize()["state"]
                results.append(
                    auth.github_callback(
                        auth.GitHubCallbackRequest(code="test", state=state)
                    )
                )
        self.assertEqual(results[0].user_id, results[1].user_id)
        self.assertEqual(wallet.balance(results[0].user_id), 10_000_000)
        self.assertEqual(len(self.entries("signup")), 1)
        self.assertEqual(len(self.entries("github_star")), 1)

    def test_month_boundary_beijing_and_concurrent_refill(self):
        last = datetime(2026, 1, 31, 15, 59, tzinfo=timezone.utc)
        first = datetime(2026, 1, 31, 16, 0, tzinfo=timezone.utc)
        self.spend("a", 5_000_000, now=last)
        with ThreadPoolExecutor(max_workers=8) as pool:
            balances = list(pool.map(lambda _: wallet.balance("a", first), range(8)))
        self.assertEqual(set(balances), {1_000_000})
        self.assertEqual(len(self.entries("monthly")), 1)

    def test_email_account_binding_callback_keeps_owner_and_email(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from dependencies import create_access_token
        from routers import auth

        with database.get_db() as conn:
            conn.execute(
                "UPDATE users SET github_id=NULL,email='original@example.com' WHERE id='a'"
            )
        app = FastAPI()
        app.include_router(auth.router)
        client = TestClient(app)
        client_adapter = MagicMock()
        client_adapter.exchange_code.return_value = "fake"
        client_adapter.current_user.return_value = {
            "id": 789,
            "login": "new",
            "email": "different@example.com",
        }
        client_adapter.has_starred.return_value = True

        with (
            patch.object(auth, "GITHUB_CLIENT_ID", "test"),
            patch.object(auth, "GITHUB_CLIENT_SECRET", "test"),
            patch.object(github_reward, "GITHUB_CLIENT_ID", "test"),
            patch.object(auth, "get_github_client", return_value=client_adapter),
        ):
            self.assertIn(
                client.get("/api/auth/github/reward/authorize").status_code, (401, 403)
            )
            for _ in range(2):
                started = client.get(
                    "/api/auth/github/reward/authorize",
                    headers={"Authorization": "Bearer " + create_access_token("a")},
                )
                self.assertEqual(started.status_code, 200, started.text)
                result = client.post(
                    "/api/auth/github/callback",
                    json={"code": "fake", "state": started.json()["state"]},
                )
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()["user_id"], "a")
        self.assertEqual(wallet.balance("a"), 10_000_000)
        self.assertEqual(len(self.entries("github_star")), 1)
        with database.get_db() as conn:
            user = conn.execute(
                "SELECT email,github_id FROM users WHERE id='a'"
            ).fetchone()
            self.assertEqual(tuple(user), ("original@example.com", "789"))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2
            )

    def test_binding_cannot_take_another_accounts_github(self):
        from fastapi import HTTPException

        with database.get_db() as conn:
            conn.execute("UPDATE users SET github_id=NULL WHERE id='a'")
        with self.assertRaises(HTTPException) as error:
            github_reward.bind_account("a", "456", "other")
        self.assertEqual(error.exception.status_code, 409)
        with database.get_db() as conn:
            self.assertIsNone(
                conn.execute("SELECT github_id FROM users WHERE id='a'").fetchone()[0]
            )
            self.assertEqual(
                conn.execute("SELECT github_id FROM users WHERE id='b'").fetchone()[0],
                "456",
            )
        self.assertEqual(len(self.entries("github_star")), 0)

    def test_concurrent_binding_only_one_owner(self):
        from fastapi import HTTPException

        with database.get_db() as conn:
            conn.execute("UPDATE users SET github_id=NULL")

        def bind(user_id):
            try:
                github_reward.bind_account(user_id, "789", "new")
                return True
            except HTTPException as error:
                self.assertEqual(error.status_code, 409)
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(bind, ["a", "b"])), 1)

    def test_reward_callback_rejects_wrong_github_account(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers import auth

        app = FastAPI()
        app.include_router(auth.router)
        with (
            patch.object(github_reward, "GITHUB_CLIENT_ID", "test"),
            patch.object(auth, "GITHUB_CLIENT_ID", "test"),
            patch.object(auth, "GITHUB_CLIENT_SECRET", "secret"),
        ):
            state = github_reward.authorize("a", "reward")["state"]
            client_adapter = MagicMock()
            client_adapter.exchange_code.return_value = "fake-token"
            client_adapter.current_user.return_value = {
                "id": 456,
                "login": "b",
                "email": "b@example.com",
            }
            with (
                patch.object(auth, "get_github_client", return_value=client_adapter),
            ):
                response = TestClient(app).post(
                    "/api/auth/github/callback", json={"code": "test", "state": state}
                )
                self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(len(self.entries("github_star")), 0)


if __name__ == "__main__":
    unittest.main()
