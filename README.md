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
│   └── workspaces/
│       └── <paper-name>/
│           ├── inputs/      # 该主论文在本地工作区中的输入副本
│           ├── downloads/   # 该主论文关联的参考文献 PDF
│           ├── processed/   # 该主论文关联的参考文献文本和索引
│           └── reports/     # 该主论文的报告与事件流
├── inputs/             # 输入论文 PDF
├── src/autocheck/
├── tests/
├── LICENSE
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
AUTOCHECK_ENABLE_LLM_EXTRACTION=false
AUTOCHECK_ENABLE_LLM_VERIFICATION=true
AUTOCHECK_CHAT_MODEL=gpt-5.4
AUTOCHECK_VERIFY_MODEL=gpt-5.4
AUTOCHECK_TEMPERATURE=0
AUTOCHECK_CHUNK_SIZE=2200
AUTOCHECK_CHUNK_OVERLAP=300
EOF
```

默认建议：

- 默认开启 `LLM verification`
- 默认关闭 `LLM extraction`
- 默认模型为 `gpt-5.4`

这样真实测试时不需要再额外写环境变量开关，命令会更短。

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

## 参数列表

### 命令行参数

命令格式：

```bash
uv run autocheck run <source> [options]
```

- `source`
  输入论文路径或论文链接，支持 `PDF`、`TXT`、`MD`
- `-o, --report-dir`
  报告输出目录
  默认值：`data/workspaces/<source-stem>/reports`
- `-s, --skip-download`
  跳过参考文献下载
  默认值：关闭
- `-n, --max-references`
  只处理前 `N` 条参考文献以及它们关联的核验结果
  默认值：不限制

### 环境变量

说明：

- 下列“默认值”指代码里的内置默认值
- `.env.example` 里提供的是推荐模板值，不完全等同于代码默认值

- `OPENAI_API_KEY`
  OpenAI 或 OpenAI 兼容代理的 API Key
- `AUTOCHECK_OPENAI_BASE_URL`
  OpenAI 兼容接口地址
  默认值：空，留空时使用 SDK 默认地址
- `AUTOCHECK_OPENAI_TIMEOUT`
  请求超时秒数
  默认值：`120`
- `AUTOCHECK_OPENAI_MAX_RETRIES`
  请求失败后的最大重试次数
  默认值：`2`
- `AUTOCHECK_OPENAI_WIRE_API`
  OpenAI 接口模式
  默认值：`responses`
- `AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE`
  是否禁用响应存储
  默认值：`true`
- `AUTOCHECK_MODEL_REASONING_EFFORT`
  推理强度
  默认值：空，留空时不显式传递该参数
- `AUTOCHECK_ENABLE_LLM_EXTRACTION`
  是否用 LLM 做声明和参考文献抽取
  默认值：`false`
- `AUTOCHECK_ENABLE_LLM_VERIFICATION`
  是否用 LLM 做引用核验
  默认值：`true`
- `AUTOCHECK_CHAT_MODEL`
  默认聊天模型
  默认值：`gpt-5.4`
- `AUTOCHECK_EXTRACT_MODEL`
  抽取阶段模型
  默认值：空，回退到 `AUTOCHECK_CHAT_MODEL`
- `AUTOCHECK_VERIFY_MODEL`
  核验阶段模型
  默认值：`gpt-5.4`
- `AUTOCHECK_TEMPERATURE`
  模型温度
  默认值：`0`
- `AUTOCHECK_CHUNK_SIZE`
  证据切块大小
  默认值：`2200`
- `AUTOCHECK_CHUNK_OVERLAP`
  证据切块重叠
  默认值：`300`

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
uv run autocheck run tests/fixtures/sample_draft.txt -s
```

直接输入论文链接：

```bash
uv run autocheck run https://arxiv.org/abs/1706.03762 -n 3
```

启动本地可视化页面：

```bash
uv run autocheck web --host 127.0.0.1 --port 8000
```

指定输出目录：

```bash
uv run autocheck run tests/fixtures/sample_draft.txt -s -o /tmp/autocheck-demo
```

测试时只处理前 `N` 条参考文献：

