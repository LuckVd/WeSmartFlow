"""Regression tests for the phase-one HTTP API foundation."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.contracts import ApiRequest
from api.errors import DomainError, install_api_foundation
from api.request_context import get_request_id


class Payload(ApiRequest):
    topic: str = Field(min_length=1, max_length=40)


class ApiFoundationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        install_api_foundation(self.app)

        @self.app.get("/health", operation_id="test_health")
        async def health():
            return {"request_id": get_request_id()}

        @self.app.post("/payload", operation_id="test_payload")
        async def payload(body: Payload):
            return {"topic": body.topic}

        @self.app.get("/domain-error", operation_id="test_domain_error")
        async def domain_error():
            raise DomainError(
                status_code=409,
                code="job_already_running",
                title="任务正在运行",
                detail="请等待当前任务结束后再试。",
            )

        @self.app.get("/http-error", operation_id="test_http_error")
        async def http_error():
            raise HTTPException(404, "没有该资源")

        @self.app.get("/unexpected", operation_id="test_unexpected")
        async def unexpected():
            raise RuntimeError("provider token must not reach the client")

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def assert_problem(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(
            response.headers["content-type"].split(";")[0],
            "application/problem+json",
        )
        body = response.json()
        self.assertEqual(body["status"], status)
        self.assertEqual(body["code"], code)
        self.assertEqual(body["request_id"], response.headers["x-request-id"])
        self.assertIn("detail", body)
        self.assertIn("retryable", body)
        return body

    def test_assigns_and_echoes_safe_request_ids(self):
        created = self.client.get("/health")
        self.assertEqual(created.status_code, 200)
        request_id = created.headers["x-request-id"]
        self.assertRegex(request_id, r"^req_[0-9a-f]{32}$")
        self.assertEqual(created.json()["request_id"], request_id)

        provided = "web-flow_20260922"
        echoed = self.client.get("/health", headers={"X-Request-ID": provided})
        self.assertEqual(echoed.headers["x-request-id"], provided)
        self.assertEqual(echoed.json()["request_id"], provided)

        unsafe = self.client.get("/health", headers={"X-Request-ID": "bad id"})
        self.assertRegex(unsafe.headers["x-request-id"], r"^req_[0-9a-f]{32}$")

    def test_validation_is_a_safe_problem_document(self):
        response = self.client.post("/payload", json={"topic": "", "unknown": True})
        body = self.assert_problem(response, 422, "validation_error")
        self.assertTrue(body["extensions"]["errors"])
        self.assertNotIn("unknown", body["detail"])

    def test_domain_http_and_unknown_errors_share_the_envelope(self):
        self.assert_problem(
            self.client.get("/domain-error"), 409, "job_already_running"
        )
        self.assert_problem(self.client.get("/http-error"), 404, "resource_not_found")
        body = self.assert_problem(
            self.client.get("/unexpected"), 500, "internal_error"
        )
        self.assertNotIn("provider token", body["detail"])
        self.assertTrue(body["retryable"])

    def test_openapi_has_unique_explicit_operation_ids(self):
        schema = self.client.get("/openapi.json").json()
        operation_ids = []
        for path_item in schema["paths"].values():
            for method, operation in path_item.items():
                if method in {"get", "post", "put", "patch", "delete"}:
                    operation_ids.append(operation.get("operationId"))
        self.assertNotIn(None, operation_ids)
        self.assertEqual(len(operation_ids), len(set(operation_ids)))


if __name__ == "__main__":
    unittest.main()


class ImmersiveContractTests(unittest.TestCase):
    def setUp(self):
        from dependencies import get_current_user
        from routers.immersive import router

        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
        install_api_foundation(self.app)
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: "test-user"
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_job_control_validation_and_openapi_contract(self):
        response = self.client.post("/api/immersive/jobs/cancel", json={})
        self.assertEqual(response.status_code, 422, response.text)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        self.assertEqual(body["request_id"], response.headers["x-request-id"])

        schema = self.client.get("/openapi.json").json()
        operation = schema["paths"]["/api/immersive/jobs/cancel"]["post"]
        self.assertEqual(operation["operationId"], "cancel_immersive_job")
        self.assertIn("JobControlResponse", str(operation["responses"]["200"]))
        self.assertIn("ProblemDetails", str(operation["responses"]["422"]))

    def test_cors_preflight_has_request_id(self):
        response = self.client.options(
            "/api/immersive/jobs/cancel",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("x-request-id", response.headers)
        self.assertEqual(
            response.headers["access-control-allow-origin"], "http://localhost:5173"
        )
