from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Callable
from uuid import uuid4

import requests
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from autocheck.config.settings import AppSettings, PaperWorkspace
from autocheck.pipeline.orchestrator import AutoCheckPipeline
from autocheck.schemas.models import VerificationReport
from autocheck.services.source_resolver import resolve_source_input

PipelineFactory = Callable[[AppSettings], AutoCheckPipeline]

_ALLOWED_INPUT_SUFFIXES = {".pdf", ".txt", ".md"}


def create_app(
    settings: AppSettings | None = None,
    pipeline_factory: PipelineFactory = AutoCheckPipeline,
) -> FastAPI:
    resolved_settings = settings or AppSettings.from_env(project_root=Path.cwd())
    resolved_settings.ensure_directories()

    app = FastAPI(title="AutoCheck Studio")
    app.state.settings = resolved_settings
    app.state.pipeline_factory = pipeline_factory

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _render_page(
            form_values=_default_form_values(),
            recent_reports=_recent_reports(resolved_settings),
        )

    @app.post("/run", response_class=HTMLResponse)
    async def run(
        manuscript_text: str = Form(default=""),
        manuscript_file: UploadFile | None = File(default=None),
        manuscript_url: str = Form(default=""),
        max_references: str = Form(default=""),
        report_dir: str = Form(default=""),
        skip_download: bool = Form(default=False),
    ) -> str:
        form_values = {
            "manuscript_text": manuscript_text,
            "manuscript_url": manuscript_url,
            "max_references": max_references,
            "report_dir": report_dir,
            "skip_download": skip_download,
        }
        recent_reports = _recent_reports(resolved_settings)

        try:
            source_path, workspace = await _prepare_source(
                settings=resolved_settings,
                manuscript_text=manuscript_text,
                manuscript_file=manuscript_file,
                manuscript_url=manuscript_url,
            )
            output_dir = _resolve_report_dir(resolved_settings, workspace, report_dir)
            pipeline = pipeline_factory(resolved_settings)
            report, paths = pipeline.run(
                source_path=source_path,
                report_dir=output_dir,
                workspace_dir=workspace.root_dir,
                skip_download=skip_download,
                max_references=_parse_max_references(max_references),
            )
            markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
            return _render_page(
                form_values=form_values,
                report=report,
                report_paths={key: str(value) for key, value in paths.items()},
                markdown_preview=markdown,
                recent_reports=_recent_reports(resolved_settings),
                source_path=str(source_path),
            )
        except ValueError as exc:
            return _render_page(
                form_values=form_values,
                error_message=str(exc),
                recent_reports=recent_reports,
            )

    return app


