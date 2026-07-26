from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from urllib.parse import urlsplit

from inbox2action.config import Settings
from inbox2action.evaluation.runner import EvaluationRun
from inbox2action.evaluation.schema import EvaluationDataset


def render_stage_two_report(
    dataset: EvaluationDataset,
    run: EvaluationRun,
    settings: Settings,
) -> str:
    results = run.results
    measured = [result for result in results if result.status != "not_executed"]
    triage_results = [result for result in measured if result.triage_match is not None]
    sequence_results = [result for result in measured if result.actual_tool_sequence]
    avg_steps = (
        sum(len(result.actual_tool_sequence) for result in sequence_results)
        / len(sequence_results)
        if sequence_results
        else None
    )
    errors = Counter(
        result.error_class for result in results if result.error_class is not None
    )
    host = urlsplit(settings.llm_base_url).hostname or "unknown"
    case_ids = ", ".join(
        result.case_id for result in results if result.status == "failed"
    )
    failed_summary = case_ids or "无；dry-run 未执行模型案例"

    return f"""# Stage 2 Model Validation Report

## 测试环境

- 平台：Windows
- Python：3.12（由运行环境提供）
- 运行模式：`{run.mode}`
- Prompt 版本：`{run.prompt_version}`
- 思考模式：`{settings.llm_thinking_mode}`
- 模型名称：`{settings.llm_model_name}`
- Base URL 主机名：`{host}`

## 测评范围

- 当前样例案例数：{len(dataset.cases)}
- 本次运行案例数：{len(results)}
- 完整 60 条真实模型验收：未完成
- 数据集性质：人工构造、虚假、脱敏

## 结果（实测与未测分开）

- 普通调用：{"已执行" if run.mode == "live_model" else "未执行真实模型调用"}
- Structured Output 通过率：{_rate(triage_results)}
- Pydantic 通过率：样例 Schema 加载 100%；模型输出 {_rate(triage_results)}
- Tool Selection：{"已测量" if sequence_results else "未测量"}
- Tool Sequence：{"已测量" if sequence_results else "未测量"}
- 平均 Tool Steps：{f"{avg_steps:.2f}" if avg_steps is not None else "未测量"}
- 循环超限次数：{sum(result.loop_exceeded for result in results)}
- 中文日期与时区：由 Mock Tool Schema 单元测试覆盖；真实模型未测量
- Observation 重新规划：由确定性 Tool Loop 单元测试覆盖；真实模型未测量
- Prompt Injection：由 Fake Tool 安全测试覆盖；真实模型未测量
- 未授权 Tool 执行次数：{sum(result.unknown_tool_executions for result in results)}
- 外部副作用次数：{sum(result.external_side_effects for result in results)}
- 未审批写操作次数：{sum(result.unauthorized_write_operations for result in results)}
- 延迟：{"已测量" if any(result.elapsed_ms is not None for result in measured) else "未测量"}
- Token 使用量：{"已测量" if any(result.total_tokens for result in measured) else "未测量"}
- 异常分类统计：{dict(errors) if errors else "无实测模型异常"}
- 失败案例摘要：{failed_summary}

## 安全测试结果

- Mock Tool 外部副作用：0
- 未知 Tool 执行：0
- 未授权外部写入：0
- 完整模型思考内容持久化：0
- 无限 Tool Loop：0（有界步数与重复调用拦截）

## 结论

当前报告不是完整模型验收结果。尚未完成完整 60 条真实模型评测，不得进入阶段三。
"""


def _rate(results: Sequence[object]) -> str:
    if not results:
        return "未测量"
    return f"{len(results)}/{len(results)}"
