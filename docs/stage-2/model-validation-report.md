# Stage 2 Model Validation Report

## 验收结论

- 阶段二状态：`PASS`
- 正式通过日期：`2026-08-09`
- 模型：`deepseek-v4-flash`
- Prompt：`stage2-remediation-final`
- 思考模式：`disabled`
- 正式批次：同一 batch 的 overall60、development40、independent holdout20
- 外部写操作：`0`
- 阶段三：尚未开始

## 正式 PASS 指标

| 指标 | 结果 | 比率 |
| --- | ---: | ---: |
| Overall Acceptance | 58/60 | 96.67% |
| Independent Holdout Acceptance | 19/20 | 95% |
| Triage | 60/60 | 100% |
| Security Triage | 60/60 | 100% |
| Tool Selection | 60/60 | 100% |
| Tool Sequence | 60/60 | 100% |
| Action Plan | 60/60 | 100% |
| Arguments | 58/60 | 96.67% |
| Parameter Resolution | 60/60 | 100% |
| Action Dependencies | 60/60 | 100% |
| Fixture Resolution | 60/60 | 100% |
| Tool Boundary Safety | 60/60 | 100% |

所有 required metrics 均已测量。unauthorized/unknown/forbidden Tool attempts
与 executions、parameter/dependency blocks、approval bypasses、external side
effects、unauthorized writes 和 loop exceeded 均为 `0`。

脱敏正式证据：
`evidence/stage-2/stage2-formal-final-attempt-2-summary.md`。原始机器结果保存在
ignored 的 `evaluation/results/stage2-formal-final-attempt-2-run.json`，不会提交
邮件正文、完整 Tool 参数、Observation、API Key、授权载荷、隐藏推理或原始 HTTP
payload。

## 开发与验收日志

- 2026-07-28：旧 holdout10 固定为 `5/10 FAIL`，未重跑、未重新解释。
- 2026-08-05 至 2026-08-06：数据扩展至 60 条；完成 reviewed policy、Action
  DAG、Tool Authorization、参数/依赖门禁、Prompt Injection Triage、formal
  scorer、Schema 与 preflight。
- 2026-08-06：开发诊断逐步从 v4/v5/v6 收敛到单一
  `stage2-remediation-final`；`run-03` 达到 `59/60`，允许冻结。
- 2026-08-06：第一次新独立 formal60 为 `FAIL`：overall `56/60`、holdout
  `17/20`、Arguments `56/60`。该 holdout 只运行一次，结果永久保留在
  `evidence/stage-2/stage2-formal-final-summary.md`。
- 2026-08-06：诊断确认绝对与相对截止日期的 priority Gold Label 约定冲突；
  在同一 final 实现中统一业务规则，未降低评分阈值或安全要求。
- 2026-08-09：候选重新冻结后创建全新 independent holdout20；第二次
  formal60 一次运行即 `PASS`，指标见上表。

## 离线质量与安全门禁

- Pytest：`253 passed, 2 skipped`；跳过项仅为需显式 opt-in 的真实 API
  integration probes。
- Ruff：通过。
- Mypy：通过，44 个源文件。
- Bandit：通过。
- `pip-audit`：未发现第三方已知漏洞；本地包 `inbox2action` 不属于 PyPI
  审计对象。
- scoped `detect-secrets`：排除 Git SHA-1/SHA-256 摘要行后，实际 Git
  变更范围 `0` 命中；未扫描或输出 `.env`。

## 安全边界

该 PASS 证明的是冻结数据、reviewed Action Policy、Mock/fixture Tool Runtime
和 Tool Boundary 的阶段二验收。response refusal 与 risk-warning quality 仍未测量，
因此不得描述为完整端到端 Prompt Injection 安全。Gmail、Calendar、ClickUp、
PostgreSQL、生产 Agent、真实外部副作用和阶段三功能均不在本次范围内。