def run_web_server(app: FastAPI, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


async def _prepare_source(
    settings: AppSettings,
    manuscript_text: str,
    manuscript_file: UploadFile | None,
    manuscript_url: str,
) -> tuple[Path, PaperWorkspace]:
    has_text = bool(manuscript_text.strip())
    has_file = bool(manuscript_file and manuscript_file.filename)
    has_url = bool(manuscript_url.strip())
    selected_count = sum((has_text, has_file, has_url))

    if selected_count > 1:
        raise ValueError("请只选择一种输入方式：上传文件、填写论文链接，或粘贴文本。")
    if selected_count == 0:
        raise ValueError("请上传文件、填写论文链接，或在文本框里粘贴论文内容。")

    if has_file and manuscript_file is not None:
        original_name = Path(manuscript_file.filename or "")
        suffix = original_name.suffix.lower()
        if suffix not in _ALLOWED_INPUT_SUFFIXES:
            raise ValueError("上传文件只支持 PDF、TXT 或 MD。")
        workspace = settings.workspace_for_source(original_name.name)
        workspace.ensure_directories()
        target_path = workspace.inputs_dir / _build_input_name(original_name.stem, suffix)
        target_path.write_bytes(await manuscript_file.read())
        return target_path, workspace

    if has_url:
        workspace = settings.workspace_for_source(manuscript_url.strip())
        workspace.ensure_directories()
        try:
            target_path = resolve_source_input(
                manuscript_url.strip(),
                workspace,
                timeout=settings.openai_timeout,
            )
        except requests.RequestException as exc:
            raise ValueError(f"下载论文链接失败：{exc}") from exc
        return target_path, workspace

    workspace = settings.workspace_for_source(
        f"pasted-manuscript-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    workspace.ensure_directories()
    target_path = workspace.inputs_dir / _build_input_name("pasted-manuscript", ".txt")
    target_path.write_text(manuscript_text, encoding="utf-8")
    return target_path, workspace


def _build_input_name(stem: str, suffix: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in stem).strip("-")
    safe_stem = safe_stem or "input"
    return f"{timestamp}-{safe_stem}-{uuid4().hex[:8]}{suffix}"


def _parse_max_references(raw_value: str) -> int | None:
    value = raw_value.strip()
    if not value:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("最大参考文献数量必须是正整数。")
    return parsed


def _resolve_report_dir(
    settings: AppSettings,
    workspace: PaperWorkspace,
    raw_value: str,
) -> Path:
    value = raw_value.strip()
    if not value:
        return workspace.reports_dir
    target = Path(value)
    if not target.is_absolute():
        target = settings.project_root / target
    target.mkdir(parents=True, exist_ok=True)
    return target


def _recent_reports(settings: AppSettings) -> list[str]:
    if not settings.workspaces_dir.exists():
        return []
    candidates = sorted(
        settings.workspaces_dir.glob("*/reports/*.report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [str(path) for path in candidates[:6]]


def _default_form_values() -> dict[str, object]:
    return {
        "manuscript_text": "",
        "manuscript_url": "",
        "max_references": "",
        "report_dir": "",
        "skip_download": False,
    }


def _render_page(
    *,
    form_values: dict[str, object],
    recent_reports: list[str],
    report: VerificationReport | None = None,
    report_paths: dict[str, str] | None = None,
    markdown_preview: str = "",
    source_path: str = "",
    error_message: str = "",
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoCheck Studio</title>
  <style>
    :root {{
      --bg: #f4efe5;
      --bg-accent: #ead8bb;
      --ink: #1d1a16;
      --muted: #6a6258;
      --panel: rgba(255, 252, 245, 0.86);
      --line: rgba(29, 26, 22, 0.1);
      --brand: #a43f24;
      --brand-deep: #6e2010;
      --good: #1f6f50;
      --warn: #a56a12;
      --bad: #8f2f33;
      --shadow: 0 24px 80px rgba(76, 46, 19, 0.14);
      --radius: 24px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI Variable", "Noto Sans SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(164, 63, 36, 0.16), transparent 32%),
        radial-gradient(circle at right center, rgba(63, 111, 80, 0.14), transparent 26%),
        linear-gradient(180deg, #fbf7ef 0%, var(--bg) 100%);
      min-height: 100vh;
    }}
    .shell {{
      width: min(1240px, calc(100vw - 32px));
      margin: 28px auto 48px;
    }}
    .hero {{
      display: grid;
      gap: 18px;
      padding: 28px;
      background: linear-gradient(145deg, rgba(255,255,255,0.88), rgba(245,232,212,0.92));
      border: 1px solid rgba(255,255,255,0.6);
      border-radius: 32px;
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -60px -80px auto;
      width: 260px;
      height: 260px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(164,63,36,0.22), rgba(164,63,36,0));
      pointer-events: none;
    }}
    .eyebrow {{
      display: inline-flex;
      width: fit-content;
      gap: 8px;
      align-items: center;
      padding: 6px 12px;
      border-radius: 999px;
      background: rgba(164,63,36,0.08);
      color: var(--brand-deep);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(36px, 7vw, 72px);
      line-height: 0.94;
      letter-spacing: -0.04em;
      max-width: none;
    }}
    .lead {{
      margin: 0;
      max-width: 720px;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.6;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
      gap: 22px;
      margin-top: 22px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
      padding: 22px;
    }}
    .panel h2, .panel h3 {{
      margin: 0 0 14px;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}
    .stack {{
      display: grid;
      gap: 14px;
    }}
    label {{
      display: grid;
      gap: 8px;
      font-size: 14px;
      color: var(--muted);
    }}
    .hint {{
      font-size: 12px;
      color: var(--muted);
    }}
    textarea, input[type="number"], input[type="text"], input[type="file"] {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid rgba(29,26,22,0.12);
      background: rgba(255,255,255,0.86);
      color: var(--ink);
      font: inherit;
    }}
    textarea {{
      min-height: 220px;
      resize: vertical;
    }}
    .option-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .checkbox {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      border: 1px solid rgba(29,26,22,0.12);
      border-radius: 18px;
      background: rgba(255,255,255,0.72);
      color: var(--ink);
    }}
    .checkbox input {{
      width: 18px;
      height: 18px;
      accent-color: var(--brand);
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 14px 22px;
      background: linear-gradient(135deg, var(--brand), var(--brand-deep));
      color: white;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 16px 34px rgba(111, 32, 16, 0.25);
    }}
    button:disabled {{
      opacity: 0.7;
      cursor: progress;
    }}
    .subtle {{
      color: var(--muted);
      font-size: 13px;
    }}
    .notice {{
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(143,47,51,0.08);
      border: 1px solid rgba(143,47,51,0.12);
      color: var(--bad);
      margin-bottom: 16px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric {{
      padding: 16px;
      border-radius: 20px;
      background: rgba(255,255,255,0.9);
      border: 1px solid var(--line);
    }}
    .metric span {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }}
    .metric strong {{
      font-size: 28px;
      letter-spacing: -0.04em;
    }}
    .meta-list, .recent-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .meta-item, .recent-item {{
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(255,255,255,0.76);
      border: 1px solid var(--line);
      overflow-wrap: anywhere;
    }}
    .reference-grid, .assessment-grid {{
      display: grid;
      gap: 14px;
    }}
    .reference-card, .assessment-card {{
      padding: 16px;
      border-radius: 20px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.88);
    }}
    .assessment-head {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .badge.strong_support {{ background: rgba(31,111,80,0.12); color: var(--good); }}
    .badge.partial_support {{ background: rgba(165,106,18,0.12); color: var(--warn); }}
    .badge.unsupported_or_misleading {{ background: rgba(143,47,51,0.12); color: var(--bad); }}
    .badge.not_found {{ background: rgba(29,26,22,0.08); color: var(--muted); }}
    .assessment-card p, .reference-card p {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .assessment-card strong, .reference-card strong {{
      color: var(--ink);
    }}
    .evidence {{
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(244,239,229,0.9);
      border: 1px solid rgba(29,26,22,0.08);
      font-size: 13px;
      line-height: 1.6;
      color: var(--muted);
    }}
    details {{
      margin-top: 16px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.84);
      overflow: hidden;
    }}
    summary {{
      cursor: pointer;
      padding: 14px 16px;
      font-weight: 700;
    }}
    pre {{
      margin: 0;
      padding: 0 16px 16px;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--muted);
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 13px;
      line-height: 1.55;
    }}
    @media (max-width: 980px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
      .option-row {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <span class="eyebrow">AutoCheck Studio</span>
      <h1>论文引用核验可视化工作台</h1>
      <p class="lead">上传 PDF、TXT、MD，填写论文链接，或者直接粘贴草稿文本。页面会调用现有 AutoCheck 流水线，并把摘要、参考文献匹配和逐条 assessment 直接展示出来。</p>
    </section>

    <div class="grid">
      <section class="panel">
        <h2>输入与运行</h2>
        {_render_error(error_message)}
        <form method="post" action="/run" enctype="multipart/form-data" id="run-form">
          <div class="stack">
            <label>
              上传论文文件
              <input type="file" name="manuscript_file" accept=".pdf,.txt,.md">
              <span class="hint">支持 PDF、TXT、MD。上传文件、论文链接、粘贴文本三选一。</span>
            </label>
            <label>
              或填写论文链接
              <input type="text" name="manuscript_url" value="{escape(str(form_values.get("manuscript_url", "")))}" placeholder="例如 https://arxiv.org/abs/1706.03762">
              <span class="hint">支持可直接下载的 PDF、TXT、MD 链接；常见 arXiv `abs` 链接会自动转换为 PDF。</span>
            </label>
            <label>
              或直接粘贴论文 / 草稿文本
              <textarea name="manuscript_text" placeholder="把带引用的段落粘贴到这里。">{escape(str(form_values.get("manuscript_text", "")))}</textarea>
            </label>
            <div class="option-row">
              <label>
                最大参考文献数
                <input type="number" min="1" name="max_references" value="{escape(str(form_values.get("max_references", "")))}" placeholder="例如 3">
              </label>
              <label>
                报告输出目录
                <input type="text" name="report_dir" value="{escape(str(form_values.get("report_dir", "")))}" placeholder="留空则写入 data/workspaces/&lt;paper&gt;/reports">
              </label>
            </div>
            <label class="checkbox">
              <input type="checkbox" name="skip_download" {"checked" if form_values.get("skip_download") else ""}>
              <span>跳过参考文献下载，只测试抽取和本地核验链路</span>
            </label>
            <div class="actions">
              <button type="submit" id="submit-button">运行 AutoCheck</button>
              <span class="subtle">页面是本地单用户模式；核验期间请求会保持打开。</span>
            </div>
          </div>
        </form>
      </section>

      <section class="panel">
        {_render_output(report, report_paths, markdown_preview, source_path)}
      </section>
    </div>

    <section class="panel" style="margin-top: 22px;">
      <h2>最近报告</h2>
      {_render_recent_reports(recent_reports)}
    </section>
  </div>
  <script>
    const form = document.getElementById("run-form");
    const button = document.getElementById("submit-button");
    form?.addEventListener("submit", () => {{
      button.disabled = true;
      button.textContent = "正在运行…";
    }});
  </script>
</body>
</html>"""


def _render_output(
    report: VerificationReport | None,
    report_paths: dict[str, str] | None,
    markdown_preview: str,
    source_path: str,
) -> str:
    if report is None:
        return """
        <h2>输出预览</h2>
        <p class="lead" style="font-size:16px;max-width:none;">运行完成后，这里会显示摘要卡片、引用匹配、assessment 详情，以及生成的报告路径。</p>
        """

    summary = report.summary
    progress = report.progress
    metrics = f"""
      <div class="metrics">
        <div class="metric"><span>Claims</span><strong>{summary.total_claims}</strong></div>
        <div class="metric"><span>Assessments</span><strong>{summary.total_assessments}</strong></div>
        <div class="metric"><span>Strong</span><strong>{summary.strong_support}</strong></div>
        <div class="metric"><span>Partial</span><strong>{summary.partial_support}</strong></div>
        <div class="metric"><span>Unsupported</span><strong>{summary.unsupported_or_misleading}</strong></div>
        <div class="metric"><span>Not Found</span><strong>{summary.not_found}</strong></div>
      </div>
    """

    meta_items = [
        ("状态", report.status),
        ("输入源", source_path or report.source_path),
        ("参考文献进度", f"{progress.completed_references}/{progress.total_references}" if progress else "-"),
        ("核验进度", f"{progress.completed_assessments}/{progress.total_assessments}" if progress else "-"),
    ]
    if report_paths:
        meta_items.extend(
            [
                ("JSON 报告", report_paths["json"]),
                ("Markdown 报告", report_paths["markdown"]),
                ("事件流", report_paths["events"]),
            ]
        )

    references = "".join(
        f"""
        <article class="reference-card">
          <strong>{escape(reference.ref_id)} · {escape(reference.title or "Unknown reference")}</strong>
          <p>作者：{escape(", ".join(reference.authors) or "未知")}</p>
          <p>年份：{escape(str(reference.year) if reference.year else "未知")}</p>
          <p>原始条目：{escape(reference.raw_text[:260])}</p>
        </article>
        """
        for reference in report.parsed_document.references
    ) or "<p class='subtle'>没有解析出参考文献。</p>"

    assessments = "".join(_render_assessment(item) for item in report.assessments) or "<p class='subtle'>没有生成 assessment。</p>"

    return f"""
      <h2>结果面板</h2>
      {metrics}
      <ul class="meta-list">
        {''.join(f"<li class='meta-item'><strong>{escape(label)}：</strong>{escape(value)}</li>" for label, value in meta_items)}
      </ul>
      <div style="height: 16px;"></div>
      <h3>解析出的参考文献</h3>
      <div class="reference-grid">{references}</div>
      <div style="height: 16px;"></div>
      <h3>逐条核验结果</h3>
      <div class="assessment-grid">{assessments}</div>
      <details>
        <summary>查看 Markdown 报告预览</summary>
        <pre>{escape(markdown_preview)}</pre>
      </details>
    """


def _render_assessment(item) -> str:
    evidence = "".join(
        f"<div class='evidence'><strong>{escape(chunk.chunk_id)}</strong><br>{escape(chunk.text[:300])}</div>"
        for chunk in item.evidence[:3]
    )
    supported = escape("; ".join(item.supported_points)) if item.supported_points else "无"
    concerns = escape("; ".join(item.concerns)) if item.concerns else "无"
    reference_title = item.reference.title if item.reference and item.reference.title else "Unknown reference"
    return f"""
      <article class="assessment-card">
        <div class="assessment-head">
          <strong>{escape(item.claim_id)} × {escape(item.citation_marker)}</strong>
          <span class="badge {escape(item.verdict.value)}">{escape(item.verdict.value)}</span>
        </div>
        <p><strong>引用文献：</strong>{escape(reference_title)}</p>
        <p><strong>置信度：</strong>{item.confidence:.2f}</p>
        <p><strong>Claim：</strong>{escape(item.claim_text)}</p>
        <p><strong>Reasoning：</strong>{escape(item.reasoning)}</p>
        <p><strong>Supported points：</strong>{supported}</p>
        <p><strong>Concerns：</strong>{concerns}</p>
        {evidence}
      </article>
    """


def _render_recent_reports(recent_reports: list[str]) -> str:
    if not recent_reports:
        return "<p class='subtle'>还没有生成过 Web UI 报告。</p>"
    items = "".join(
        f"<li class='recent-item'>{escape(path)}</li>"
        for path in recent_reports
    )
    return f"<ul class='recent-list'>{items}</ul>"


def _render_error(error_message: str) -> str:
    if not error_message:
        return ""
    return f"<div class='notice'>{escape(error_message)}</div>"
