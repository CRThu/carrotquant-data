# CarrotQuant.Data 全量数据表字典与 Schema 规范

本文档为 `CarrotQuant.Data` (`cqdata`) 的全局数据字典与字段权威定义（Single Source of Truth, SSOT）。
供 Python SDK (`cq.data.read`, `cq.data.ashare.*`)、RESTful API (`/api/v1/query`) 以及前端数据面板查阅字段定义、数据类型及各数据源（TDX / Baostock / EastMoney）特化差异。

---

## 1. 全量 16 个内置数据表总览索引 (Master Index)

| 数据表 ID (`table_id`) | 数据表名称 | 类别 (`category`) | 数据源 | 频率与复权 | 分片存储策略 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `ashare.kline.1d.raw.baostock` | Baostock A股个股日线 (不复权) | `timeseries` | Baostock | 1d, raw | `[symbol, year]` 分片 |
| `ashare.kline.1d.adj.baostock` | Baostock A股个股日线 (后复权) | `timeseries` | Baostock | 1d, adj | `[symbol, year]` 分片 |
| `ashare.kline.5m.raw.baostock` | Baostock A股个股 5 分钟线 (不复权) | `timeseries` | Baostock | 5m, raw | `[symbol, year]` 分片 |
| `ashare.kline.5m.adj.baostock` | Baostock A股个股 5 分钟线 (后复权) | `timeseries` | Baostock | 5m, adj | `[symbol, year]` 分片 |
| `aindex.kline.1d.raw.baostock` | Baostock 大盘指数日线 (不复权) | `timeseries` | Baostock | 1d, raw | `[symbol, year]` 分片 |
| `ashare.adj_factor.baostock` | Baostock A股后复权因子表 | `event` | Baostock | 事件驱动 | 按年 / 全量事件 |
| `ashare.kline.1d.raw.tdx` | 通达信 A股个股日线 (不复权) | `timeseries` | TDX | 1d, raw | `[symbol, year]` 分片 |
| `ashare.kline.5m.raw.tdx` | 通达信 A股个股 5 分钟线 (不复权) | `timeseries` | TDX | 5m, raw | `[symbol, year]` 分片 |
| `ashare.kline.1m.raw.tdx` | 通达信 A股个股 1 分钟线 (不复权) | `timeseries` | TDX | 1m, raw | `[symbol, year]` 分片 |
| `aindex.kline.1d.raw.tdx` | 通达信 大盘指数日线 (不复权) | `timeseries` | TDX | 1d, raw | `[symbol, year]` 分片 |
| `aindex.kline.5m.raw.tdx` | 通达信 大盘指数 5 分钟线 (不复权) | `timeseries` | TDX | 5m, raw | `[symbol, year]` 分片 |
| `aindex.kline.1m.raw.tdx` | 通达信 大盘指数 1 分钟线 (不复权) | `timeseries` | TDX | 1m, raw | `[symbol, year]` 分片 |
| `ashare.concept.eastmoney` | 东方财富 概念板块与成分股映射 | `event` | EastMoney | 事件/快照 | 平铺 / 单表 |
| `ashare.industry.eastmoney` | 东方财富 行业板块与成分股映射 | `event` | EastMoney | 事件/快照 | 平铺 / 单表 |
| `ashare.dragon_tiger.eastmoney` | 东方财富 龙虎榜每日明细统计 | `event` | EastMoney | 按日事件 | `[year]` 分片 |
| `ashare.inst_trade.eastmoney` | 东方财富 机构席位交易每日统计 | `event` | EastMoney | 按日事件 | `[year]` 分片 |

---

## 2. 核心设计规范与通用字段基准

### 2.1 命名与类型标准化原则
所有数据源在落盘和对外暴露前，已由数据清洗层（`DataCleaner`）强制完成归一化：
1. **代码标准化 (`symbol`)**：统一带市场小写前缀（如 `sh.600000`, `sz.000001`, `bj.830000`）。
2. **时序三件套 (`timestamp`, `datetime`, `date`)**：
   - `timestamp` (`pl.Int64`)：UTC 毫秒时间戳，物理时序主键与排序列。
   - `datetime` (`pl.String`)：带本地时区偏移的 ISO 8601 标准时间字符串（如 `2024-01-03T15:00:00.000+08:00`）。
   - `date` (`pl.String`)：业务日期字符串（`YYYY-MM-DD`）。
3. **价格与量能物理量纲规范**：价格保留 2~4 位小数，金额统一以人民币“元”为单位，成交量统一以“股”为单位。

---

## 3. K 线时序数据表 (TimeSeries Tables)

