from pathlib import Path

from autocheck.services.document_loader import DocumentLoader


def test_load_pdf_text_skips_failing_pages(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 demo")

    class GoodPage:
        def extract_text(self, *args, **kwargs):
            return "first page"

    class BadPage:
        def extract_text(self, *args, **kwargs):
            raise RuntimeError("broken page")

    class FakeReader:
        is_encrypted = False

        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [GoodPage(), BadPage(), GoodPage()]

    monkeypatch.setattr("autocheck.services.document_loader.PdfReader", FakeReader)

    text = DocumentLoader().load_text(pdf_path)

    assert text == "first page\n\nfirst page"


def test_load_pdf_text_returns_empty_for_encrypted_pdf_without_password(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 demo")

    class FakeReader:
        is_encrypted = True
        pages = []

        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def decrypt(self, _password: str) -> None:
            raise RuntimeError("password required")

    monkeypatch.setattr("autocheck.services.document_loader.PdfReader", FakeReader)

    text = DocumentLoader().load_text(pdf_path)

    assert text == ""
