# CarrotQuant.Data REST API 详细接口使用指南

`cqdata server` 提供了基于 FastAPI 的 RESTful HTTP 接口，方便 Web 前端、微服务架构与非 Python 语言客户端（如 Go, C++, Rust, Node.js, Java）快速集成金融数据同步与切片查询服务。

> [!NOTE]
> 项目内置了官方标准 React Web 前端实现（位于 `web/` 目录），基于该 REST API 提供了 TradingView 3-Pane 强同步 K 线与板块概念 0 延时穿透。详情请参阅 [React Web 终端使用指南](web_terminal_guide.md)。

---

## 1. 核心设计原则与数据响应协议

### 1.1 纯 HTTP GET 切片查询
- 所有元数据探查与数据切片查询统一使用 `HTTP GET` 请求，方便浏览器直接调试与 HTTP 缓存控制。

### 1.2 高性能 2D List 矩阵 JSON 响应协议
为了显著降低网络传输 Overhead，`GET /api/v1/query` 切片查询接口输出 **`columns` (表头一维数组)** 与 **`data` (数据二维矩阵数组)**：
- **体积优势**：与传统 KV 对象数组相比，Payload 体积减小 **50% ~ 65%**。
- **无缝集成**：可直接挂载至 Apache ECharts (`dataset.source`)、TradingView 或前端 Canvas 图表渲染引擎。

### 1.3 HTTP 状态码规范
所有 REST API 节点严格遵循 HTTP 语义化状态码分发：
- **`200 OK`**: 请求处理成功。
- **`400 Bad Request`**: 请求参数校验失败（如传入非法的参数类型、时间格式或缺少必填 Query 参数）。
- **`404 Not Found`**: 请求的数据表或元数据不存在。
- **`405 Method Not Allowed`**: 使用错误的 HTTP Method（例如用 `POST` 请求 `GET` 节点）。
- **`409 Conflict`**: 同一 `table_id` 的后台同步任务正在运行中，拒绝重复并发触发。
- **`500 Internal Server Error`**: 未捕获的服务器内部未知异常。

### 1.4 线程池并发与主事件循环 (Event Loop) 非阻塞架构
FastAPI 路由对于包含 Polars DataFrame 切片处理与磁盘文件 IO 的只读查询端点（如 `/query`, `/tables/detailed`, `/tables/{table_id}/boards`），采用标准 `def` 同步声明。
- **底层机制**：FastAPI 自动将这些同步 IO 密集型操作派发至底层的 Worker 线程池并发执行，使主事件循环（Event Loop）保持空闲与自由。
- **并发优势**：即使在进行大表数据切片读取时，系统依然能够以 `< 1ms` 的极速响应 `/health` 健康检查与 `/sync/status` 同步状态轮询，杜绝线程卡顿与网络假死。

---

## 2. API 端点全量概览表

基准 URL (Base URL): `http://<host>:<port>/api/v1`

| 分类 | 端点路径 | HTTP 方法 | 功能说明 |
| :--- | :--- | :---: | :--- |
| **前端 UI 托管** | `/` | `GET` | 内置托管的 React Web 金融终端主界面（支持 SPA 路由） |
| **系统探针** | `/health` | `GET` | 服务运行状态探针与 `data_dir` 探查 |
| | `/sources` | `GET` | 列出系统当前已加载/注册的所有数据源驱动清单及其支持的数据表列表 |
| **元数据探查** | `/tables` | `GET` | 列出本地所有数据表清单（平铺对象数组，含 `category` 分类） |
| | `/tables/detailed` | `GET` | 获取所有数据表及其各格式 (Parquet/CSV) 独立水位线与条数的详细元数据 |
| | `/tables/{table_id}/boards` | `GET` | 极速获取板块概念/行业列表及各板块成分股计数 (轻量 20KB 响应包) |
| | `/tables/{table_id}/formats` | `GET` | 获取某数据表本地拥有的格式列表 (如 `["parquet", "csv"]`) |
| | `/tables/{table_id}/symbols` | `GET` | 获取某数据表已落地的证券/代码唯一清单 |
| | `/tables/{table_id}/time_range` | `GET` | 获取某数据表覆盖的全局时间起止跨度 |
| | `/tables/{table_id}/schema` | `GET` | 获取某数据表的字段列名与 Polars/数据类型映射字典 |
| | `/tables/{table_id}/row_count` | `GET` | 获取某数据表在物理存储中的记录总条数 |
| **数据写入与导入** | `/write` | `POST` | 写入/导入自定义结构化数据，自动生成与原子化更新 `metadata.json` |
| **数据切片查询** | `/data/{market}/{category}` | `GET` | **【动态业务语义路由】** 自动识别内置访问器与外部导入表，服务端动态后复权折算 |
| | `/query` | `GET` | **【按物理表切片】** 按 `table_id` 精确路由，支持物理分页与 2D List 导出 |

