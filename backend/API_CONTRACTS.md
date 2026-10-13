# WeSmartFlow API 契约规范

本规范从第一阶段开始适用于所有新接口；已有 `/api/*` 接口按领域逐步迁移，避免破坏 Web 与小程序客户端。

## HTTP 约定

- 资源接口保留在 `/api/*`；完成迁移后新增重大版本进入 `/api/v1/*`。
- 每个新接口都声明 `operation_id`、请求模型、成功 `response_model` 和标准错误响应。
- 所有响应带 `X-Request-ID`。客户端可以传入合法的 `X-Request-ID` 以串联自己的日志。
- 请求模型继承 `api.contracts.ApiRequest`：剥除首尾空格、拒绝未知字段。
- 成功模型继承 `ApiResponse`；命令型成功响应优先使用 `SuccessResponse` 或领域专用响应。

## 错误格式

所有 HTTP 错误统一为 `ProblemDetails`：

```json
{
  "type": "https://api.wesmartflow.local/problems/validation_error",
  "code": "validation_error",
  "title": "请求参数不合法",
  "status": 422,
  "detail": "请检查请求字段后重试。",
  "request_id": "req_...",
  "retryable": false,
  "extensions": { "errors": [] }
}
```

业务代码应抛出 `DomainError`；不再用 HTTP 200 表达失败。第三方原始错误、密钥和堆栈只写服务端日志。

## SSE 与异步任务

SSE 和 Job 契约属于第二阶段。第一阶段保持现有事件字段兼容；新事件可逐步补充 `request_id`、`job_id` 和 `sequence`。

## 外部供应商调用

所有会产生外部 API 请求的新能力通过领域工厂或
`services.provider_gateway` 接入。工厂继续负责用户配置、额度检查和
用量记账；Gateway 负责以下与供应商无关的横切约定：

- 在 registry 中声明 provider ID、能力、超时与重试安全性；配置不携带或记录密钥；
- 解析 `PROVIDER_<PROVIDER>_*` 覆盖（如 `..._TIMEOUT_SECONDS`）；已有 `LLM_*` 配置继续兼容；
- 记录 provider、operation、scene、request_id、时长、尝试次数和安全的失败分类；
- 只为明确幂等的调用重试。搜索可重试瞬态网络失败；图像和语音生成禁止网关盲重试，防止重复计费；
- SDK/协议细节仍留在具体 provider 客户端中，不允许业务服务直接创建 HTTP 客户端或读取供应商密钥。

## 迁移门槛

新增或迁移接口必须具备：

1. 限定的请求字段与长度/枚举校验；
2. 显式成功响应模型；
3. `operation_id` 与 OpenAPI 错误文档；
4. 对 401、422 及至少一个业务失败的契约测试；
5. 不改变既有 Web、小程序的成功字段和状态码，除非同步发布客户端迁移。
