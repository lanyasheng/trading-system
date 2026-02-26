# 交易机器人盯盘架构 V2（设计文档）

## 0. 文档目标与范围

本文档定义盯盘系统 V2 的目标架构、可靠性策略与迁移路径，覆盖 A 股/美股/商品三类市场数据接入、评分计算、告警输出与观测治理。重点解决以下问题：
- 数据源不稳定导致误判或漏判
- 多市场字段不统一导致策略复用困难
- 抓取频率提升后触发限流/封禁风险
- 评分模型迭代后缺乏可回放验证
- 线上质量缺乏可量化 SLI/SLO 与分级告警

---

## 1) 分层架构与职责边界

### 1.1 总体分层

1. **接入层（Connector Layer）**
   - 职责：对接行情/财务/新闻/宏观等外部数据源。
   - 输出：标准化前的原始数据（Raw Payload）+ 元数据（source, ts, latency, status）。

2. **标准化层（Normalize Layer）**
   - 职责：字段映射、单位换算、时区统一、缺失值规则处理。
   - 输出：统一市场数据模型（Unified Market Record）。

3. **质量层（DQS Layer）**
   - 职责：完整性、一致性、新鲜度、异常值检测；生成 DQS 分数和风险标签。
   - 输出：`record + dqs_score + dqs_flags + degrade_hint`。

4. **缓存与分发层（Cache & Distribution Layer）**
   - 职责：L1/L2 缓存管理、热冷分层、批量读取聚合。
   - 输出：低延迟可消费数据流（Snapshot/Window）。

5. **策略与评分层（Strategy & Scoring Layer）**
   - 职责：执行信号计算、风险过滤、评分模型；支持版本化。
   - 输出：`score_result(versioned)`、候选信号、解释字段。

6. **执行与通知层（Action Layer）**
   - 职责：触发盯盘事件、推送告警、写入审计日志。
   - 输出：告警事件、回放数据、可追踪链路 ID。

7. **可观测与治理层（Observability & Governance）**
   - 职责：指标、日志、追踪、SLO 评估、熔断状态管理。
   - 输出：仪表盘、告警、周报。

### 1.2 职责边界原则
- 接入层**不做业务判断**，只保证“拿到数据并带来源信息”。
- 评分层**不直接访问外部源**，必须通过标准化+质量层输入。
- 告警层**不重算评分**，仅消费已版本化结果。
- 任何降级决策必须通过 DQS 层统一出口，避免各模块自行降级导致行为不一致。

---

## 2) DQS 与降级策略

### 2.1 DQS（Data Quality Score）组成
建议 0~100 分，按权重聚合：
- 完整性（Completeness）30%
- 新鲜度（Freshness）25%
- 一致性（Cross-source Consistency）25%
- 异常值稳定性（Outlier Stability）20%

### 2.2 分级阈值
- **A 级（>=85）**：正常使用，允许全量策略。
- **B 级（70~84）**：谨慎使用，启用保守权重。
- **C 级（50~69）**：降级运行，禁用高频/高敏感策略。
- **D 级（<50）**：熔断关键策略，仅保留基础监控与提示。

### 2.3 降级动作矩阵
- Freshness 超时：切换最近有效快照 + 标注 `stale=true`。
- 单源异常：启用多源仲裁（多数一致 + 主源信誉优先）。
- 多源冲突：回退到上一窗口稳定值（EWMA/中位数）。
- DQS 连续 N 次低于阈值：触发局部熔断并告警。

---

## 3) 数据源抽象接口（A股/美股/商品统一字段）

### 3.1 抽象接口定义

```ts
interface MarketDataProvider {
  providerId: string;
  market: 'CN_EQ' | 'US_EQ' | 'COMMODITY';
  capabilities: string[];

  fetchSnapshot(symbols: string[], asOf?: string): Promise<UnifiedQuote[]>;
  fetchBars(symbol: string, interval: '1m'|'5m'|'1d', start: string, end: string): Promise<UnifiedBar[]>;
  fetchFundamentals(symbol: string, period: string): Promise<UnifiedFundamental | null>;
}
```

### 3.2 统一字段（核心）
- 标识：`symbol`, `market`, `exchange`, `asset_type`
- 行情：`price`, `open`, `high`, `low`, `close_prev`, `volume`, `turnover`
- 时间：`ts_exchange`, `ts_utc`, `trading_session`
- 货币与单位：`currency`, `price_scale`, `volume_unit`
- 质量：`source`, `source_latency_ms`, `dqs_score`, `stale`

### 3.3 市场差异处理
- A 股：涨跌停、午间休市、复权口径。
- 美股：盘前盘后、夏令时、拆股/分红调整。
- 商品：主连/次连、合约换月、最小变动价位。
统一通过 `market_profile` 与 `instrument_meta` 驱动，不在策略代码里写硬编码分支。

---

## 4) 缓存策略（L1/L2, TTL, 热冷分层）

### 4.1 分层设计
- **L1（进程内内存）**：毫秒级访问，适合热 symbols。
- **L2（Redis/本地KV）**：跨进程共享，承接回源压力。
- **冷层（对象存储/时序库）**：历史回放与审计。

### 4.2 TTL 建议
- 实时快照：3~10 秒
- 1m Bar：60~120 秒
- 日线/财务：1 天~1 周
- 合约元数据：按交易日刷新

### 4.3 热冷分层策略
- 热集：近 24h 高频访问前 20% 标的（命中优先驻留 L1）。
- 温集：普通关注池（L2 主存）。
- 冷集：低频标的（按需加载 + 预热）。

