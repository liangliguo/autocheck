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

### 1. 安装项目

```bash
git clone https://github.com/liangliguo/autocheck.git
cd autocheck
git checkout cli
uv sync --dev
```

### 2. 配置 `.env`

推荐先复制模板：

```bash
cp .env.example .env
```

最小可用配置示例：

```bash
OPENAI_API_KEY=your-key
AUTOCHECK_OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
AUTOCHECK_OPENAI_WIRE_API=responses
AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE=true
AUTOCHECK_MODEL_REASONING_EFFORT=xhigh
AUTOCHECK_ENABLE_LLM_EXTRACTION=false
AUTOCHECK_ENABLE_LLM_VERIFICATION=true
AUTOCHECK_CHAT_MODEL=gpt-5.4
AUTOCHECK_VERIFY_MODEL=gpt-5.4
AUTOCHECK_TEMPERATURE=0
AUTOCHECK_CHUNK_SIZE=2200
AUTOCHECK_CHUNK_OVERLAP=300
```

如果你使用 OpenAI 兼容代理，通常只需要改这两个值：

```bash
OPENAI_API_KEY=your-proxy-key
AUTOCHECK_OPENAI_BASE_URL=https://your-proxy.example.com/v1
```

如果你需要走系统代理：

```bash
export HTTPS_PROXY=http://127.0.0.1:7890
export HTTP_PROXY=http://127.0.0.1:7890
```

### 3. 运行命令行

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

## 增量输出

CLI 会在处理过程中持续打印进度，而不是等全部结束后再一次性输出。

终端中通常会看到：

- 阶段开始信息
- 每条参考文献的处理状态
- 每条 `claim x citation` 的核验结果
- 最终报告文件路径

同时会生成事件流文件：

```text
data/workspaces/<paper-name>/reports/<stem>.events.jsonl
```

该文件每行都是一个 JSON 事件，适合后续脚本处理或调试。

## 常用命令

```bash
# 安装依赖
uv sync --dev

# 运行全部测试
uv run pytest

# 运行样例输入
uv run autocheck run tests/fixtures/sample_draft.txt -s

# 核验论文链接
uv run autocheck run https://arxiv.org/abs/1706.03762 -n 3

# 指定输出目录
uv run autocheck run tests/fixtures/sample_draft.txt -s -o /tmp/autocheck-demo
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
  默认聊天模型，默认值为 `gpt-5.4`
- `AUTOCHECK_EXTRACT_MODEL`
  抽取阶段模型；留空时回退到 `AUTOCHECK_CHAT_MODEL`
- `AUTOCHECK_VERIFY_MODEL`
  核验阶段模型，默认值为 `gpt-5.4`
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

## 从零开始跑一篇论文

### 1. 准备输入

可以直接使用论文链接：

```bash
uv run autocheck run https://arxiv.org/abs/1706.03762 -n 5
```

也可以先下载 PDF 再处理：

```bash
mkdir -p inputs
curl -L https://arxiv.org/pdf/1706.03762.pdf -o inputs/attention-is-all-you-need.pdf
uv run autocheck run inputs/attention-is-all-you-need.pdf
```

### 2. 调整运行规模

如果只是联调流程，建议限制参考文献数量：

```bash
uv run autocheck run inputs/attention-is-all-you-need.pdf -n 5
```

如果只想验证抽取流程，不下载参考文献：

```bash
uv run autocheck run inputs/attention-is-all-you-need.pdf -s
```

### 3. 查看结果

```bash
find data/workspaces -maxdepth 3 -type f | sort
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