| **同步任务控制** | `/sync` | `POST` | 触发后台数据全自动增量/全量同步任务 |
| | `/tasks` | `GET` | 获取当前正在后台运行的同步任务列表 |
| | `/sync/status` | `GET` | 获取全局同步任务精准进度、百分比与处理 Symbol 字典 |
| | `/sync/stream` | `GET` | **【SSE】** Server-Sent Events 任务同步进度与状态实时主动推流通道 |
| | `/logs/stream` | `GET` | **【SSE】** Server-Sent Events 全局 Loguru 系统与数据引擎日志实时推送流 |
| **文件系统探查** | `/filesystem/list` | `GET` | 通用本地文件/目录列表探查 API（为 Web 端文件浏览器 Modal 提供支持） |


> [!TIP]
> **数据字典与字段速查**：查询接口 (`GET /api/v1/query`) 中 `columns` 过滤支持的具体字段清单、数据类型定义及各数据源（TDX / Baostock / EastMoney）特化列对照，请参阅专门的 [数据字典与 Schema 全量规范 (Schema Reference)](schema_reference.md)。

---

## 3. 端点详细说明与 JSON 响应契约

### 3.1 系统健康检查 (`GET /api/v1/health`)

#### 响应 JSON 结构示例
```json
{
  "status": "ok",
  "version": "1.1.0",
  "data_dir": "D:\\Quant\\CarrotQuant.Data\\data",
  "log_dir": "D:\\Quant\\CarrotQuant.Data\\logs",
  "log_level": "INFO",
  "active_tasks": 0
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/health"
```

---

### 3.2 数据表总览探查 (`GET /api/v1/tables`)

#### 请求参数 (Query Parameters)
| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `format` | String | 否 | `"auto"` | 物理存储格式选择 (`auto`, `parquet`, `csv`) |

#### 响应 JSON 结构示例
```json
{
  "tables": [
    { "table_id": "ashare.kline.1d.raw.baostock", "category": "timeseries" },
    { "table_id": "ashare.kline.5m.raw.tdx", "category": "timeseries" },
    { "table_id": "ashare.concept.eastmoney", "category": "event" },
    { "table_id": "ashare.adj_factor.baostock", "category": "event" }
  ],
  "total": 4
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/tables?format=auto"
```

---

### 3.3 数据源清单探查 (`GET /api/v1/sources`)

获取系统当前已加载/注册的所有可用数据源驱动清单，包含各个数据源当前支持抓取与同步的完整数据表列表。

