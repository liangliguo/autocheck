# AutoCheck

`AutoCheck` 是一个基于 LangChain 的论文引用核验项目，目标是自动化交叉比对论文中的声明与其引用的原始文献，判断引用是否真正支撑该声明。

## 能力范围

项目按标准流水线拆分为以下阶段：

1. 逆向解析输入论文或草稿，抽取事实性声明与参考文献列表。
2. 调用开放学术 API 自动检索并下载原始 PDF。
3. 从草稿中提取包含引用的句子及其引用标识。
4. 读取本地 PDF，提取为纯文本并切分为可检索证据块。
5. 使用 LangChain 驱动长上下文模型，对声明与候选证据做严格交叉核验。
6. 输出 JSON 与 Markdown 两种格式的验证报告。

## 项目结构

```text
autocheck/
├── data/
│   ├── downloads/      # 下载的原始 PDF
│   ├── processed/      # 抽取后的文本和索引
│   └── reports/        # JSON / Markdown 报告
├── src/autocheck/
│   ├── cli/            # 命令行入口
│   ├── config/         # 配置加载
│   ├── extractors/     # 声明、引用、参考文献抽取
│   ├── llm/            # LangChain 模型工厂
│   ├── pipeline/       # 主流程编排
│   ├── prompts/        # Prompt 模板
│   ├── repository/     # 本地文献库和缓存
│   ├── resolvers/      # OpenAlex / arXiv 寻址下载
│   ├── schemas/        # Pydantic 数据模型
│   ├── services/       # 文档加载、文本切分、报告写入
│   └── utils/          # 引用与文本工具
├── .env.example
└── pyproject.toml
```

## 安装

建议使用 `uv`：

```bash
uv sync --dev
```

## 环境变量

复制 `.env.example` 并设置模型参数：

```bash
export OPENAI_API_KEY="your-key"
export AUTOCHECK_OPENAI_BASE_URL="https://ai.td.ee"
export AUTOCHECK_OPENAI_WIRE_API="responses"
export AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE="true"
export AUTOCHECK_MODEL_REASONING_EFFORT="xhigh"
export AUTOCHECK_CHAT_MODEL="gpt-5.4"
export AUTOCHECK_VERIFY_MODEL="gpt-5.4"
export AUTOCHECK_CHUNK_SIZE="2200"
export AUTOCHECK_CHUNK_OVERLAP="300"
```

如果你通过第三方 OpenAI 兼容代理访问模型，配置代理的 `base_url`：

```bash
export OPENAI_API_KEY="your-proxy-key"
export AUTOCHECK_OPENAI_BASE_URL="https://your-proxy.example.com/v1"
export AUTOCHECK_CHAT_MODEL="gpt-4.1"
```

如果你使用的是系统层 HTTP 转发代理，而不是 OpenAI 兼容网关，则直接设置：

```bash
export HTTPS_PROXY="http://127.0.0.1:7890"
export HTTP_PROXY="http://127.0.0.1:7890"
```

项目会自动读取仓库根目录下的 `.env`。`AUTOCHECK_OPENAI_BASE_URL` 优先级高于 `OPENAI_BASE_URL` 和 `OPENAI_API_BASE`。
`AUTOCHECK_OPENAI_WIRE_API=responses` 会让 LangChain 尝试使用 OpenAI Responses API；`AUTOCHECK_MODEL_REASONING_EFFORT` 会透传为模型的 reasoning effort；`AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE=true` 会把请求的 `store` 参数设为 `false`。
对长论文，建议保留 `AUTOCHECK_ENABLE_LLM_VERIFICATION=true`，但可临时把 `AUTOCHECK_ENABLE_LLM_EXTRACTION=false`，先用启发式规则抽取声明和参考文献，再把 LLM 预算集中到交叉核验阶段。

未配置 `OPENAI_API_KEY` 时，项目仍可完成正则抽取、本地寻址和启发式打分，但严格的交叉推理核验会退化为词面重叠评分，不建议用于正式审稿场景。

## 使用方式

对论文 PDF 或纯文本草稿运行主流程：

```bash
uv run autocheck run ./examples/draft.pdf
```

指定输出目录：

```bash
uv run autocheck run ./examples/draft.txt --report-dir ./data/reports
```

只做解析，不下载：

```bash
uv run autocheck run ./examples/draft.pdf --skip-download
```

运行测试：

```bash
uv run pytest
```

## 当前实现说明

- 支持 PDF / TXT / MD 输入。
- 参考文献定位优先使用 OpenAlex 开放接口，随后回退到 arXiv。
- 引用句抽取优先使用正则；若提供 LLM，则用 LangChain 做结构化补全。
- 核验粒度为“声明 x 引用文献”。
- 输出包含 `strong_support`、`partial_support`、`unsupported_or_misleading`、`not_found` 四类结论。

## 后续可扩展点

- 接入 Crossref、Semantic Scholar、DOI 解析器。
- 增加向量检索或 reranker，提高长文献证据召回质量。
- 增加 Web UI 或批量任务队列。
