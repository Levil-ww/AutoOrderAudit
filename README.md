# 方果ERP 自动审单工具

基于适配器模式的跨ERP自动审单系统。**核心通用，适配器可插拔。**

## 架构

```
fangguo-auto/
│
├── core/                       ← 🟢 通用核心（换ERP也不用改）
│   ├── adapter_base.py         ← ERP适配器抽象接口
│   ├── parser.py               ← 备注解析引擎（参数化，无外部依赖）
│   └── engine.py               ← 自动审单引擎（通过接口调用适配器）
│
├── adapters/                   ← 🔴 ERP适配器（换系统就换这个文件夹）
│   └── fangguo/                ← 方果ERP适配器
│       ├── config.py           ← 方果的API地址、鉴权信息
│       ├── material_source.py  ← 从方果拉取材质列表做自动匹配
│       └── adapter.py          ← ErpAdapter 接口实现
│
├── main.py                     ← 入口（选择适配器 + 启动引擎）
├── test.py                     ← 连通性测试
├── requirements.txt
└── README.md
```

## 核心理念

```
core/  = 大脑（通用，跨ERP复用）
         ↓ 通过 ErpAdapter 接口调用
adapters/ = 手脚（ERP特定，可替换）
```

## 使用前准备

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置鉴权

打开 `adapters/fangguo/config.py`，填入从 F12 抓取的信息：

```python
AUTHORIZATION = "Bearer 你的token"
COOKIE_STR = "JSESSIONID=你的session"
TENANT_ID = "你的租户ID"
```

### 3. 配置材质映射（可选）

如果备注里有新的材质写法，加到 `MATERIAL_MAP` 中：

```python
MATERIAL_MAP = {
    "双面芊": "双面格",
    "吸水皮革": "吸水皮革",
    "防辣椒油": "防辣椒油",
    # 遇到新材质加上就行
}
```

## 运行

```bash
# 测试连通性
python test.py

# 执行自动审单（默认 DRY_RUN=True）
python main.py

# 确认无误后，修改 config.py 中 DRY_RUN = False
```

## 换其他 ERP 系统

只需要 3 步：

### 1. 创建新适配器

```bash
mkdir -p adapters/erp_x/
```

### 2. 实现 ErpAdapter 接口

```python
# adapters/erp_x/adapter.py
from core import ErpAdapter, Order, OrderItem

class ErpXAdapter(ErpAdapter):
    def query_orders(self, **kwargs) -> list[Order]:
        # 调新ERP的订单查询接口
        ...

    def update_merchant_code(self, order, parsed) -> bool:
        # 调新ERP的修改编码接口
        ...
```

### 3. 修改 main.py

```python
# main.py  改动这一行
# from adapters.fangguo import FangguoAdapter   ← 旧
from adapters.erp_x import ErpXAdapter           # ← 新

adapter = ErpXAdapter()
engine = AutoAuditEngine(adapter=adapter, ...)
engine.run(...)
```

核心 `core/` 一个字母都不用改。

## 技术栈

- **语言**: Python 3.8+
- **核心依赖**: requests（HTTP调用）
- **架构模式**: 适配器模式（Adapter Pattern）
- **部署方式**: 脚本 / 打包成 exe / 定时任务