```bash
uv run autocheck run tests/fixtures/sample_draft.txt -s -n 2
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
data/workspaces/<paper-name>/reports/<stem>.events.jsonl
```

每一行都是一个 JSON 事件。

## 输出文件

每次运行会生成三类文件：

```text
data/workspaces/<paper-name>/reports/<stem>.report.json
data/workspaces/<paper-name>/reports/<stem>.report.md
data/workspaces/<paper-name>/reports/<stem>.events.jsonl
```

其中：

- `.report.json` 是完整结构化报告
- `.report.md` 是便于阅读的 Markdown 报告
- `.events.jsonl` 是增量事件流

## Web 可视化界面

除了 CLI，现在还可以直接启动本地页面：

```bash
uv run autocheck web
```

默认地址：

```text
http://127.0.0.1:8000
```

页面支持：

- 上传 `PDF`、`TXT`、`MD`
- 填写论文链接作为输入
- 直接粘贴论文或草稿文本
- 默认按主论文名落到独立工作目录
- 设置 `max references`
- 设置自定义报告输出目录
- 选择是否跳过参考文献下载
- 在页面里查看摘要卡片、参考文献列表、assessment 结果和 Markdown 报告预览

适合本地单用户联调：

- 想快速试输入输出链路
- 不想只看 CLI 文本流
- 需要把报告结果直接展示给非命令行用户

## 从零开始跑真实论文

以下步骤就是这次实际测试用的完整流程。

### 1. 清空旧数据

```bash
rm -rf data/workspaces
mkdir -p data/workspaces
```

### 2. 下载输入论文

```bash
mkdir -p inputs
curl -L https://arxiv.org/pdf/1706.03762.pdf -o inputs/attention-is-all-you-need.pdf
```

或者直接把论文链接作为输入：

```bash
uv run autocheck run https://arxiv.org/abs/1706.03762 -n 5
```

### 3. 真实重跑

长论文建议关闭 `LLM extraction`，把模型预算留给核验阶段：

```bash
uv run autocheck run inputs/attention-is-all-you-need.pdf
```

如果只是联调流程，建议再限制参考文献数量：

```bash
uv run autocheck run inputs/attention-is-all-you-need.pdf -n 5
```

这条命令会：

- 解析输入论文
- 自动下载被引论文
- 逐条输出引用核验进度
- 在 `data/workspaces/<paper-name>/reports/` 生成最终报告

### 4. 查看结果

```bash
find data/workspaces -maxdepth 3 -type f | sort
```

```bash
uv run python - <<'PY'
import json
from pathlib import Path
p = Path("data/workspaces/attention-is-all-you-need/reports/attention-is-all-you-need.report.json")
data = json.loads(p.read_text())
print(data["summary"])
PY
```

## 快速完成版

如果你需要先快速拿到完整报告，不等整套 LLM 核验跑完，可以关闭 LLM 核验：

```bash
OPENAI_API_KEY='' \
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
uv run autocheck run your-paper.pdf
```

只看解析和增量输出，不下载：

```bash
uv run autocheck run your-paper.pdf -s
```

测试阶段只跑前几条参考文献：

```bash
uv run autocheck run your-paper.pdf -n 3
```

## 当前实现边界

- 支持 `PDF`、`TXT`、`MD`
- 支持本地文件路径和可直接下载的论文链接输入
- 默认按主论文名为每篇输入创建独立工作目录
- 参考文献寻址优先走 `OpenAlex`，再回退到 `arXiv`
- 部分引用会因为 PDF 提取噪声产生误解析
- 开放获取不到的参考文献会落到 `not_found`
- 长论文在 `gpt-5.4 + xhigh` 下逐条核验会比较慢

## 许可证

本项目采用 `MIT` 许可证。

完整条款见 [`LICENSE`](LICENSE)。

## 已验证命令

本仓库已经实际跑通过这些命令：

```bash
uv sync --dev
uv run pytest
uv run autocheck run tests/fixtures/sample_draft.txt -s
uv run autocheck run inputs/attention-is-all-you-need.pdf -n 3
uv run autocheck run https://arxiv.org/abs/1706.03762 -n 3
uv run autocheck web --help
```
