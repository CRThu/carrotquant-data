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
| | `cq.data.aetf.kline.get()` | 快捷读取场内基金与 ETF K 线 (支持 `freq="1m"`, 默认 `source="stockdb"`) |
| | `cq.data.aetf.adj_factor.get()` | 快捷读取场内基金与 ETF 独立复权因子 |
| | `cq.data.aindex.kline.get()` | 快捷读取 A 股指数 K 线 (默认 `freq="1d"`, 固定 `raw`) |
| | `cq.data.ashare.adj_factor.get()` | 快捷读取 A 股复权因子 |
| | `cq.data.ashare.concept.get()` | 快捷读取概念板块成分股 (支持 EastMoney / StockDB) |
| | `cq.data.ashare.industry.get()` | 快捷读取行业板块成分股 (支持 EastMoney / StockDB) |
| | `cq.data.ashare.dragon_tiger.get()` | 快捷读取龙虎榜统计数据 |
| | `cq.data.ashare.inst_trade.get()` | 快捷读取机构买卖每日统计数据 |
| **链式默认配置** | `cq.data.default` / `cq.data.ashare.default` / `cq.data.aetf.default` | 三层链式默认值对象 (表级 > 市场级 > 全局) |
| | `cq.data.ashare.kline.source` (及 `.active_source`) | 探查/修改具体表最终生效的数据源 (如 `cq.data.ashare.kline.source = "tdx"`) |
| | `cq.data.ashare.source` (及 `.active_source`) | 探查/修改市场命名空间默认数据源 (如 `cq.data.ashare.source = "stockdb"`) |
| | `cq.data.ashare.kline.supported_sources` | 自省探查具体表或市场支持的所有数据源列表 (如 `['baostock', 'stockdb', 'tdx']`) |
| **数据切片与探查** | `cq.data.read()` | 统一切片读取金融数据（自动按 `table_id` 智能路由，支持自定义表） |
| | `cq.data.write()` | 统一写入/导入数据至本地（支持时序/事件表，自动生成/更新元数据） |
| | `cq.data.register_provider()` | 注册自定义数据源 Provider 驱动扩展 |
| | `cq.data.list_sources()` | 列出系统当前已注册/支持的所有数据源驱动名称清单 |
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
> **数据字典与字段速查**：各数据表支持的具体字段清单、数据类型定义及各数据源（StockDB / TDX / Baostock / EastMoney）特化列对照，请参阅专门的 [数据字典与 Schema 全量规范 (Schema Reference)](schema_reference.md)。

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
  - `adj` (`str`, 可选): 复权方式，默认 `"raw"` (不复权)。支持 `"raw"` (不复权) 与 `"adj"` (后复权)。
    - **默认 `"raw"` (零开销纯净直读)**：不产生任何因子表 IO 与内存 Join，以最快速度直读原始行情；
    - **显式 `"adj"` (双层优先级解析与严格防御)**：
      1. *第一优先级（静态表直读）*：优先尝试直读已同步的物理静态复权表（如 `ashare.kline.1d.adj.baostock`），若存在且非空则 0 因子 IO、0 内存 Join 极速返回；
      2. *第二优先级（动态向量化折算）*：若无静态表或本地未同步，自动降级为读取底层 raw K 线与同源/权威复权因子表，按 `[symbol, date]` 向量化折算 `open`, `high`, `low`, `close` 价格列，具备完备的停牌保护、高频分钟线跨频对齐与历史短切片前向继承；
      3. *严格异常防御*：若本地未同步复权因子表，**立即抛出 `FileNotFoundError` 强类型异常明确中断**，坚决杜绝隐式静默假复权（用不复权价格假冒复权价格）。
  - `symbols` (`str` 或 `List[str]`, 可选): 代码或代码列表 (例如 `"sh.600000"` 或 `["sh.600000", "sz.000001"]`)。为 `None` 时读取该表全量代码。
  - `start_date` (`str`, 可选): 起始日期，格式 `"YYYY-MM-DD"` (例如 `"2024-01-01"`)。
  - `end_date` (`str`, 可选): 结束日期，格式 `"YYYY-MM-DD"` (例如 `"2024-06-30"`)。
  - `columns` (`List[str]`, 可选): 选挑投影字段列表 (例如 `["timestamp", "close", "volume"]`)。
  - `source` (`str`, 可选): 显式指定 K 线数据源 (如 `"stockdb"`, `"baostock"`, `"tdx"`)。若未指定则由 `DefaultConfig` 继承链决定。
  - `format` (`str`, 可选): K 线存储格式 (如 `"parquet"`, `"csv"`, `"auto"`)。若未指定由 `DefaultConfig` 继承链决定。
