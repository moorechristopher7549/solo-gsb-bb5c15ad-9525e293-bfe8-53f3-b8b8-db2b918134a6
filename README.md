# 📮 MailTrace — 邮件投递路径检查器

一个轻量的 Python Flask 网页应用，帮助开发者检查邮件**原始头部**（raw headers）的投递路径：

- 自动处理 **折行（folding）字段**，按 RFC 5322 展开续行；
- 提取每一个 `Received` 字段中的时间戳，统一换算为 **UTC**；
- 按邮件**实际投递先后**排列中继节点（发件方 → 收件方），而不是按头部里的书写顺序；
- 计算并展示**相邻节点耗时**（含端到端总耗时）；
- **无法解析的时间标记为异常，但保留原始字段**（可展开查看）；
- **缺少时间的节点仍然列出**，不会被丢弃；
- 识别时钟偏移/时间倒灌（上一节点时间晚于本节点）并告警；
- 提取 `from` / `by` / `via` / `with` / `id` 与对端 IPv4/IPv6 地址；
- **双邮件头路径对照**：分别粘贴两份头部，按 `by` 主机 + 对端 IP 识别同一节点，
  以保序全局对齐并列展示**共有 / 新增（仅 B）/ 缺失（仅 A）**节点，
  并比较共有节点两侧的相邻耗时（任一侧时间无效则不可比较，不拼接耗时）。

解析核心（`mailtrace/`）仅依赖 Python 标准库，可脱离 Flask 单独使用或被其他程序导入。

---

## 一条命令启动

### 方式一：Docker Compose（推荐）

```bash
docker compose up -d --build
```

然后浏览器访问：

```
http://localhost:8000
```

### 方式二：仅用 Docker

```bash
docker build -t mailtrace . && docker run --rm -p 8000:8000 mailtrace
```

访问 `http://localhost:8000`。

> 容器在**启动时**会执行一次 `pip install -r requirements.txt`（见 `entrypoint.sh`），
> 因此即使基础镜像内没有预装依赖，依赖也会随容器启动自动安装；
> Dockerfile 在构建阶段也会预装一次以加速常规启动。
> 离线或希望跳过启动安装时，设置环境变量 `SKIP_STARTUP_INSTALL=1`。

停止服务：`docker compose down`。

---

## 使用方法

1. 打开 `http://localhost:8000`；
2. 把邮件的**原始头部**（Gmail 的“显示原始邮件”、Outlook 的“查看邮件来源”等）完整粘贴到文本框
   （也可以点“填入示例”）；
3. 点击 **分析投递路径**。

页面以时间线形式展示每个中继节点：节点名称、UTC 时间、from/by/协议、对端 IP、
距上一节点耗时、异常/告警，以及可展开的**原始 `Received` 文本（保留折行）**。

### 双邮件头路径对照

在首页下方的「双邮件头路径对照」区域，把两份邮件原始头部分别粘贴到
**头部 A（基准）** 与 **头部 B（对照）**，点击 **对照投递路径**（可点“填入对照示例”体验）。
页面按结构顺序对齐两侧中继节点，并列展示：

- **共有**：两侧身份相同的节点，展示各自的相邻耗时与差值（如 `+5 秒` 表示 A 侧更慢）；
- **新增（仅 B）**：只出现在头部 B 的节点；
- **缺失（仅 A）**：只出现在头部 A 的节点。

对照规则：

- 节点身份 = `by` 主机名（忽略大小写与末尾点号）+ 对端 IP，二者共同决定“同一跳”；
- `by` 主机与对端 IP **都缺失**的节点没有身份，不参与匹配——不会仅凭时间相近被当作同一跳；
- 同名节点重复出现时，使用**保序全局对齐**（LCS 动态规划，最大化匹配对数且保持结构顺序），
  而非“首次命中”式的贪心配对；
- 共有节点的耗时取各自单份分析中的**相邻两跳耗时之差**；任一侧时间无效即显示
  **不可比较**，不会跳过中间无时间的节点拼接耗时。

也提供 JSON 对照接口：

