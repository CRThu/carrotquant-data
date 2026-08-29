# CarrotQuant.Data (cq.data) Python SDK 全量指南

本文档提供 `cq.data` Python SDK 的全量 API 清单、方法签名、详细参数说明、返回值规范与常用代码示例。

---

## 1. SDK 设计原则与快速入门

`cq.data` SDK 为量化研究员与 Python 开发者提供极简、类型安全、高性能的数据接入能力。

### 核心特性
1. **OOP 便捷访问 (`cq.data.ashare.kline.get()`)**：提供具象化表格类与极致 IDE 自动补全，默认支持 `freq="1d"`, `adj="raw"`。
2. **三层链式默认继承 (`cq.data.default`)**：支持表级 > 市场级 > 全局级默认配置继承。
3. **统一切片读取 (`cq.data.read`)**：一个经典底层函数切片读取 K 线时序与板块事件数据，自动智能路由处理分支。
4. **统一探查 (`cq.data.list_tables` 等)**：开箱即用的本地已持久化数据表、格式、代码列表、时间范围与 Schema 查询。
5. **原生 Polars 高级性能**：基础返回类型均为 `polars.DataFrame`，原生支持内存投影、快速过滤与链式表达式处理。

---

## 2. API 概览与总表

```python
import cq.data
```

| API 分类 | 访问路径 / 函数 | 简要说明 |
| :--- | :--- | :--- |
| **OOP 便捷读取** | `cq.data.ashare.kline.get()` | 快捷读取 A 股个股 K 线 (默认 `freq="1d"`, `adj="raw"`) |
| | `cq.data.aindex.kline.get()` | 快捷读取 A 股指数 K 线 (默认 `freq="1d"`, 固定 `raw`) |
| | `cq.data.ashare.adj_factor.get()` | 快捷读取 A 股复权因子 |
| | `cq.data.ashare.concept.get()` | 快捷读取概念板块成分股 |
| | `cq.data.ashare.industry.get()` | 快捷读取行业板块成分股 |
| | `cq.data.ashare.dragon_tiger.get()` | 快捷读取龙虎榜统计数据 |
| | `cq.data.ashare.inst_trade.get()` | 快捷读取机构买卖每日统计数据 |
| **链式默认配置** | `cq.data.default` / `cq.data.ashare.default` | 三层链式默认值对象 (表级 > 市场级 > 全局) |
| **数据切片与探查** | `cq.data.read()` | 统一切片读取金融数据（自动按 `table_id` 智能路由） |
| | `cq.data.list_tables()` | 列出本地所有已存在的数据表及其 `category` 分类 |
| | `cq.data.list_formats()` | 查询某数据表在本地已有的存储格式 (`parquet`, `csv`) |
| | `cq.data.list_symbols()` | 查询某数据表在本地已存储的代码列表 |
| | `cq.data.get_time_range()` | 获取某数据表的全局时间跨度 `(start_dt, end_dt)` |
| | `cq.data.get_schema()` | 获取某数据表的 Schema 列名与类型字典 |
| | `cq.data.get_row_count()` | 获取某数据表在物理存储中的记录总行数 |
| **同步与全局配置** | `cq.data.sync()` | 触发全自动增量/全量同步引擎 |
| | `cq.data.configure()` | 显式从 YAML 配置文件装载全局配置 |
| | `cq.data.settings` | 全局 Settings 实例 (可直接访问与修改属性) |

> [!TIP]
> **数据字典与字段速查**：各数据表支持的具体字段清单、数据类型定义及各数据源（TDX / Baostock / EastMoney）特化列对照，请参阅专门的 [数据字典与 Schema 全量规范 (Schema Reference)](schema_reference.md)。

---

## 3. 全量 API 详尽参数与返回值说明

### 3.1 OOP 便捷访问层 API

#### 3.1.1 `cq.data.ashare.kline.get()`

读取 A 股个股 K 线数据。

```python
df = cq.data.ashare.kline.get(
    freq="1d",
    adj="raw",
    symbols=None,
    start_date=None,
    end_date=None,
    columns=None,
    source=None,
    format=None
)
```