#### 响应 JSON 结构示例
```json
{
  "total": 4,
  "sources": [
    {
      "source": "baostock",
      "supported_tables": [
        "ashare.kline.1d.adj.baostock",
        "ashare.kline.1d.raw.baostock",
        "ashare.kline.5m.adj.baostock",
        "ashare.kline.5m.raw.baostock",
        "aindex.kline.1d.raw.baostock",
        "ashare.adj_factor.baostock"
      ],
      "table_count": 6
    },
    {
      "source": "eastmoney",
      "supported_tables": [
        "ashare.concept.eastmoney",
        "ashare.industry.eastmoney",
        "ashare.dragon_tiger.eastmoney",
        "ashare.inst_trade.eastmoney"
      ],
      "table_count": 4
    },
    {
      "source": "tdx",
      "supported_tables": [
        "ashare.kline.1d.raw.tdx",
        "ashare.kline.5m.raw.tdx",
        "ashare.kline.1m.raw.tdx",
        "aindex.kline.1d.raw.tdx",
        "aindex.kline.5m.raw.tdx",
        "aindex.kline.1m.raw.tdx"
      ],
      "table_count": 6
    },
    {
      "source": "stockdb",
      "supported_tables": [
        "ashare.kline.1m.raw.stockdb",
        "ashare.kline.1d.raw.stockdb",
        "ashare.adj_factor.stockdb",
        "ashare.concept.stockdb",
        "ashare.industry.stockdb",
        "aetf.kline.1m.raw.stockdb",
        "aetf.kline.1d.raw.stockdb",
        "aetf.adj_factor.stockdb"
      ],
      "table_count": 8
    }
  ]
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/sources"
```

---

### 3.4 查看表存储格式 (`GET /api/v1/tables/{table_id}/formats`)

#### 路径参数 (Path Parameters)
| 参数名 | 说明 |
| :--- | :--- |
| `table_id` | 目标表 ID，例如 `ashare.kline.1d.raw.baostock` |

#### 响应 JSON 结构示例
```json
{
  "table_id": "ashare.kline.1d.raw.baostock",
  "formats": ["parquet", "csv"]
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/tables/ashare.kline.1d.raw.baostock/formats"
```

---

### 3.4 查看表代码列表 (`GET /api/v1/tables/{table_id}/symbols`)

#### 路径与查询参数
- `table_id` (Path): 数据表 ID
- `format` (Query): 存储格式 (`auto`, `parquet`, `csv`)

#### 响应 JSON 结构示例
```json
{
  "table_id": "ashare.kline.1d.raw.baostock",
  "symbol_count": 2,
  "symbols": ["sh.600000", "sz.000001"]
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/tables/ashare.kline.1d.raw.baostock/symbols"
```

---

### 3.5 查看表时间跨度 (`GET /api/v1/tables/{table_id}/time_range`)

#### 响应 JSON 结构示例
```json
{
  "table_id": "ashare.kline.1d.raw.baostock",
  "start_datetime": "2020-01-02T15:00:00.000+08:00",
  "end_datetime": "2024-06-30T15:00:00.000+08:00"
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/tables/ashare.kline.1d.raw.baostock/time_range"
```

---

### 3.6 查看表字段 Schema (`GET /api/v1/tables/{table_id}/schema`)

#### 响应 JSON 结构示例
```json
{
  "table_id": "ashare.kline.1d.raw.baostock",
  "schema": {
    "timestamp": "Int64",
    "datetime": "String",
    "symbol": "String",
    "open": "Float64",
    "high": "Float64",
    "low": "Float64",
    "close": "Float64",
    "volume": "Float64"
  }
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/tables/ashare.kline.1d.raw.baostock/schema"
```

---

### 3.7 查看物理记录总条数 (`GET /api/v1/tables/{table_id}/row_count`)

#### 响应 JSON 结构示例
```json
{
  "table_id": "ashare.kline.1d.raw.baostock",
  "row_count": 125000
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/tables/ashare.kline.1d.raw.baostock/row_count"
```

---

### 3.8 写入/导入自定义数据 (`POST /api/v1/write`)

接收结构化 JSON 数据并写入指定的本地 Parquet 或 CSV 数据表中，自动完成字段标准化与 `metadata.json` 原子化盖章。


#### 请求 Body 参数 (JSON Payload)
| 字段名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `table_id` | String | **是** | - | 目标数据表 ID (如 `custom.factors.momentum`) |
| `data` | List[Dict] | **是** | - | 要写入的行数据对象数组 |
| `category` | String | 否 | `"timeseries"` | 数据集类别 (`timeseries` 或 `event`)，默认为 `"timeseries"` |
| `formats` | List[String] | 否 | `["parquet"]` | 目标存储格式列表 (`["parquet"]`, `["csv"]` 或 `["parquet", "csv"]`) |