```bash
curl -s -X POST http://localhost:8000/api/compare \
  -H 'Content-Type: application/json' \
  -d '{
        "headers_a": "Received: by mx.example; Tue, 23 Sep 2026 10:00:00 +0800",
        "headers_b": "Received: by mx.example; Tue, 23 Sep 2026 10:00:05 +0800"
      }'
```

返回的 `rows` 数组按结构顺序给出每一行对照（`kind` 为 `common` / `added` / `missing`），
共有行内含 `delay`（两侧相邻耗时与 `diff_seconds` 差值，`comparable=false` 表示不可比较）。
任一侧没有 `Received` 字段时返回 HTTP 400 与明确错误，例如：

```json
{"error": "头部 B 中未找到任何 Received 字段，无法进行路径对照", "side": "b", "counts": {...}, "rows": []}
```

单份头部分析也提供 JSON 接口，便于脚本调用：

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"headers": "Received: by mx.example; Tue, 23 Sep 2026 10:00:00 +0800"}'
```

健康检查：`GET http://localhost:8000/healthz`。

---

## 排序原理（为什么要反转）

邮件每经过一台服务器，该服务器就把自己的 `Received` 字段**追加到头部最前面**。
因此头部文本里第一条 `Received` 是最后一跳（最靠近收件方），最后一条才是第一跳。
本工具按这一“嵌套结构”将 `Received` **反转**后呈现，得到真实投递顺序，
再用时间戳校验该顺序并计算相邻耗时。当解析出的时间出现倒挂（时钟偏差或伪造）时，会明确告警。

---

## 配置（环境变量）

| 变量 | 默认值 | 作用范围 | 说明 |
| --- | --- | --- | --- |
| `HOST_PORT` | `8000` | Compose | 宿主机映射端口（容器内服务固定监听 8000） |
| `APP_PORT` | `8000` | 容器/本地 | 容器内 gunicorn 绑定端口；改它需同步调整端口映射 |
| `APP_HOST` | `0.0.0.0` | 本地 | 直接用 Flask 开发服务器运行时的监听地址 |
| `MAX_INPUT_KB` | `256` | 容器/本地 | 单次粘贴头部的大小上限（KB），超出返回错误 |
| `SKIP_STARTUP_INSTALL` | `0` | 容器 | 设为 `1` 跳过容器启动时的 `pip install`，直接用镜像内依赖 |

### 访问端口

- Compose 默认把宿主机 **8000** 端口映射到容器 8000。
- 想换宿主机访问端口，在项目根目录创建 `.env`（或先导出环境变量再 `up`）：

```bash
echo "HOST_PORT=9000" > .env
docker compose up -d --build
# 访问 http://localhost:9000
```

也可以在运行时直接覆盖，例如：

```bash
docker run --rm -e MAX_INPUT_KB=512 -p 8080:8000 mailtrace
# 访问 http://localhost:8080
```

---

## 本地开发（不使用容器）

需要 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python wsgi.py            # Flask 开发服务器，默认 http://localhost:8000
# 或
gunicorn -b 0.0.0.0:8000 wsgi:app
```

运行解析器测试（**仅需标准库，无需安装 Flask**）：

```bash
python -m unittest discover -s tests -v
```

---

## 项目结构

```
.
├── app/                    # Flask 应用（路由、模板）
│   ├── __init__.py         # create_app()：页面 + JSON API + 健康检查
│   └── templates/index.html
├── mailtrace/              # 纯标准库解析核心（可独立复用）
│   └── parsing/
│       ├── parser.py       # 折行展开、时间解析、路径排序、耗时与异常
│       ├── compare.py      # 双头部：身份键 + 保序全局对齐 + 相邻耗时差值
│       └── sample.py       # 页面“填入示例”数据（单份与对照各一份）
├── wsgi.py                 # gunicorn / flask 启动入口
├── entrypoint.sh           # 容器启动时安装依赖并启动 gunicorn
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── tests/
    ├── test_parser.py      # 解析核心单元测试
    └── test_compare.py     # 双头部对照单元测试
```

## 安全与隐私

应用只在本地/你的服务器内解析粘贴内容，不向任何外部服务发送邮件头；
请仍按敏感信息对待原始头部（其中可能含内网主机名与 IP）。