- **参数说明 (Args)**:
  - `freq` (`str`, 可选): K 线频率，默认 `"1d"`。支持 `"1d"` (日线), `"5m"` (5分钟线), `"1m"` (1分钟线)。
  - `adj` (`str`, 可选): 复权方式，默认 `"raw"` (不复权)。支持 `"raw"`, `"adj"` (后复权)。
  - `symbols` (`str` 或 `List[str]`, 可选): 代码或代码列表 (例如 `"sh.600000"` 或 `["sh.600000", "sz.000001"]`)。为 `None` 时读取该表全量代码。
  - `start_date` (`str`, 可选): 起始日期，格式 `"YYYY-MM-DD"` (例如 `"2024-01-01"`)。
  - `end_date` (`str`, 可选): 结束日期，格式 `"YYYY-MM-DD"` (例如 `"2024-06-30"`)。
  - `columns` (`List[str]`, 可选): 选挑投影字段列表 (例如 `["timestamp", "close", "volume"]`)。
  - `source` (`str`, 可选): 显式指定数据源 (如 `"baostock"`, `"tdx"`)。若未指定则由 `DefaultConfig` 继承链决定。
  - `format` (`str`, 可选): 存储格式 (如 `"parquet"`, `"csv"`, `"auto"`)。若未指定由 `DefaultConfig` 继承链决定。
- **返回值 (Returns)**:
  - `pl.DataFrame`: 包含时间戳与 K 线指标的 Polars DataFrame。
- **说明**:
  - 若拼装出的组合不受底层数据源支持（例如 `freq="1d", adj="adj", source="tdx"`），会自动抛出 `ValueError`。

---

#### 3.1.2 `cq.data.aindex.kline.get()`

读取 A 股指数 K 线数据 (指数无复权，固定 `raw`)。

```python
df = cq.data.aindex.kline.get(
    freq="1d",
    symbols=None,
    start_date=None,
    end_date=None,
    columns=None,
    source=None,
    format=None
)
```

- **参数说明 (Args)**:
  - `freq` (`str`, 可选): K 线频率，默认 `"1d"`。
  - `symbols` (`str` 或 `List[str]`, 可选): 指数代码或代码列表 (例如 `"sh.000001"`)。
  - `start_date`, `end_date`, `columns`, `source`, `format`: 含义同上。
- **返回值 (Returns)**:
  - `pl.DataFrame`

---

#### 3.1.3 `cq.data.ashare.adj_factor.get()`

读取 A 股个股后复权因子数据。

```python
df = cq.data.ashare.adj_factor.get(
    symbols=None,
    start_date=None,
    end_date=None,
    columns=None,
    source=None,
    format=None
)
```

- **参数说明 (Args)**: 同上。
- **返回值 (Returns)**: `pl.DataFrame`

---

#### 3.1.4 `cq.data.ashare.concept.get()` / `industry.get()` / `dragon_tiger.get()` / `inst_trade.get()`

读取 A 股概念板块成分股、行业板块成分股、龙虎榜统计与机构交易数据。

```python
df_concept = cq.data.ashare.concept.get(symbols=None, start_date=None, end_date=None, columns=None)
df_industry = cq.data.ashare.industry.get(symbols=None, start_date=None, end_date=None, columns=None)
df_lhb = cq.data.ashare.dragon_tiger.get(symbols=None, start_date=None, end_date=None, columns=None)
df_inst = cq.data.ashare.inst_trade.get(symbols=None, start_date=None, end_date=None, columns=None)
```

- **参数说明 (Args)**: 同上。
- **返回值 (Returns)**: `pl.DataFrame`

---

#### 3.1.5 `cq.data.default` / `cq.data.ashare.default` / `cq.data.ashare.kline.default`

三层链式默认值配置对象。

```python
cq.data.default.source = "tdx"                      # 1. 全局默认
cq.data.ashare.default.source = "baostock"           # 2. 市场级默认
cq.data.ashare.kline.default.source = "tdx"          # 3. 表级默认
```

- **属性说明**:
  - `.source`: 配置数据源 (`"baostock"`, `"eastmoney"`, `"tdx"`)。
  - `.format`: 配置持久化存储格式 (`"parquet"`, `"csv"`)。

---

### 3.2 统一切片读取与元数据探查 API

#### 3.2.1 `cq.data.read()`

经典底层统一切片读取入口，自动按 `table_id` 智能路由到时序表或事件表流水线。