### 4.4 一致性策略
- `cache-aside + write-through metadata`。
- 关键字段写入时附带 `version + ts`，防止旧数据覆盖新数据。

---

## 5) 批量抓取 + 限流退避 + 熔断防封号

### 5.1 批量抓取
- 按源/市场分桶（bucket）并行。
- 单批大小动态调整（根据近 5 分钟失败率和 P95 延迟）。

### 5.2 限流与退避
- 令牌桶 + 并发上限双控。
- 429/5xx 触发指数退避（带抖动）：`base * 2^n + jitter`。
- 按 provider 维度隔离重试队列，避免雪崩。

### 5.3 熔断防封号
- 熔断状态：Closed / Open / Half-Open。
- Open 条件：错误率超过阈值且持续窗口超限。
- Half-Open 仅放行探针请求，成功后恢复 Closed。
- 对高风险源启用“夜间低频 + 白天动态速率”策略。

---

## 6) 评分版本化 + 回放验证

### 6.1 版本化规范
- 评分结果必须包含：`model_version`, `feature_schema_version`, `rule_pack_version`。
- 禁止无版本结果入库。

### 6.2 回放机制
- 输入冻结：保存当时 `record + dqs + market_profile`。
- 逻辑冻结：按版本加载评分器。
- 输出对比：新旧版本在同一回放集上比较命中率、误报率、稳定性。

### 6.3 发布门禁
- 新版本需通过：
  - 离线回放通过阈值（例如 F1 / Precision 提升或不退化）
  - 在线灰度（5% → 20% → 50% → 100%）
  - 回滚开关可在 1 分钟内生效

---

## 7) SLI/SLO 与告警规则

### 7.1 核心 SLI
- 数据新鲜度：`freshness_lag_seconds`
- 抓取成功率：`fetch_success_rate`
- 标准化失败率：`normalize_error_rate`
- DQS 合格率：`dqs_pass_rate`
- 评分时延：`score_latency_p95`
- 告警有效率：`alert_precision_proxy`（可用人工标注或后验信号近似）

### 7.2 SLO（示例）
- 实时标的 freshness P95 < 8s
- 抓取成功率 >= 99.0%（5m 窗口）
- 评分链路 P95 < 500ms
- DQS>=70 占比 >= 97%

### 7.3 告警分级
- **P0**：全局不可用、关键源全熔断、评分链路中断 > 2 分钟
- **P1**：核心市场数据显著降级、误报激增、SLO 连续违约
- **P2**：局部源异常、单策略降级、缓存命中率下降

告警应包含：影响范围、起始时间、当前降级级别、建议动作、回滚/恢复入口。

---

## 8) P0 / P1 / P2 落地计划

### P0（1~2 周）— 先保命
- 建立统一 `MarketDataProvider` 抽象与字段模型
- 接入 DQS 最小可用版（完整性+新鲜度）
- 上线 L1/L2 缓存与基础 TTL
- 完成限流、指数退避、基础熔断
- 建立最小 SLI 看板（成功率/时延/新鲜度）

### P1（2~4 周）— 可运营
- DQS 扩展一致性与异常值检测
- 评分版本化元数据落库 + 回放管道
- 灰度发布与一键回滚
- 告警分级规则与值班响应手册

### P2（4~8 周）— 优化与扩展
- 热冷分层自动调参（基于访问画像）
- 多市场特性配置中心化（交易时段/单位/换月）
- 告警有效率闭环（人工反馈→策略修正）
- 成本优化（回源成本、缓存成本、延迟成本联合优化）

---

## 9) 迁移映射（monitor_v2 / us_monitor_v2 / stock_data / us_data）

### 9.1 模块迁移原则
- 先“接口对齐”再“实现替换”，避免一次性重写。
- 旧模块通过 Adapter 接入新抽象层，逐步下线。

### 9.2 映射关系

1. **monitor_v2（A股盯盘）**
   - 迁移到：`Connector(CN_EQ) + Normalize + DQS + Strategy`
   - 保留：现有规则逻辑（先封装为 `rule_pack_v1`）
   - 改造：直接数据调用改为 `MarketDataProvider.fetch*`

2. **us_monitor_v2（美股盯盘）**
   - 迁移到：`Connector(US_EQ) + Normalize + DQS + Strategy`
   - 保留：盘前盘后识别逻辑（迁入 market_profile）
   - 改造：时间与货币处理统一走标准化层

3. **stock_data（A股数据模块）**
   - 迁移到：`Connector(CN_EQ)` 主实现 + `L2 cache feeder`
   - 保留：稳定的数据源适配能力
   - 改造：输出统一字段，不再直接暴露源格式

4. **us_data（美股数据模块）**
   - 迁移到：`Connector(US_EQ)` 主实现 + 多源仲裁
   - 保留：历史数据抓取能力
   - 改造：增加 DQS 元数据与限流熔断状态回传

### 9.3 分阶段迁移路径
- Phase A：加 Adapter，不动旧调用方
- Phase B：新旧双跑，对比 DQS/评分一致性
- Phase C：切主流量至 V2，保留旧链路热备
- Phase D：下线旧直连路径，统一治理

---

## 附录：建议目录结构（示例）

```text
core/
  connector/
    cn_eq/
    us_eq/
    commodity/
  normalize/
  dqs/
  cache/
  strategy/
  scoring/
  replay/
  observability/
apps/
  monitor_v2_adapter/
  us_monitor_v2_adapter/
```

## 结语

V2 的核心不是“更多策略”，而是“先有可信数据，再做可验证决策”。通过统一抽象、质量驱动降级、版本化评分与可观测治理，系统可以在多市场扩展时保持稳定与可进化。