### 3.1 跨数据源通用基准字段 (Baseline)
无论底层数据源使用 **通达信 (TDX)** 还是 **Baostock**，以下字段保证 **同名、同类型、100% 存在**：

| 字段名 | Polars / Arrow 类型 | REST JSON 类型 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- | :--- |
| **`symbol`** | `pl.String` | `string` | 证券代码（含市场小写前缀） | `"sh.600000"` |
| **`datetime`** | `pl.String` | `string` | ISO 8601 带时区标准时间 | `"2024-01-03T15:00:00.000+08:00"` |
| **`timestamp`** | `pl.Int64` | `number` | UTC 毫秒时间戳 | `1704265200000` |
| **`date`** | `pl.String` | `string` | 业务日期 (YYYY-MM-DD) | `"2024-01-03"` |
| **`open`** | `pl.Float64` | `number` | 开盘价 (元) | `6.82` |
| **`high`** | `pl.Float64` | `number` | 最高价 (元) | `6.95` |
| **`low`** | `pl.Float64` | `number` | 最低价 (元) | `6.80` |
| **`close`** | `pl.Float64` | `number` | 收盘价 (元) | `6.90` |
| **`volume`** | `pl.Float64` | `number` | 成交量 (股) | `35284000.0` |
| **`amount`** | `pl.Float64` | `number` | 成交额 (元) | `242681500.0` |

---

### 3.2 数据源附加扩展字段 (Extended Fields by Source)

通用 K 线数据源默认均包含 3.1 节中的 10 个标准基础字段。若使用具备衍生数据能力的特定数据源，将在基准字段之上额外提供如下扩展列：

#### 3.2.1 Baostock 日线附加扩展字段 (`ashare.kline.1d.*.baostock`)
除通用基准字段外，Baostock 日线表额外包含以下 9 个基本面与行情衍生字段：

| 字段名 | 类型 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- |
| `preclose` | `pl.Float64` | 前收盘价 (元) | `6.85` |
| `change_pct` | `pl.Float64` | 当日涨跌幅（百分比，如 `1.5` 代表 `+1.5%`） | `0.73` |
| `turnover_rate` | `pl.Float64` | 换手率（百分比，如 `0.85` 代表 `0.85%`） | `0.42` |
| `trade_status` | `pl.String` | 交易状态（`"1"`: 正常交易, `"0"`: 停牌） | `"1"` |
| `is_st` | `pl.String` | 是否 ST 风险警示标的（`"1"`: 是, `"0"`: 否） | `"0"` |
| `pe_ttm` | `pl.Float64` | 滚动市盈率 (TTM) | `12.45` |
| `pb_mrq` | `pl.Float64` | 市净率 (MRQ) | `1.15` |
| `ps_ttm` | `pl.Float64` | 市销率 (TTM) | `2.31` |
| `pcf_ncf_ttm` | `pl.Float64` | 市现率 (TTM) | `8.92` |

*(注：通达信 TDX 等纯行情数据源仅包含 3.1 节的标准基准字段。后续若接入其他具备衍生能力的新数据源，将在此处按源独立追加子章节，保持结构清晰模块化。)*

---

### 3.3 分钟级高频 K 线 (`ashare.kline.5m.*`, `ashare.kline.1m.*`)
包含字段：`symbol`, `datetime`, `timestamp`, `date`, `open`, `high`, `low`, `close`, `volume`, `amount`。

---

## 4. 复权因子事件表 (`ashare.adj_factor.baostock`)

记录个股历史除权除息与分红送转事件的后复权因子序列。

| 字段名 | 类型 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- |
| **`symbol`** | `pl.String` | 证券代码 | `"sh.600000"` |
| **`date`** | `pl.String` | 除权除息生效日期 (`YYYY-MM-DD`) | `"2023-06-15"` |
| **`back_adj_factor`** | `pl.Float64` | **后复权因子** (上市首日为 1.0，每次除权累乘) | `1.5234` |
| **`datetime`** | `pl.String` | 标准时间字符串 | `"2023-06-15T00:00:00.000+08:00"` |
| **`timestamp`** | `pl.Int64` | 毫秒时间戳 | `1686787200000` |

### 4.1 各字段复权折算原则 (Adjustment Principles)
* **参与复权的价格列**：`open`, `high`, `low`, `close`, `preclose`
  - 后复权 (hfq)：$Price_{hfq} = Price_{raw} \times back\_adj\_factor$
  - 前复权 (qfq)：$Price_{qfq} = Price_{raw} \times \frac{back\_adj\_factor}{latest\_factor}$
