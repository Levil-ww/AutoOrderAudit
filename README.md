# AutoOrderAudit — 自动审单系统

基于卖家备注自动解析并修改 ERP 订单商品编码的自动化工具，专为电商客服场景设计。

## 项目概述

AutoOrderAudit 连接方果 ERP 系统，自动拉取待整理订单，解析卖家备注中的**材质-颜色-尺寸-花型**编码，更新订单商品商家编码（shop_mapping_sku），大幅减少客服人工处理订单的时间。

核心流程：

```
方果ERP ──[API]──→ 适配器拉取订单 ──→ 解析卖家备注 ──→ 生成商家编码 ──→ [API]更新回ERP
```

## 功能特性

- **自动审单** — 批量拉取待整理订单，逐单解析备注并更新编码
- **智能备注解析** — 支持编码格式（`材质-颜色-尺寸-花型`）和自然语言备注的混合解析
- **材质同义词映射** — 内置同义词映射表，兼容客服不同写法（如"双面芊"→"双面格"）
- **材质自动匹配** — 从方果 API 拉取材质列表，支持模糊匹配，识别率高
- **合并订单处理** — 识别合并订单（多个子订单），逐一分配到商品行
- **赠品检测** — 自动识别备注中的赠品信息，避免误处理
- **安全关键字过滤** — 备注含"待定"、"等通知发"等关键字时自动跳过
- **Dry Run 模式** — 仅打印不提交，安全测试
- **Token 自动管理** — 支持账号密码自动登录，Token 过期检测与提醒
- **图形界面** — 基于 tkinter 的美化版 GUI，适合非技术人员直接使用

## 目录结构

```
AutoOrderAudit/
├── adapters/                          # 适配器模块（可扩展多个ERP）
│   └── fangguo/                       # 方果ERP适配器
│       ├── __init__.py                # 包入口，导出 FangguoAdapter 及配置
│       ├── adapter.py                 # 方果ERP适配器实现（查询订单、更新编码）
│       ├── config.py                  # 方果配置（API地址、材质映射、运行模式）
│       ├── material_source.py         # 材质数据源（从API拉取材质列表）
│       └── ExampleFangguo.txt         # 示例/模板文件
├── core/                              # 核心引擎模块（通用，不依赖具体ERP）
│   ├── __init__.py                    # 包入口，导出核心类
│   ├── adapter_base.py                # ERP适配器抽象接口基类
│   ├── engine.py                      # 自动审单引擎（核心流程编排）
│   └── parser.py                      # 卖家备注解析引擎（正则+规则）
├── Test/                              # 测试模块
├── auth_client.py                     # 方果登录客户端（封装登录API）
├── auth_manager.py                    # Token管理（自动登录/保存/刷新）
├── gui.py                             # 图形界面（tkinter美化版）
├── run_gui.py                         # GUI启动脚本
├── test.py                            # 测试入口脚本
├── token.json                         # Token存储文件（程序自动管理）
├── requirements.txt                   # Python依赖列表
└── README.md                          # 项目说明文档
```

## 技术架构

### 分层设计

| 层 | 模块 | 职责 |
|---|---|---|
| **适配器层** | `adapters/fangguo/` | 实现 `ErpAdapter` 接口，与具体 ERP 系统通信 |
| **核心引擎层** | `core/engine.py` | 编排审单流程，不依赖具体 ERP |
| **解析引擎** | `core/parser.py` | 通用备注解析，注入式材质映射 |
| **认证层** | `auth_client.py` + `auth_manager.py` | Token 自动获取与生命周期管理 |
| **界面层** | `gui.py` | 桌面图形界面，零代码操作 |

### 关键抽象

- **ErpAdapter**（`core/adapter_base.py`） — ERP 适配器抽象接口。所有 ERP 系统实现该接口即可接入引擎。
- **ParsedRemark**（`core/parser.py`） — 备注解析结果模型，包含 `material_code`、`color_code`、`model_code`、`picture_code` 等字段。
- **AutoAuditEngine**（`core/engine.py`） — 自动审单引擎，遍历订单 → 解析备注 → 更新编码，支持回调确认。

## 快速开始

### 环境要求

- Python 3.9+
- 依赖库：`requests`

### 安装

```bash
# 创建虚拟环境（推荐）
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 运行

**方式一：图形界面（推荐）**

```bash
python run_gui.py
```

首次使用点击「登录」，输入方果 ERP 的账号密码，程序会自动获取 Token 并保存。

**方式二：命令行**

```bash
python test.py
```

### 配置说明

主要配置在 `adapters/fangguo/config.py` 中：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `DRY_RUN` | `False` | 设为 `True` 时仅打印不提交，安全测试用 |
| `MAX_ORDERS` | `0` | 最大处理订单数，`0` 表示不限 |
| `MATERIAL_MAP` | （内置映射表） | 材质同义词映射，可自行扩展 |
| `QUERY_STATUS` | `1` | 查询状态，`1`=待整理 |
| `TIME_BEGIN/END` | 最近7天 | 自动计算滚动时间范围 |

## 备注解析规则

### 标准编码格式

```
材质-颜色-尺寸-花型
```

例如：`双面格-灰色-100x150-花满金陵`

### 自然语言格式

支持多种自然语言写法，例如：

- `灰色双面格1张100x150花满金陵`
- `双面格灰色100x150花满金陵1个`
- `圆80cm 双面格 灰色 花满金陵`

### 材质自动映射

客服手写材质名称 → 系统标准化编码：

```
双面芊 → 双面格
pu皮革 → pu防水
镜面革 → 镜面皮革
真有机硅 → 有机硅
...
```

## 登录与 Token 管理

- **推荐方式**：通过 GUI 的「登录」按钮，输入账号密码，程序自动调用方果登录接口获取 Token
- **手动方式**：技术人员在 `token.json` 中填入 Token 信息

**Token 文件（`token.json`）**：

```json
{
  "authorization": "Bearer xxxxx",
  "cookie_str": "JSESSIONID=xxxxx",
  "tenant_id": "3005247",
  "expires_at": "2026-07-18",
  "username": "188xxxx6178"
}
```

程序会自动检测 Token 是否过期，并在过期前提醒。

## 扩展其它 ERP

如需接入其他 ERP 系统，只需：

1. 在 `adapters/` 下创建新包（如 `jingdong/`）
2. 实现 `ErpAdapter` 接口（`query_orders` + `update_merchant_code`）
3. 可选：实现材质数据源以提供 `material_matcher`
4. 引擎和解析器无需改动

## 技术栈

- Python 3 — 主语言
- `requests` — HTTP 客户端（带重试机制）
- `tkinter` — 桌面 GUI
- `difflib.SequenceMatcher` — 材质模糊匹配
- 正则表达式 — 备注解析核心

## 许可证

本项目仅供内部使用。