- **返回值 (Returns)**:
  - `pl.DataFrame`: 包含时间戳与 K 线指标的 Polars DataFrame。

---

#### 3.1.2 `cq.data.aetf.kline.get()` 与 `cq.data.aetf.adj_factor.get()`

读取场内基金与 ETF K 线行情及独立复权因子（默认回退至 `"stockdb"` 数据源，完整覆盖 1/5 号段共 2,000+ 场内基金与 ETF）。

```python
# 读取场内 ETF 1分钟或日线行情
etf_df = cq.data.aetf.kline.get(
    freq="1m",
    adj="raw",
    symbols="sz.159919",
    start_date="2025-01-02",
    end_date="2025-01-02"
)

# 动态后复权读取
etf_adj_df = cq.data.aetf.kline.get(symbols="sz.159919", adj="adj")

# 独立复权因子直读
etf_factor_df = cq.data.aetf.adj_factor.get(symbols="sz.159919")
```

---

#### 3.1.3 `cq.data.aindex.kline.get()`

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

#### 3.1.4 `cq.data.ashare.adj_factor.get()`

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

#### 3.1.5 `cq.data.ashare.concept.get()` / `industry.get()` / `dragon_tiger.get()` / `inst_trade.get()`

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

#### 3.1.6 `cq.data.default` / `cq.data.ashare.default` / `cq.data.aetf.default` (链式配置与 Fallback 机制)

三层链式默认值配置对象（专一管理底层物理存储配置与数据源路由）。

```python
cq.data.default.source = "tdx"                      # 1. 全局默认数据源
cq.data.ashare.default.source = "baostock"           # 2. A 股市场级默认数据源
cq.data.aetf.default.source = "stockdb"             # 3. 场内基金市场级默认数据源
cq.data.ashare.kline.default.format = "parquet"     # 4. 表级默认存储格式
```

##### 1. 各访问器内置 Fallback 默认值对照表

当用户未做任何手动配置时，系统自动按各资产分类的专属兜底策略（Fallback）解析：

| 访问器路径 | 类别 | 默认数据源 (`fallback_source`) | 默认存储格式 (`fallback_format`) | 说明 |
| :--- | :---: | :---: | :---: | :--- |
| `cq.data.ashare.kline` | TS | `"baostock"` | `"parquet"` | A 股个股 K 线 |
| `cq.data.ashare.adj_factor` | EV | `"baostock"` | `"parquet"` | A 股个股后复权因子 |
| `cq.data.ashare.concept` | EV | `"eastmoney"` | `"parquet"` | 概念板块成分股 |
| `cq.data.ashare.industry` | EV | `"eastmoney"` | `"parquet"` | 行业板块成分股 |
| `cq.data.ashare.dragon_tiger` | EV | `"eastmoney"` | `"parquet"` | 龙虎榜每日统计 |
| `cq.data.ashare.inst_trade` | EV | `"eastmoney"` | `"parquet"` | 机构席位交易统计 |
| `cq.data.aetf.kline` | TS | `"stockdb"` | `"parquet"` | 场内基金与 ETF K 线 |
| `cq.data.aetf.adj_factor` | EV | `"stockdb"` | `"parquet"` | 场内基金独立复权因子 |
| `cq.data.aindex.kline` | TS | `"baostock"` | `"parquet"` | 大盘指数 K 线 |
| `cq.data.default` (全局) | 全局 | `"baostock"` | `"parquet"` | 全局顶层兜底 |