* **严禁复权的列**：`amount` (真实成交额), `turnover_rate` (换手率), `change_pct` (涨跌幅), 估值指标及状态标记。

---

## 5. 东方财富特色事件数据表 (EastMoney Event Tables)

### 5.1 龙虎榜每日统计 (`ashare.dragon_tiger.eastmoney`)

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `symbol` | `pl.String` | 股票代码 |
| `stock_name` | `pl.String` | 股票简称 |
| `trade_date` / `date` | `pl.String` | 上榜交易日期 (`YYYY-MM-DD`) |
| `close_price` | `pl.Float64` | 当日收盘价 (元) |
| `change_rate` | `pl.Float64` | 当日涨跌幅 (%) |
| `net_amount` | `pl.Float64` | 龙虎榜买卖净差额 (元) |
| `buy_amount` | `pl.Float64` | 龙虎榜买入总额 (元) |
| `sell_amount` | `pl.Float64` | 龙虎榜卖出总额 (元) |
| `deal_amount` | `pl.Float64` | 龙虎榜席位成交总额 (元) |
| `market_amount` | `pl.Float64` | 当日该股市场总成交额 (元) |
| `deal_net_ratio` | `pl.Float64` | 龙虎榜净买额占总成交额比 (%) |
| `deal_amount_ratio` | `pl.Float64` | 龙虎榜总成交占总成交额比 (%) |
| `turnover_rate` | `pl.Float64` | 当日换手率 (%) |
| `float_market_cap` | `pl.Float64` | 当日实际流通市值 (元) |
| `explain` / `explanation` | `pl.String` | 上榜原因与席位解读（如“日涨幅偏离值达到7%的前五只证券”） |
| `day1_change_rate` | `pl.Float64` | 上榜后 1 日后验涨跌幅 (%) |
| `day2_change_rate` | `pl.Float64` | 上榜后 2 日后验涨跌幅 (%) |
| `day5_change_rate` | `pl.Float64` | 上榜后 5 日后验涨跌幅 (%) |
| `day10_change_rate` | `pl.Float64` | 上榜后 10 日后验涨跌幅 (%) |
| `datetime` / `timestamp` | - | 标准时间轴 |

---

### 5.2 机构交易每日统计 (`ashare.inst_trade.eastmoney`)

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `symbol` | `pl.String` | 股票代码 |
| `stock_name` | `pl.String` | 股票简称 |
| `close_price` | `pl.Float64` | 当日收盘价 (元) |
| `change_rate` | `pl.Float64` | 当日涨跌幅 (%) |
| `buy_times` | `pl.Int64` | 买方机构席位数 |
| `sell_times` | `pl.Int64` | 卖方机构席位数 |
| `buy_amount` | `pl.Float64` | 机构席位买入总额 (元) |
| `sell_amount` | `pl.Float64` | 机构席位卖出总额 (元) |
| `net_buy_amount` | `pl.Float64` | 机构席位净买入额 (元) |
| `market_amount` | `pl.Float64` | 市场总成交额 (元) |
| `ratio` | `pl.Float64` | 机构买卖总额占市场总成交比 (%) |
| `turnover_rate` | `pl.Float64` | 当日换手率 (%) |
| `float_market_cap` | `pl.Float64` | 当日流通市值 (元) |
| `explanation` | `pl.String` | 上榜原因说明 |
| `datetime` / `timestamp` | - | 标准时间轴 |

---

### 5.3 概念与行业板块成分股 (`ashare.concept.eastmoney` / `ashare.industry.eastmoney`)

| 字段名 | 类型 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- |
| `board_code` | `pl.String` | 板块唯一代码 | `"BK0612"` |
| `board_name` | `pl.String` | 板块名称 | `"低空经济"` |
| `symbol` | `pl.String` | 成分股代码 | `"sh.600000"` |
| `stock_name` | `pl.String` | 成分股简称 | `"浦发银行"` |
| `datetime` / `timestamp` | - | 标准时间轴 | - |

---

## 6. 指数时序数据表 (AIndex TimeSeries Tables)

涵盖大盘基准与核心指数：
- `aindex.kline.1d.raw.baostock` (Baostock 指数日线)
- `aindex.kline.1d.raw.tdx`, `aindex.kline.5m.raw.tdx`, `aindex.kline.1m.raw.tdx` (通达信指数多周期)
- 包含字段：`symbol`, `datetime`, `timestamp`, `date`, `open`, `high`, `low`, `close`, `volume`, `amount`, `turnover_rate`, `change_pct`。
- 指数行情固定为 **`raw` (不复权)**。