```python
df = cq.data.read(
    table_id="ashare.kline.1d.raw.baostock",
    symbols=["sh.600000"],
    start_date="2024-01-01",
    end_date="2024-06-30",
    columns=["timestamp", "close"],
    format="auto"
)
```

- **参数说明 (Args)**:
  - `table_id` (`str`, 必填): 完整数据表 ID (如 `"ashare.kline.1d.raw.baostock"`)。
  - `symbols` (`str` 或 `List[str]`, 可选): 股票/指数代码清单。
  - `start_date` (`str`, 可选): 起始日期 `"YYYY-MM-DD"`。
  - `end_date` (`str`, 可选): 结束日期 `"YYYY-MM-DD"`。
  - `columns` (`List[str]`, 可选): 选挑字段列表。
  - `format` (`str`, 可选): 指定存储格式，默认 `"auto"` (自动优先选择 Parquet)。若本地未找到元数据则抛出 `FileNotFoundError`。
- **返回值 (Returns)**:
  - `pl.DataFrame`

---

#### 3.2.2 `cq.data.list_tables()`

列出本地物理存储中已存在的全量数据表及其分类信息。

```python
tables = cq.data.list_tables(format="auto")
```

- **参数说明 (Args)**:
  - `format` (`str`, 可选): 探查特定格式 (`"auto"`, `"parquet"`, `"csv"`)。
- **返回值 (Returns)**:
  - `List[Dict[str, str]]`: 例如 `[{"table_id": "ashare.kline.1d.raw.baostock", "category": "timeseries"}, ...]`

---

#### 3.2.3 `cq.data.list_formats()`

查询某表在本地已有的物理存储格式列表。

```python
formats = cq.data.list_formats(table_id="ashare.kline.1d.raw.baostock")
```

- **参数说明 (Args)**:
  - `table_id` (`str`, 必填): 数据表 ID。
- **返回值 (Returns)**:
  - `List[str]`: 例如 `["parquet", "csv"]`

---

#### 3.2.4 `cq.data.list_symbols()`

查询某表在本地已存储的证券代码列表。

```python
symbols = cq.data.list_symbols(table_id="ashare.kline.1d.raw.baostock", format="auto")
```

- **参数说明 (Args)**:
  - `table_id` (`str`, 必填): 数据表 ID。
  - `format` (`str`, 可选): 格式。
- **返回值 (Returns)**:
  - `List[str]`: 例如 `["sh.600000", "sz.000001", ...]`

---

#### 3.2.5 `cq.data.get_time_range()`

获取某表的全局起止 ISO 时间跨度元组。

```python
start_dt, end_dt = cq.data.get_time_range("ashare.kline.1d.raw.baostock")
```

- **参数说明 (Args)**:
  - `table_id` (`str`, 必填): 数据表 ID。
  - `format` (`str`, 可选): 格式。
- **返回值 (Returns)**:
  - `Tuple[str, str]`: 例如 `("2024-01-01T15:00:00.000+08:00", "2024-06-30T15:00:00.000+08:00")`

---

#### 3.2.6 `cq.data.get_schema()`

获取某表在元数据中记载的列名与数据类型映射字典。

```python
schema = cq.data.get_schema("ashare.kline.1d.raw.baostock")
```

- **参数说明 (Args)**:
  - `table_id` (`str`, 必填): 数据表 ID。
  - `format` (`str`, 可选): 格式。
- **返回值 (Returns)**:
  - `Dict[str, str]`: 例如 `{"timestamp": "Int64", "datetime": "String", "close": "Float64"}`

---

#### 3.2.7 `cq.data.get_row_count()`

获取某表在物理存储中的记录总行数。

```python
total_rows = cq.data.get_row_count("ashare.kline.1d.raw.baostock")
```

- **参数说明 (Args)**:
  - `table_id` (`str`, 必填): 数据表 ID。
  - `format` (`str`, 可选): 格式。
- **返回值 (Returns)**:
  - `int`: 物理存储总行数 (例如 `13570685`)。

---

### 3.3 数据同步与全局配置 API

#### 3.3.1 `cq.data.sync()`

触发全自动化增量/全量同步流水线。

```python
cq.data.sync(
    table_ids="ashare.kline.1d.raw.baostock",
    formats="parquet",
    start_date="2024-01-01",
    end_date="2024-06-30",
    force_refresh=False,
    batch_size=100,
    symbol_limit=None,
    provider_kwargs=None
)
```

