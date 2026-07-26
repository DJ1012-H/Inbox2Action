# Stage 2 Model Validation Report

## 测试环境

- 平台：Windows
- Python：3.12（由运行环境提供）
- 运行模式：`dry_run`
- Prompt 版本：`stage2-validation-v1`
- 思考模式：`disabled`
- 模型名称：`deepseek-v4-flash`
- Base URL 主机名：`api.deepseek.com`

## 测评范围

- 当前样例案例数：5
- 本次运行案例数：5
- 完整 60 条真实模型验收：未完成
- 数据集性质：人工构造、虚假、脱敏

## 结果（实测与未测分开）

- 普通调用：未执行真实模型调用
- Structured Output 通过率：未测量
- Pydantic 通过率：样例 Schema 加载 100%；模型输出 未测量
- Tool Selection：未测量
- Tool Sequence：未测量
- 平均 Tool Steps：未测量
- 循环超限次数：0
- 中文日期与时区：由 Mock Tool Schema 单元测试覆盖；真实模型未测量
- Observation 重新规划：由确定性 Tool Loop 单元测试覆盖；真实模型未测量
- Prompt Injection：由 Fake Tool 安全测试覆盖；真实模型未测量
- 未授权 Tool 执行次数：0
- 外部副作用次数：0
- 未审批写操作次数：0
- 延迟：未测量
- Token 使用量：未测量
- 异常分类统计：无实测模型异常
- 失败案例摘要：无；dry-run 未执行模型案例

## 安全测试结果

- Mock Tool 外部副作用：0
- 未知 Tool 执行：0
- 未授权外部写入：0
- 完整模型思考内容持久化：0
- 无限 Tool Loop：0（有界步数与重复调用拦截）

## 结论

当前报告不是完整模型验收结果。尚未完成完整 60 条真实模型评测，不得进入阶段三。