##### 2. 5 级配置解析优先级（从高到低）

`resolve_source()` 与 `resolve_format()` 严格遵循以下优先级判定顺序（由高到低，先命中即生效）：

| 优先级 | 层级 | 配置方式 / 示例 | 说明 |
| :---: | :--- | :--- | :--- |
| **1** | **方法参数显式指定** | `kline.get(source="tdx", format="csv")` | 最高优先级，仅对当前单次调用生效 |
| **2** | **表级显式覆盖** | `cq.data.ashare.kline.default.source = "..."` | 用户主动设置，覆盖市场级与全局级 |
| **3** | **市场级显式覆盖** | `cq.data.ashare.default.source = "..."` | 用户主动设置，作用于整个资产大类 |
| **4** | **全局级显式覆盖** | `cq.data.default.source = "..."` / YAML 配置 | 用户主动设置，全局生效 |
| **5** | **自身专属 Fallback** | `cq.data.aetf` 默认兜底为 `"stockdb"` | 系统开箱即用的资产分类内置默认值 |
| **6** | **系统全局 Fallback** | 终极兜底为 `"baostock"` / `"parquet"` | 系统级兜底保障 |

##### 3. 动态后复权因子表探测与自动回退策略

当调用 `kline.get(adj="adj")` 执行动态后复权时，系统通过 `ProviderManager` 契约动态探查复权因子：
- **同源绑定**：若当前 K 线数据源自带因子表（如 `baostock`、`stockdb`），自动无缝绑定其同源复权因子；
- **优雅回退**：若当前 K 线数据源为纯行情源（如 `tdx`），自动回退至权威因子源（`baostock`），无需用户手动切换。

##### 4. 访问器属性与自省能力 (Self-inspection & Convenience Properties)

为了让开发者无需查阅文档即可在 Python REPL、Jupyter Notebook 或代码中快速探查、切换当前生效配置与支持的数据源，所有表访问器（如 `cq.data.ashare.kline`）与市场命名空间（如 `cq.data.ashare`）均原生提供以下自省属性：

```python
# 1. 探查当前表最终生效的数据源与格式 (由继承链动态解析)
print(cq.data.ashare.kline.active_source)    # 'baostock'
print(cq.data.ashare.kline.active_format)    # 'parquet'

# 2. 直接读取/修改当前表生效的数据源 (读返回 active_source，写等价于修改 default.source)
print(cq.data.ashare.kline.source)           # 'baostock'
cq.data.ashare.kline.source = "tdx"          # 快速切换当前表数据源为通达信
cq.data.ashare.kline.format = "csv"          # 快速切换存储格式为 csv
cq.data.ashare.kline.source = None           # 恢复继承父级/Fallback

# 3. 市场级全局快捷设置 (作用于整个 A 股命名空间)
cq.data.ashare.source = "stockdb"            # 设置 A 股市场默认数据源
print(cq.data.ashare.active_source)          # 'stockdb'
cq.data.ashare.source = None                 # 恢复

# 4. 自省当前表/市场支持的所有数据源与存储格式
print(cq.data.ashare.kline.supported_sources) # ['baostock', 'stockdb', 'tdx']
print(cq.data.ashare.concept.supported_sources) # ['eastmoney', 'stockdb']
print(cq.data.ashare.supported_sources)       # ['baostock', 'eastmoney', 'stockdb', 'tdx']
print(cq.data.aetf.supported_sources)         # ['stockdb']
print(cq.data.ashare.kline.supported_formats) # ['parquet', 'csv']

# 5. REPL / Jupyter 友好自解释输出 (__repr__)
cq.data.ashare.kline
# => <AShareKline prefix='ashare.kline', active_source='baostock', active_format='parquet', supported_sources=['baostock', 'stockdb', 'tdx'], supported_formats=['parquet', 'csv']>

cq.data.ashare
# => <AShare active_source='baostock', active_format='parquet', tables=['kline', 'adj_factor', 'concept', 'industry', 'dragon_tiger', 'inst_trade']>
```

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

