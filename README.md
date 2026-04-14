# AutoCheck

`AutoCheck` 是一个面向论文作者、审稿人和研究助理的引用核验工具，用来检查“文中的结论是否真的被对应参考文献支持”。

它支持读取论文 PDF、草稿文本或论文链接，自动提取带引用的声明与参考文献，检索可公开获取的被引论文，并输出结构化核验报告。

## 适用场景

- 投稿前检查论文中的引用是否准确
- 审稿时快速抽查重点 claim 的文献支撑情况
- 阅读论文时核对关键结论是否被原始文献充分支持

## 它会做什么

给定一篇论文后，`AutoCheck` 会依次完成以下步骤：

1. 读取 PDF、文本草稿或论文链接
2. 提取文中带引用的声明和参考文献列表
3. 自动解析、检索并下载可公开获取的被引论文
4. 将被引论文转换为可检索文本
5. 对每条 `claim x citation` 进行交叉核验
6. 输出 Markdown、JSON 和事件流结果

## 快速开始

### 1. 获取 API Key

如果你使用阿里云百炼平台，可以免费领取兼容 OpenAI 接口格式的 API Key：

1. 访问 [阿里云官网](https://www.aliyun.com/) 并登录账号
2. 进入 [百炼平台控制台](https://bailian.console.aliyun.com/)
3. 在左侧菜单打开「API-KEY 管理」
4. 创建新的 API Key
5. 复制并保存生成的 `sk-` 密钥

也可以使用 OpenAI 官方 API，或其他兼容 OpenAI 格式的服务。

### 2. 安装项目

要求：Python 3.11 或更高版本。

```bash
git clone https://github.com/liangliguo/autocheck.git
cd autocheck
uv sync --dev
```

### 3. 配置 `.env`

推荐先复制模板：

```bash
cp .env.example .env
```

默认推荐先从不开启 thinking、并使用 `function_calling` 开始：

```bash
OPENAI_API_KEY=sk-你的密钥
AUTOCHECK_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AUTOCHECK_CHAT_MODEL=qwen3-max
AUTOCHECK_VERIFY_MODEL=qwen3-max
AUTOCHECK_TEMPERATURE=0
AUTOCHECK_ENABLE_THINKING=false
AUTOCHECK_THINKING_BUDGET=0
AUTOCHECK_PRESERVE_THINKING=false
AUTOCHECK_ENABLE_LLM_EXTRACTION=false
AUTOCHECK_ENABLE_LLM_VERIFICATION=true
AUTOCHECK_STRUCTURED_OUTPUT_METHOD=function_calling
```

### 4. 启动 Web 界面

```bash
uv run autocheck web
```

浏览器访问 <http://127.0.0.1:8000>

Web 界面支持：

- 上传 `PDF`、`TXT`、`MD` 文件
- 输入论文链接，例如 arXiv 页面
- 直接粘贴论文文本
- 在配置页调整模型与运行参数
- 实时查看核验进度和 Markdown 报告

### 5. 或使用命令行

```bash
# 运行内置样例
uv run autocheck run tests/fixtures/sample_draft.txt -s

# 核验论文链接，仅处理前 3 条参考文献
uv run autocheck run https://arxiv.org/abs/1706.03762 -n 3

# 核验本地 PDF
uv run autocheck run your-paper.pdf
```

## 输出结果

默认情况下，运行结果会写入：

```text
data/workspaces/<paper-name>/reports/
```

通常包括：

- Markdown 报告：便于阅读和人工复核
- JSON 报告：便于后续程序处理
- 事件流文件：记录处理过程中的阶段事件

与单篇论文相关的中间文件会保存在对应工作目录下：

```text
data/workspaces/<paper-name>/
├── inputs/
├── downloads/
├── processed/
└── reports/
```

## 常用命令

```bash
# 安装依赖
uv sync --dev

# 运行全部测试
uv run pytest

# 运行一个测试文件
uv run pytest tests/test_pipeline_smoke.py

# 运行样例输入
uv run autocheck run tests/fixtures/sample_draft.txt -s

# 启动本地 Web UI
uv run autocheck web --host 127.0.0.1 --port 8000
```

## 命令行参数

命令格式：

```bash
uv run autocheck run <source> [options]
```

其中 `<source>` 可以是本地文件路径或论文链接，支持 `PDF`、`TXT`、`MD` 等输入。

常用参数如下：

- `-o, --report-dir`
  指定输出目录；默认写入 `data/workspaces/<source-stem>/reports`
- `-s, --skip-download`
  跳过参考文献下载；适合离线测试或只验证抽取流程
- `-n, --max-references`
  仅处理前 `N` 条参考文献；适合快速试跑或调试

## 配置说明

### 基础环境变量

- `OPENAI_API_KEY`
  OpenAI 或兼容服务的 API Key
- `AUTOCHECK_OPENAI_BASE_URL`
  OpenAI 兼容接口地址；留空时使用 SDK 默认地址
- `AUTOCHECK_CHAT_MODEL`
  默认聊天模型，默认值为 `qwen3-max`
- `AUTOCHECK_EXTRACT_MODEL`
  抽取阶段模型；留空时回退到 `AUTOCHECK_CHAT_MODEL`
- `AUTOCHECK_VERIFY_MODEL`
  核验阶段模型，默认值为 `qwen3-max`
- `AUTOCHECK_TEMPERATURE`
  模型温度，默认值为 `0`

### 运行相关参数

- `AUTOCHECK_ENABLE_LLM_EXTRACTION`
  是否启用 LLM 参与声明与参考文献抽取，默认值为 `false`
- `AUTOCHECK_ENABLE_LLM_VERIFICATION`
  是否启用 LLM 参与引用核验，默认值为 `true`
- `AUTOCHECK_CHUNK_SIZE`
  检索证据时的切块大小，默认值为 `2200`
- `AUTOCHECK_CHUNK_OVERLAP`
  相邻证据块的重叠长度，默认值为 `300`
- `AUTOCHECK_STRUCTURED_OUTPUT_METHOD`
  结构化输出方法，默认值为 `function_calling`
  可选值：`function_calling`、`json_mode`

### OpenAI 原生接口相关

以下参数主要在使用 OpenAI 原生 API 时生效，第三方兼容服务通常会忽略：

- `AUTOCHECK_OPENAI_TIMEOUT`
  请求超时秒数，默认值为 `120`
- `AUTOCHECK_OPENAI_MAX_RETRIES`
  最大重试次数，默认值为 `2`
- `AUTOCHECK_OPENAI_WIRE_API`
  接口通信模式，默认值为 `responses`
- `AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE`
  是否禁用服务端响应存储，默认值为 `true`
- `AUTOCHECK_MODEL_REASONING_EFFORT`
  推理强度；留空时不显式传递

### Qwen / 百炼兼容接口相关

以下参数主要在阿里云百炼等 OpenAI 兼容接口下生效，会通过 `extra_body` 传递：

- `AUTOCHECK_ENABLE_THINKING`
  是否启用深度思考，默认值为 `false`
- `AUTOCHECK_THINKING_BUDGET`
  思考预算，默认值为 `0`
- `AUTOCHECK_PRESERVE_THINKING`
  是否保留多轮思考上下文，默认值为 `false`

默认建议：

- `AUTOCHECK_ENABLE_THINKING=false`
- `AUTOCHECK_STRUCTURED_OUTPUT_METHOD=function_calling`

如果需要开启 thinking，请同时将结构化输出切到 `json_mode`。

### 下载相关

- `AUTOCHECK_SCIHUB_URL`
  自定义 Sci-Hub 镜像地址；留空时使用默认镜像列表

## 配置示例

### 使用 OpenAI 官方 API

```bash
OPENAI_API_KEY=your-openai-key
AUTOCHECK_CHAT_MODEL=gpt-4o
AUTOCHECK_VERIFY_MODEL=gpt-4o
AUTOCHECK_TEMPERATURE=0
AUTOCHECK_ENABLE_LLM_EXTRACTION=false
AUTOCHECK_ENABLE_LLM_VERIFICATION=true
```

### 使用第三方兼容 API

```bash
OPENAI_API_KEY=your-key
AUTOCHECK_OPENAI_BASE_URL=https://api.deepseek.com/v1
AUTOCHECK_CHAT_MODEL=deepseek-chat
AUTOCHECK_VERIFY_MODEL=deepseek-chat
AUTOCHECK_ENABLE_THINKING=false
AUTOCHECK_STRUCTURED_OUTPUT_METHOD=function_calling
```

如果第三方接口在 `function_calling` 下兼容性较弱，再改用 `json_mode`。若启用 thinking，则应使用 `json_mode`。

### 使用阿里云百炼 + Qwen3-Max

```bash
OPENAI_API_KEY=your-dashscope-key
AUTOCHECK_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AUTOCHECK_CHAT_MODEL=qwen3-max
AUTOCHECK_VERIFY_MODEL=qwen3-max
AUTOCHECK_ENABLE_THINKING=false
AUTOCHECK_THINKING_BUDGET=0
AUTOCHECK_PRESERVE_THINKING=false
AUTOCHECK_STRUCTURED_OUTPUT_METHOD=function_calling
AUTOCHECK_TEMPERATURE=0
```

如果你明确需要开启深度思考，再调整为：

```bash
AUTOCHECK_ENABLE_THINKING=true
AUTOCHECK_THINKING_BUDGET=50
AUTOCHECK_PRESERVE_THINKING=true
AUTOCHECK_STRUCTURED_OUTPUT_METHOD=json_mode
```

如果你需要走系统代理：

```bash
export HTTPS_PROXY=http://127.0.0.1:7890
export HTTP_PROXY=http://127.0.0.1:7890
```

## 项目结构

```text
autocheck/
├── data/
│   └── workspaces/
├── src/autocheck/
├── tests/
├── LICENSE
├── .env.example
├── pyproject.toml
└── uv.lock
```

## 说明

`AutoCheck` 的目标是帮助你更快发现引用中的明显问题、模糊支撑和潜在误引。它生成的是辅助核验结果，不应替代人工阅读原文和学术判断。
