# AutoCheck

`AutoCheck` 是一个基于 LangChain 的论文引用核验工具。

它做的事情很具体：

1. 读取论文 PDF 或草稿文本
2. 提取带引用的声明和参考文献列表
3. 自动检索并下载可公开获取的被引论文
4. 把被引论文转成纯文本
5. 对每条 `claim x citation` 做交叉核验
6. 输出完整报告和增量事件流

## 项目结构

```text
autocheck/
├── data/
│   ├── downloads/      # 下载的参考文献 PDF
│   ├── processed/      # 抽取后的参考文献文本和索引
│   └── reports/        # 输出报告
├── inputs/             # 输入论文 PDF
├── src/autocheck/
├── tests/
├── .env.example
├── pyproject.toml
└── uv.lock
```

## 环境要求

- Python 由 `uv` 管理
- 推荐直接使用仓库内 `.env`
- 默认命令全部使用 `uv run`

## 安装

在项目根目录执行：

```bash
uv sync --dev
```

## 配置

复制环境变量模板：

```bash
cp .env.example .env
```

最小可用配置示例：

```bash
cat > .env <<'EOF'
OPENAI_API_KEY=your-key
AUTOCHECK_OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
AUTOCHECK_OPENAI_WIRE_API=responses
AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE=true
AUTOCHECK_MODEL_REASONING_EFFORT=xhigh
AUTOCHECK_ENABLE_LLM_EXTRACTION=true
AUTOCHECK_ENABLE_LLM_VERIFICATION=true
AUTOCHECK_CHAT_MODEL=gpt-5.4
AUTOCHECK_VERIFY_MODEL=gpt-5.4
AUTOCHECK_TEMPERATURE=0
AUTOCHECK_CHUNK_SIZE=2200
AUTOCHECK_CHUNK_OVERLAP=300
EOF
```

如果你走 OpenAI 兼容代理，只需要改这两个值：

```bash
OPENAI_API_KEY=your-proxy-key
AUTOCHECK_OPENAI_BASE_URL=https://your-proxy.example.com/v1
```

如果你走系统代理：

```bash
export HTTPS_PROXY=http://127.0.0.1:7890
export HTTP_PROXY=http://127.0.0.1:7890
```

## 常用命令

安装依赖：

```bash
uv sync --dev
```

运行测试：

```bash
uv run pytest
```

运行一个最小样例：

```bash
uv run autocheck run tests/fixtures/sample_draft.txt --skip-download
```

指定输出目录：

```bash
uv run autocheck run tests/fixtures/sample_draft.txt --skip-download --report-dir /tmp/autocheck-demo
```

## 增量返回

CLI 不是等全部结束后才打印。

现在会增量输出：

- 阶段开始
- 每条参考文献处理结果
- 每条 `claim x citation` 核验结果
- 最终报告路径

同时会生成事件流文件：

```text
data/reports/<stem>.events.jsonl
```

每一行都是一个 JSON 事件。

## 输出文件

每次运行会生成三类文件：

```text
data/reports/<stem>.report.json
data/reports/<stem>.report.md
data/reports/<stem>.events.jsonl
```

其中：

- `.report.json` 是完整结构化报告
- `.report.md` 是便于阅读的 Markdown 报告
- `.events.jsonl` 是增量事件流

## 从零开始跑真实论文

以下步骤就是这次实际测试用的完整流程。

### 1. 清空旧数据

```bash
rm -rf data/downloads data/processed data/reports
mkdir -p data/downloads data/processed data/reports
```

### 2. 下载输入论文

```bash
mkdir -p inputs
curl -L https://arxiv.org/pdf/1706.03762.pdf -o inputs/attention-is-all-you-need.pdf
```

### 3. 真实重跑

长论文建议关闭 `LLM extraction`，把模型预算留给核验阶段：

```bash
AUTOCHECK_ENABLE_LLM_EXTRACTION=false \
uv run autocheck run inputs/attention-is-all-you-need.pdf
```

这条命令会：

- 解析输入论文
- 自动下载被引论文
- 逐条输出引用核验进度
- 在 `data/reports/` 生成最终报告

### 4. 查看结果

```bash
ls -lh data/reports
```

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("data/reports/attention-is-all-you-need.report.json")
data = json.loads(p.read_text())
print(data["summary"])
PY
```

## 快速完成版

如果你需要先快速拿到完整报告，不等整套 LLM 核验跑完，可以关闭 LLM 核验：

```bash
OPENAI_API_KEY='' \
AUTOCHECK_ENABLE_LLM_EXTRACTION=false \
AUTOCHECK_ENABLE_LLM_VERIFICATION=false \
uv run autocheck run inputs/attention-is-all-you-need.pdf
```

这时：

- 参考文献仍然会真实下载和预处理
- 报告仍然会完整输出
- 核验 verdict 改为启发式快速评分

## 运行模式建议

短文档：

```bash
uv run autocheck run your-paper.pdf
```

长论文，优先保证能跑完：

```bash
AUTOCHECK_ENABLE_LLM_EXTRACTION=false \
uv run autocheck run your-paper.pdf
```

只看解析和增量输出，不下载：

```bash
uv run autocheck run your-paper.pdf --skip-download
```

## 当前实现边界

- 支持 `PDF`、`TXT`、`MD`
- 参考文献寻址优先走 `OpenAlex`，再回退到 `arXiv`
- 部分引用会因为 PDF 提取噪声产生误解析
- 开放获取不到的参考文献会落到 `not_found`
- 长论文在 `gpt-5.4 + xhigh` 下逐条核验会比较慢

## 已验证命令

本仓库已经实际跑通过这些命令：

```bash
uv sync --dev
uv run pytest
uv run autocheck run tests/fixtures/sample_draft.txt --skip-download
AUTOCHECK_ENABLE_LLM_EXTRACTION=false uv run autocheck run inputs/attention-is-all-you-need.pdf
```