| `mode` | String | 否 | `"append"` | 写入模式 (`append` 增量合并去重，`overwrite` 全量覆盖) |
| `sort_keys` | List[String] | 否 | `None` | 事件表自定义排序列 |

#### 请求 JSON 示例
```json
{
  "table_id": "custom.factors.alpha_mom",
  "category": "timeseries",
  "formats": ["parquet", "csv"],
  "mode": "append",
  "data": [
    {
      "symbol": "sh.600000",
      "timestamp": 1704067200000,
      "momentum": 1.25,
      "volatility": 0.18
    },
    {
      "symbol": "sz.000001",
      "timestamp": 1704067200000,
      "momentum": 0.95,
      "volatility": 0.22
    }
  ]
}
```

#### 响应 JSON 示例
```json
{
  "status": "success",
  "table_id": "custom.factors.alpha_mom",
  "result": {
    "table_id": "custom.factors.alpha_mom",
    "category": "timeseries",
    "formats": ["parquet", "csv"],
    "rows_written": 2,
    "status": "success"
  }
}
```

---

### 3.9 统一切片数据查询 (`GET /api/v1/query`)


后端接收到请求后，会自动判断 `table_id` 的类别（时序数据还是事件数据）并智能路由，同时支持物理分页与字段选挑（Columns Projection）。

#### 请求参数 (Query Parameters)
| 参数名 | 类型 | 是否必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `table_id` | String | **是** | - | 目标数据集 ID (如 `ashare.kline.1d.raw.baostock` 或 `ashare.concept.eastmoney`) |
| `symbols` | String | 否 | `None` | 证券代码过滤，多个代码以逗号分隔 (如 `sh.600000,sz.000001`) |
| `start_date` | String | 否 | `None` | 起始日期过滤 (`YYYY-MM-DD`) |
| `end_date` | String | 否 | `None` | 结束日期过滤 (`YYYY-MM-DD`) |
| `columns` | String | 否 | `None` | 选挑字段清单，逗号分隔 (如 `timestamp,symbol,close`) |
| `format` | String | 否 | `"auto"` | 物理存储格式 (`auto`, `parquet`, `csv`) |
| `page` | Integer | 否 | `1` | 当前页码 (从 1 开始) |
| `page_size` | Integer | 否 | `5000` | 每页物理切片条数 |

#### 响应 JSON 结构示例 (2D Matrix 矩阵)
```json
{
  "table_id": "ashare.kline.1d.raw.baostock",
  "total": 12500,
  "page": 1,
  "page_size": 5000,
  "total_pages": 3,
  "count": 5000,
  "columns": ["timestamp", "datetime", "symbol", "open", "high", "low", "close", "volume"],
  "data": [
    [1704092400000, "2024-01-01T15:00:00.000+08:00", "sh.600000", 6.62, 6.68, 6.61, 6.65, 12500000.0],
    [1704178800000, "2024-01-02T15:00:00.000+08:00", "sh.600000", 6.65, 6.72, 6.64, 6.70, 15000000.0]
  ]
}
```

#### cURL 调用示例
```bash
# 切片查询 2024年日 K 线前 100 条
curl -X GET "http://127.0.0.1:8000/api/v1/query?table_id=ashare.kline.1d.raw.baostock&symbols=sh.600000&start_date=2024-01-01&page=1&page_size=100"
```

---

### 3.10 通用动态业务语义切片查询 (`GET /api/v1/data/{market}/{category}`)

