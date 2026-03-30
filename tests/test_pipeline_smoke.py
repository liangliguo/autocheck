from pathlib import Path
import json

from langchain_core.runnables import RunnableLambda

from autocheck.config.settings import AppSettings
from autocheck.extractors.document_extractor import DocumentClaimReferenceExtractor
from autocheck.pipeline.orchestrator import AutoCheckPipeline
from autocheck.pipeline.verifier import ClaimCitationVerifier
from autocheck.schemas.models import (
    ClaimRecord,
    EvidenceChunk,
    LLMClaimExtraction,
    LLMVerificationDecision,
    ReferenceEntry,
    VerificationLabel,
)
from autocheck.repository.library import PaperLibrary
from autocheck.services.evidence_retriever import EvidenceRetriever
from autocheck.services.reference_manager import ReferenceManager
from autocheck.utils.citations import extract_cited_sentences, match_citation_to_reference


def test_pipeline_smoke_run_without_network(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
            "References\n"
            "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    report, paths = pipeline.run(source_path=source_path, skip_download=True)

    assert report.summary.total_claims == 1
    assert report.summary.total_assessments == 1
    assert report.assessments[0].verdict == VerificationLabel.NOT_FOUND
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert paths["events"].exists()
    assert Path(paths["json"]).read_text(encoding="utf-8")


def test_pipeline_emits_incremental_events(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
            "References\n"
            "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    events = list(pipeline.run_incremental(source_path=source_path, skip_download=True))

    assert events[0].event == "stage_started"
    assert any(event.event == "reference_processed" for event in events)
    assert any(event.event == "assessment_ready" for event in events)
    assert events[-1].event == "report_completed"
    first_reference_processed = next(
        index for index, event in enumerate(events) if event.event == "reference_processed"
    )
    first_assessment_ready = next(
        index for index, event in enumerate(events) if event.event == "assessment_ready"
    )
    resolve_completed = next(
        index
        for index, event in enumerate(events)
        if event.event == "stage_completed" and event.payload["stage"] == "resolve_references"
    )
    assert first_reference_processed < first_assessment_ready < resolve_completed

    report, paths = pipeline.run(source_path=source_path, skip_download=True)
    event_lines = [
        json.loads(line)
        for line in Path(paths["events"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(event_lines) >= len(events)
    assert event_lines[-1]["event"] == "report_completed"
    assert report.summary.total_assessments == 1


def test_partial_report_is_written_before_completion(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
            "References\n"
            "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    report_path = (
        project_root
        / "data"
        / "workspaces"
        / "draft"
        / "reports"
        / "draft.report.json"
    )

    for event in pipeline.run_incremental(source_path=source_path, skip_download=True):
        if event.event == "assessment_ready":
            break

    assert report_path.exists()
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["status"] == "running"
    assert report_payload["progress"]["completed_assessments"] >= 1
    assert len(report_payload["assessments"]) >= 1


def test_pipeline_can_limit_processed_references(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "draft.txt"
    source_path.write_text(
        (
            "Claim one is supported by the first source [1].\n"
            "Claim two is supported by the second source [2].\n\n"
            "References\n"
            "[1] Author A. First Paper. 2017.\n"
            "[2] Author B. Second Paper. 2018.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    report, _paths = pipeline.run(
        source_path=source_path,
        skip_download=True,
        max_references=1,
    )

    assert len(report.parsed_document.references) == 1
    assert report.parsed_document.references[0].ref_id == "[1]"
    assert len(report.assessments) == 1
    assert report.assessments[0].citation_marker == "[1]"
    assert report.progress is not None
    assert report.progress.total_references == 1
    assert report.progress.total_assessments == 1


def test_pipeline_uses_per_source_workspace_directories(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    source_path = project_root / "attention-note.txt"
    source_path.write_text(
        (
            "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
            "References\n"
            "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    _report, paths = pipeline.run(source_path=source_path, skip_download=True)

    workspace_dir = project_root / "data" / "workspaces" / "attention-note"
    assert workspace_dir.exists()
    assert paths["json"] == workspace_dir / "reports" / "attention-note.report.json"
    assert paths["markdown"] == workspace_dir / "reports" / "attention-note.report.md"
    assert paths["events"] == workspace_dir / "reports" / "attention-note.events.jsonl"
    assert (workspace_dir / "processed" / "library_index.json").exists()


def test_pipeline_accepts_source_url_and_downloads_into_workspace(tmp_path, monkeypatch) -> None:
    project_root = tmp_path
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOCHECK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    remote_text = (
        "Transformers significantly improve sequence modeling quality on long-context tasks [1].\n\n"
        "References\n"
        "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. 2017.\n"
    )

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/plain"}
        url = "https://example.com/papers/attention-note.txt"
        content = remote_text.encode("utf-8")

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "autocheck.services.source_resolver.requests.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    settings = AppSettings.from_env(project_root=project_root)
    pipeline = AutoCheckPipeline(settings)
    report, paths = pipeline.run(
        source_path="https://example.com/papers/attention-note.txt",
        skip_download=True,
    )

    workspace_dir = project_root / "data" / "workspaces" / "attention-note"
    assert report.source_path.endswith("data/workspaces/attention-note/inputs/attention-note.txt")
    assert paths["json"] == workspace_dir / "reports" / "attention-note.report.json"
    assert (workspace_dir / "inputs" / "attention-note.txt").exists()


def test_numeric_citation_matching_is_exact() -> None:
    references = [
        ReferenceEntry(ref_id="[1]", raw_text="[1] First ref", aliases=["[1]"]),
        ReferenceEntry(ref_id="[13]", raw_text="[13] Thirteenth ref", aliases=["[13]"]),
    ]

    assert match_citation_to_reference("[13]", references).ref_id == "[13]"
    assert match_citation_to_reference("[3]", references) is None


def test_settings_default_to_llm_verification_only(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AUTOCHECK_ENABLE_LLM_EXTRACTION", raising=False)
    monkeypatch.delenv("AUTOCHECK_ENABLE_LLM_VERIFICATION", raising=False)
    monkeypatch.delenv("AUTOCHECK_CHAT_MODEL", raising=False)
    monkeypatch.delenv("AUTOCHECK_VERIFY_MODEL", raising=False)

    settings = AppSettings.from_env(project_root=tmp_path)
    assert settings.enable_llm_extraction is False
    assert settings.enable_llm_verification is True
    assert settings.chat_model == "gpt-5.4"
    assert settings.verify_model == "gpt-5.4"


def test_extractor_ignores_conference_header_like_nips_2017() -> None:
    text = "31st Conference on Neural Information Processing Systems (NIPS 2017), Long Beach, CA, USA."
    assert extract_cited_sentences(text) == []


def test_reference_parsing_handles_author_initials_and_abs_arxiv_ids(tmp_path) -> None:
    source_path = tmp_path / "draft.txt"
    source_path.write_text(
        (
            "Transformers use attention [3].\n\n"
            "References\n"
            "[3] Denny Britz, Anna Goldie, Minh-Thang Luong, and Quoc V . Le. "
            "Massive exploration of neural machine translation architectures. "
            "CoRR, abs/1703.03906, 2017.\n"
        ),
        encoding="utf-8",
    )

    parsed = DocumentClaimReferenceExtractor(chat_model=None).extract(source_path)

    assert parsed.references[0].title == "Massive exploration of neural machine translation architectures"
    assert parsed.references[0].authors[-1] == "Quoc V. Le"
    assert parsed.references[0].arxiv_id == "1703.03906"


def test_llm_merge_preserves_unmatched_heuristic_claims_and_references() -> None:
    extractor = DocumentClaimReferenceExtractor(chat_model=None)
    heuristic_claims = [
        ClaimRecord(claim_id="claim-1", text="A [1]", citation_markers=["[1]"]),
        ClaimRecord(claim_id="claim-2", text="B [2]", citation_markers=["[2]"]),
    ]
    llm_claims = [ClaimRecord(claim_id="llm-1", text="A [1]", citation_markers=["[1]"])]

    merged_claims = extractor._merge_claims(heuristic_claims, llm_claims)
    assert [claim.claim_id for claim in merged_claims] == ["claim-1", "claim-2"]

    heuristic_refs = [
        ReferenceEntry(ref_id="[1]", raw_text="[1] First. One. 2017.", title="One"),
        ReferenceEntry(ref_id="[2]", raw_text="[2] Second. Two. 2018.", title="Two"),
    ]
    llm_refs = [
        ReferenceEntry(
            ref_id="[2]",
            raw_text="[2] Second. Two revised. 2018.",
            title="Two revised",
        )
    ]

    merged_refs = extractor._merge_references(heuristic_refs, llm_refs)
    assert [reference.ref_id for reference in merged_refs] == ["[1]", "[2]"]
    assert merged_refs[1].title == "Two revised"


def test_library_uses_reference_identity_not_local_numeric_marker(tmp_path) -> None:
    library = PaperLibrary(tmp_path / "downloads", tmp_path / "processed")
    library.downloads_dir.mkdir(parents=True, exist_ok=True)
    library.processed_dir.mkdir(parents=True, exist_ok=True)

    first_reference = ReferenceEntry(
        ref_id="[1]",
        raw_text="[1] First paper. abs/1111.1111, 2017.",
        title="First paper",
        authors=["Author A"],
        year=2017,
        arxiv_id="1111.1111",
    )
    second_reference = ReferenceEntry(
        ref_id="[1]",
        raw_text="[1] Second paper. abs/2222.2222, 2018.",
        title="Second paper",
        authors=["Author B"],
        year=2018,
        arxiv_id="2222.2222",
    )

    first_pdf = b"%PDF-1.4 first"
    second_pdf = b"%PDF-1.4 second"

    library.save_download(
        first_reference,
        match=type(
            "Match",
            (),
            {
                "title": "First paper",
                "pdf_url": "https://example.com/first.pdf",
                "landing_page_url": "https://example.com/first",
                "resolver_name": "test",
            },
        )(),
        pdf_bytes=first_pdf,
    )
    library.save_download(
        second_reference,
        match=type(
            "Match",
            (),
            {
                "title": "Second paper",
                "pdf_url": "https://example.com/second.pdf",
                "landing_page_url": "https://example.com/second",
                "resolver_name": "test",
            },
        )(),
        pdf_bytes=second_pdf,
    )

    assert library.get(first_reference).title == "First paper"
    assert library.get(second_reference).title == "Second paper"


def test_reference_manager_reuses_processed_text_without_marking_skip(tmp_path) -> None:
    library = PaperLibrary(tmp_path / "downloads", tmp_path / "processed")
    library.downloads_dir.mkdir(parents=True, exist_ok=True)
    library.processed_dir.mkdir(parents=True, exist_ok=True)
    manager = ReferenceManager(library)
    reference = ReferenceEntry(
        ref_id="[1]",
        raw_text="[1] First paper. 2017.",
        title="First paper",
        authors=["Author A"],
        year=2017,
    )
    library.save_text(reference, "cached text")

    record = next(manager.iter_prepare_references([reference], skip_download=True))

    assert record.status == "processed"
    assert record.text_path is not None


def test_reference_manager_retries_title_with_case_variants(tmp_path) -> None:
    library = PaperLibrary(tmp_path / "downloads", tmp_path / "processed")
    library.downloads_dir.mkdir(parents=True, exist_ok=True)
    library.processed_dir.mkdir(parents=True, exist_ok=True)
    manager = ReferenceManager(library)
    reference = ReferenceEntry(
        ref_id="[1]",
        raw_text="[1] Attention Is All You Need. 2017.",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani"],
        year=2017,
    )

    class LowerOnlyResolver:
        name = "lower-only"

        def locate(self, candidate_reference: ReferenceEntry):
            if candidate_reference.title != "attention is all you need":
                return None
            return type(
                "Match",
                (),
                {
                    "title": candidate_reference.title,
                    "pdf_url": "https://example.com/lower.pdf",
                    "landing_page_url": "https://example.com/lower",
                    "resolver_name": "lower-only",
                },
            )()

    manager.resolvers = [LowerOnlyResolver()]
    manager._download_pdf = lambda _match: b"%PDF-1.4 demo"  # type: ignore[method-assign]

    record = next(manager.iter_prepare_references([reference]))

    assert record.status == "downloaded"
    assert record.pdf_path is not None
    assert record.title == "attention is all you need"


def test_verifier_falls_back_when_structured_llm_parsing_fails(tmp_path) -> None:
    settings = AppSettings.from_env(project_root=tmp_path)
    library = PaperLibrary(tmp_path / "downloads", tmp_path / "processed")
    library.downloads_dir.mkdir(parents=True, exist_ok=True)
    library.processed_dir.mkdir(parents=True, exist_ok=True)

    class BrokenChatModel:
        def with_structured_output(self, _schema, **_kwargs):
            return RunnableLambda(
                lambda _input: (_ for _ in ()).throw(RuntimeError("boom"))
            )

    verifier = ClaimCitationVerifier(
        library=library,
        retriever=EvidenceRetriever(settings),
        chat_model=BrokenChatModel(),
    )

    decision = verifier._verify_with_llm(
        ClaimRecord(claim_id="claim-1", text="A claim", citation_markers=["[1]"]),
        "[1]",
        ReferenceEntry(ref_id="[1]", raw_text="[1] Ref", title="Ref"),
        [EvidenceChunk(chunk_id="[1]#1", ref_id="[1]", score=0.3, text="A claim")],
    )

    assert decision.verdict == VerificationLabel.PARTIAL_SUPPORT
    assert "fell back to lexical scoring" in decision.concerns[0]


def test_extractor_uses_function_calling_for_structured_output(tmp_path) -> None:
    source_path = tmp_path / "draft.txt"
    source_path.write_text(
        (
            "Transformers use attention [1].\n\n"
            "References\n"
            "[1] Author A. Test Paper. 2017.\n"
        ),
        encoding="utf-8",
    )

    class RecordingChatModel:
        def __init__(self) -> None:
            self.calls = []

        def with_structured_output(self, schema, **kwargs):
            self.calls.append((schema, kwargs))
            return RunnableLambda(lambda _input: LLMClaimExtraction())

    chat_model = RecordingChatModel()
    extractor = DocumentClaimReferenceExtractor(chat_model=chat_model)
    extractor.extract(source_path)

    assert chat_model.calls[0][0] is LLMClaimExtraction
    assert chat_model.calls[0][1]["method"] == "function_calling"


def test_verifier_uses_function_calling_for_structured_output(tmp_path) -> None:
    settings = AppSettings.from_env(project_root=tmp_path)
    library = PaperLibrary(tmp_path / "downloads", tmp_path / "processed")
    library.downloads_dir.mkdir(parents=True, exist_ok=True)
    library.processed_dir.mkdir(parents=True, exist_ok=True)

    class RecordingChatModel:
        def __init__(self) -> None:
            self.calls = []

        def with_structured_output(self, schema, **kwargs):
            self.calls.append((schema, kwargs))
            return RunnableLambda(
                lambda _input: LLMVerificationDecision(
                    verdict=VerificationLabel.PARTIAL_SUPPORT,
                    confidence=0.5,
                    reasoning="ok",
                    used_chunk_ids=["[1]#1"],
                )
            )

    chat_model = RecordingChatModel()
    verifier = ClaimCitationVerifier(
        library=library,
        retriever=EvidenceRetriever(settings),
        chat_model=chat_model,
    )

    verifier._verify_with_llm(
        ClaimRecord(claim_id="claim-1", text="A claim", citation_markers=["[1]"]),
        "[1]",
        ReferenceEntry(ref_id="[1]", raw_text="[1] Ref", title="Ref"),
        [EvidenceChunk(chunk_id="[1]#1", ref_id="[1]", score=0.3, text="A claim")],
    )

    assert chat_model.calls[0][0] is LLMVerificationDecision
    assert chat_model.calls[0][1]["method"] == "function_calling"