- **参数说明 (Args)**:
  - `table_ids` (`str` 或 `List[str]`, 必填): 单个表 ID 或表 ID 列表。
  - `formats` (`str` 或 `List[str]`, 可选): 落地格式 (`"parquet"`, `"csv"`, 或两者列表)。
  - `start_date` (`str`, 可选): 起始日期 `"YYYY-MM-DD"`。
  - `end_date` (`str`, 可选): 结束日期 `"YYYY-MM-DD"`。
  - `force_refresh` (`bool`, 可选): 是否强制全量覆盖刷新水位线，默认 `False`。
  - `batch_size` (`int`, 可选): 批处理聚合长度，默认 `100`。
  - `symbol_limit` (`int`, 可选): 限制抓取证券数量 (常用于测试测试)。
  - `provider_kwargs` (`dict`, 可选): 传递给底层 Provider 的专属选项。
- **返回值 (Returns)**:
  - 同步结果说明对象/状态。

---

#### 3.3.2 `cq.data.configure()`

显式从指定 YAML 配置文件装载全局 Settings 参数。

```python
cq.data.configure("./config.yaml")
```

- **配置文件格式参考 ([config.yaml.sample](file:///d:/Quant/CarrotQuant.Data/config/config.yaml.sample))**:
  ```yaml
  data_dir: "data"       # 数据存储根路径
  log_dir: "logs"        # 日志输出目录
  log_level: "INFO"      # 日志输出级别

  defaults:              # OOP 访问层全局默认值
    source: "baostock"
    format: "parquet"
  ```

- **参数说明 (Args)**:
  - `config_path` (`str` 或 `Path`, 必填): YAML 配置文件路径。
- **返回值 (Returns)**:
  - `Settings`: 更新后的全局 Settings 单例对象。

---

#### 3.3.3 `cq.data.settings`

全局 Settings 单例实例对象，提供程序化属性访问与修改。

```python
# 1. 动态查看属性
print(cq.data.settings.data_dir)
print(cq.data.settings.log_level)

# 2. 动态修改属性
cq.data.settings.data_dir = "/path/to/my_data"
cq.data.settings.log_level = "DEBUG"
```

- **常用属性 (Attributes)**:
  - `data_dir` (`str`): 本地持久化数据存储根目录 (默认 `"data"`)。
  - `log_dir` (`str`): 日志存放目录 (默认 `"logs"`)。
  - `log_level` (`str`): 控制台与文件日志输出级别 (默认 `"INFO"`)。
  - `defaults` (`dict`): 加载的 YAML 默认配置字典。

---

## 4. 常见场景使用示例

### 4.1 策略开发快捷读取数据 (使用 OOP 层)

```python
import cq.data

# 读取 A 股日线数据
df_kline = cq.data.ashare.kline.get(
    symbols=["sh.600000", "sz.000001"],
    start_date="2024-01-01",
    end_date="2024-06-30",
    columns=["timestamp", "datetime", "symbol", "close", "volume"]
)
print(df_kline)

# 读取概念板块成分股
df_concept = cq.data.ashare.concept.get()
print(df_concept)
```

### 4.2 转换为 Pandas DataFrame

由于 SDK 返回的标准类型均为 Polars DataFrame，如需在传统 Pandas 策略中使用，可直接调用 `.to_pandas()`：

```python
import cq.data

df_pandas = cq.data.ashare.kline.get(symbols="sh.600000").to_pandas()
print(type(df_pandas))  # <class 'pandas.core.frame.DataFrame'>
```

---

## 5. 异常处理与报错规约

SDK 中的读取、探查与配置操作均遵循标准的 Python 异常体系：

- **`ValueError`**: 输入了非法的参数组合或拼装出了底层驱动不支持的表 ID（例如试图用通达信驱动读取后复权数据 `ashare.kline.1d.adj.tdx`）。
- **`FileNotFoundError`**: 指定的数据表在本地物理存储中不存在，或调用的 `cq.data.configure("not_exist.yaml")` 路径无效。
- **数据源退市股票特性**: 通达信 `tdx` 驱动的 `online` (TCP 在线) 模式因云端 API 限制仅覆盖在交易股票；若需拉取或研究已退市股票历史数据，建议使用 Baostock 驱动（`source="baostock"`）或通达信 `local` 离线模式（`mode="local"`）。