无需感知底层具体数据源物理表名（如 `ashare.kline.1d.raw.baostock`），直接按**业务功能与语义**进行切片查询。
- **内置表高阶特性自动激活**：若查询内置市场与分类（如 `ashare/kline`），自动在服务端激活动态后复权折算（`adj="adj"`）与静态表优先直读；
- **外部导入表全自动动态路由**：若查询用户自定义导入的数据集（如 `crypto/kline`、`custom/factors`），系统自动模糊检索本地已存在的物理表进行切片读取，**0 行后端代码修改**即可自动接入新表；
- **输出契约无缝对齐**：输出与 `/query` 相同的高性能 2D Matrix，便于前端与图表组件无缝消费。

#### 请求路径参数 (Path Parameters)
| 参数名 | 类型 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `market` | String | 资产市场或大类标识 | `ashare` (A股), `aetf` (场内基金), `aindex` (指数), 或自定义市场 `crypto` |
| `category` | String | 数据分类或表类型 | `kline` (行情), `concept` (概念), `industry` (行业), `dragon_tiger` (龙虎榜), 或自定义 `factors` |

#### 请求查询参数 (Query Parameters)
| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `symbols` | String | `None` | 证券代码过滤，多个代码以逗号分隔 (如 `sh.600000,sz.000001`) |
| `board_code` | String | `None` | 板块代码过滤 (如 `BK0612`，精确定向获取板块成分股) |
| `freq` | String | `"1d"` | K 线频率，支持 `1d`, `5m`, `1m` (仅对 `kline` 生效) |
| `adj` | String | `"raw"` | 复权模式，支持 `raw` (不复权) 或 `adj` (后复权，自动享受服务端动态因子折算) |
| `start_date` | String | `None` | 起始日期过滤 (`YYYY-MM-DD`) |
| `end_date` | String | `None` | 结束日期过滤 (`YYYY-MM-DD`) |
| `columns` | String | `None` | 选挑字段清单，逗号分隔 (如 `timestamp,symbol,close`) |
| `source` | String | `None` | 指定底层数据源驱动 (如 `tdx`, `baostock`, `stockdb`)，未传则走表内置默认源 |
| `format` | String | `"auto"` | 存储格式 (`auto`, `parquet`, `csv`) |
| `page` | Integer | `1` | 当前页码 (从 1 开始) |
| `page_size` | Integer | `5000` | 每页记录数 |

#### 响应 JSON 结构示例
```json
{
  "market": "ashare",
  "category": "kline",
  "resolved_table_id": "ashare.kline.1d.adj.baostock",
  "total": 12500,
  "page": 1,
  "page_size": 5000,
  "total_pages": 3,
  "count": 5000,
  "columns": ["timestamp", "datetime", "symbol", "open", "high", "low", "close", "volume"],
  "data": [
    [1704092400000, "2024-01-01T15:00:00.000+08:00", "sh.600000", 6.62, 6.68, 6.61, 6.65, 12500000.0],
    [1704178800000, "2024-01-02T15:00:00.000+08:00", "sh.600000", 6.65, 6.72, 6.64, 6.70, 15000000.0]
  ]
}
```

#### cURL 调用示例
```bash
# 1. 语义化获取 A 股日线后复权数据 (自动服务端折算复权)
curl -X GET "http://127.0.0.1:8000/api/v1/data/ashare/kline?symbols=sh.600000&freq=1d&adj=adj"

# 2. 定向获取特定概念板块的成分股
curl -X GET "http://127.0.0.1:8000/api/v1/data/ashare/concept?board_code=BK0612"

# 3. 动态访问外部导入的自定义加密货币 K 线表
curl -X GET "http://127.0.0.1:8000/api/v1/data/crypto/kline?symbols=BTC.USDT&source=binance"
```

---

### 3.11 触发后台数据同步 (`POST /api/v1/sync`)

#### 请求 Body (JSON)
```json
{
  "table_ids": ["ashare.kline.1d.raw.baostock"],
  "formats": ["parquet"],
  "start_date": "2024-01-01",
  "end_date": "2024-06-30",
  "force_refresh": false,
  "batch_size": 100
}
```

#### 响应 JSON 结构示例 (`HTTP 200 OK`)
```json
{
  "status": "accepted",
  "started_tasks": ["ashare.kline.1d.raw.baostock"],
  "ignored_tasks": [],
  "message": "Sync tasks started in background."
}
```