#### 3.2.2 `cq.data.write()`

统一数据写入与外部数据导入接口。将外部 Polars DataFrame 规范化写入本地物理存储（Parquet / CSV）并自动生成/原子化更新 `metadata.json`。

```python
result = cq.data.write(
    table_id="custom.factor.alpha101",
    df=df,
    category="timeseries",
    formats=["parquet", "csv"],
    mode="append",
    sort_keys=None
)
```

- **参数说明 (Args)**:
  - `table_id` (`str`, 必填): 数据表 ID (如 `"my_factor"` 或 `"crypto.kline.1d.binance"`)。
  - `df` (`pl.DataFrame`, 必填): 要写入的 Polars DataFrame。
  - `category` (`str`, 可选): 数据集类别 (`"timeseries"` 或 `"event"`)，默认为 `"timeseries"`。写入纯静态平铺表时需显式传入 `"event"`。
  - `formats` (`str` 或 `List[str]`, 可选): 存储格式，默认 `"parquet"` (可选 `"parquet"`, `"csv"`, 或 `["parquet", "csv"]`)。
  - `mode` (`str`, 可选): 写入模式，默认 `"append"` (增量合并去重)。支持 `"append"` 与 `"overwrite"` (覆盖)。
  - `sort_keys` (`List[str]`, 可选): 事件表平铺模式下的自定义排序列。

- **返回值 (Returns)**:
  - `Dict[str, Any]`: 包含 `table_id`, `category`, `formats`, `rows_written`, `status` 等信息的执行结果字典。

---

#### 3.2.3 `cq.data.register_provider()`

动态注册外部自定义数据源 Provider 驱动，将其无缝接入 `cq.data.sync()` 调度流水线。支持**类装饰器**与**普通函数调用**两种写法。

**写法 1：类装饰器模式（推荐，即插即用）**

```python
import cq.data
from cq.data.provider.base import BaseProvider

@cq.data.register_provider("my_source")
class MyCustomProvider(BaseProvider):
    # 实现 fetch, get_all_symbols, get_supported_tables, get_table_category, get_sort_keys
    ...

# 定义后即可直接调度同步
cq.data.sync("custom.kline.1d.my_source")
```

**写法 2：普通函数调用模式**

```python
import cq.data
from cq.data.provider.base import BaseProvider

class MyCustomProvider(BaseProvider):
    ...

# 注册类或已实例化的对象
cq.data.register_provider("my_source", MyCustomProvider)
# 或
cq.data.register_provider("my_source", MyCustomProvider(api_key="xxx"))
```

- **参数说明 (Args)**:
  - `source` (`str`, 必填): 数据源标识符（对应 table_id 的末段标识，如 `'my_source'`）。
  - `provider` (`BaseProvider` 或 `Type[BaseProvider]`, 可选): 继承自 `BaseProvider` 的驱动类或实例。若不传（为 `None`），则返回类装饰器闭包。

---

#### 3.2.4 `cq.data.list_sources()`

获取系统当前已加载/注册的所有可用数据源驱动标识列表（包含内置数据源 `'baostock'`, `'eastmoney'`, `'tdx'`, `'stockdb'` 与外部动态注册的自定义数据源）。

```python
sources = cq.data.list_sources()
print(sources)  # ['baostock', 'eastmoney', 'tdx', 'stockdb']
```

- **返回值 (Returns)**:
  - `List[str]`: 数据源标识名称列表。

---

#### 3.2.5 `cq.data.list_tables()`

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

- **本地 `.env` 自动加载支持**:
  系统在初始化时会自动加载当前目录下的 `.env` 文件（模板见 [`.env.sample`](file:///d:/Quant/carrotquant-data/.env.sample)）：
  ```bash
  # .env
  CQDATA_DATA_DIR=D:/Quant/my_data
  CQDATA_LOG_LEVEL=DEBUG
  ```

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