#### cURL 调用示例
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/sync" \
     -H "Content-Type: application/json" \
     -d '{"table_ids": ["ashare.kline.1d.raw.baostock"], "formats": ["parquet"]}'
```

---

### 3.12 查询活跃同步任务 (`GET /api/v1/tasks`)

#### 响应 JSON 结构示例
```json
{
  "active_tasks": ["ashare.kline.1d.raw.baostock"]
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/tasks"
```

---

### 3.13 获取同步任务详细进度 (`GET /api/v1/sync/status`)

获取所有正在运行或已结束的同步任务精准进度、处理代码与状态。

#### 响应 JSON 结构示例
```json
{
  "active_tasks": ["ashare.kline.1d.raw.baostock"],
  "statuses": {
    "ashare.kline.1d.raw.baostock": {
      "table_id": "ashare.kline.1d.raw.baostock",
      "status": "running",
      "current": 45,
      "total": 100,
      "percentage": 45.0,
      "current_symbol": "sh.600000",
      "message": "正在抓取 sh.600000 (45/100)",
      "start_time": 1718000000.0,
      "end_time": null,
      "error_msg": null
    }
  }
}
```

#### cURL 示例
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/sync/status"
```

---

### 3.14 实时任务进度主动推流 (`GET /api/v1/sync/stream`)

基于 **Server-Sent Events (SSE)** 协议的任务状态实时主动推流通道，彻底消除客户端定时器轮询：
- **握手快照 (`snapshot`)**：客户端建立连接后，服务端立即下发包含所有任务当前状态与活跃列表的全量快照；
- **增量推流 (`progress`)**：在每次任务开启 (`start`)、单证券进度更新 (`update`) 或结束 (`finish`) 时微秒级主动推流；
- **空闲心跳 (`: ping\n\n`)**：无任务状态变动时每秒发送轻量心跳保持长连接活跃；
- **防代理缓冲响应头**：注入 `Content-Encoding: identity`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`，绕过 GZip 与反向代理缓冲。

#### SSE 推送数据帧示例
```http
data: {"type": "snapshot", "statuses": {...}, "active_tasks": ["ashare.kline.1d.raw.baostock"]}

data: {"type": "progress", "item": {"table_id": "ashare.kline.1d.raw.baostock", "status": "running", "current": 46, "total": 100, "percentage": 46.0, "current_symbol": "sh.600004"}, "active_tasks": ["ashare.kline.1d.raw.baostock"]}

: ping
```

---

### 3.15 实时系统日志推流 (`GET /api/v1/logs/stream`)

基于 **Server-Sent Events (SSE)** 的 Loguru 引擎全局日志实时推送通道：
- **历史回放**：连接建立时自动向客户端下发最近的内存历史日志（最多 1000 条）；
- **实时广播**：后续所有数据引擎、存储落盘与系统运行日志实时推流；
- **防代理缓冲**：注入 `Content-Encoding: identity`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`。

#### SSE 推送数据帧示例
```http
data: {"timestamp": "2026-09-05 20:00:00.123", "level": "INFO", "name": "SyncManager", "line": 158, "message": "Starting batch sync for ashare.kline.1d.raw.baostock"}
```

---

### 3.16 本地文件系统探查 (`GET /api/v1/filesystem/list`)

为 Web 端文件路径选择器提供本地目录浏览能力。

#### Query 查询参数
- `path` (选填): 指定浏览的绝对路径（缺省时为当前工作目录）。

#### 响应 JSON 结构示例
```json
{
  "current_path": "D:\\Quant\\CarrotQuant.Data",
  "parent_path": "D:\\Quant",
  "items": [
    {"name": "data", "path": "D:\\Quant\\CarrotQuant.Data\\data", "is_dir": true, "size": 0},
    {"name": "config.yaml", "path": "D:\\Quant\\CarrotQuant.Data\\config.yaml", "is_dir": false, "size": 156}
  ]
}
```
