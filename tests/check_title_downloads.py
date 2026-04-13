from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from autocheck.resolvers.crossref import CrossRefResolver
from autocheck.resolvers.title_downloader import TitleDownloader
from autocheck.schemas.models import ReferenceEntry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check DOI lookup and download results for paper titles.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="testpaper.md",
        help="Path to a text file with one title per line.",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Optional directory to save successfully downloaded PDFs.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the full results as JSON.",
    )
    parser.add_argument(
        "-n",
        "--max-titles",
        type=int,
        default=None,
        help="Only process the first N titles.",
    )
    return parser


def read_titles(path: Path) -> list[str]:
    titles: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        title = line.strip()
        if title:
            titles.append(title)
    return titles


def safe_stem(index: int, title: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._")
    stem = normalized[:120] or f"title_{index:03d}"
    return f"{index:03d}_{stem}"


def extract_doi(external_id: str | None) -> str | None:
    if not external_id:
        return None
    if external_id.startswith("doi:"):
        return external_id[4:]
    return external_id


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input).resolve()
    titles = read_titles(input_path)
    if args.max_titles is not None:
        titles = titles[: args.max_titles]

    download_dir = Path(args.download_dir).resolve() if args.download_dir else None
    if download_dir:
        download_dir.mkdir(parents=True, exist_ok=True)

    crossref = CrossRefResolver()
    downloader = TitleDownloader()
    results: list[dict[str, Any]] = []

    for index, title in enumerate(titles, start=1):
        reference = ReferenceEntry(
            ref_id=f"title-{index}",
            raw_text=title,
            title=title,
        )

        doi_match = None
        try:
            doi_match = crossref.locate(reference)
        except Exception as exc:
            doi_error = str(exc)
        else:
            doi_error = None

        output_path = download_dir / f"{safe_stem(index, title)}.pdf" if download_dir else None
        pdf_bytes = None
        download_match = None
        try:
            pdf_bytes, download_match = downloader.download_reference(reference, output_path=output_path)
        except Exception as exc:
            download_error = str(exc)
        else:
            download_error = None

        if output_path and not pdf_bytes and output_path.exists():
            output_path.unlink()

        result = {
            "index": index,
            "title": title,
            "doi_lookup": {
                "success": doi_match is not None,
                "doi": extract_doi(doi_match.external_id) if doi_match else None,
                "resolver": doi_match.resolver_name if doi_match else None,
                "score": doi_match.score if doi_match else None,
                "matched_title": doi_match.title if doi_match else None,
                "error": doi_error,
            },
            "download": {
                "success": pdf_bytes is not None,
                "resolver": download_match.resolver_name if download_match else None,
                "external_id": download_match.external_id if download_match else None,
                "saved_pdf": str(output_path) if output_path and pdf_bytes else None,
                "error": download_error,
            },
        }
        results.append(result)

        doi_value = result["doi_lookup"]["doi"] or "-"
        download_status = "OK" if result["download"]["success"] else "FAIL"
        download_resolver = result["download"]["resolver"] or "-"
        print(
            f"{index:02d}. DOI={doi_value} | download={download_status} "
            f"| resolver={download_resolver} | {title}",
            flush=True,
        )

    if args.output_json:
        output_json = Path(args.output_json).resolve()
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON: {output_json}")

    doi_success = sum(1 for item in results if item["doi_lookup"]["success"])
    download_success = sum(1 for item in results if item["download"]["success"])
    print(f"Titles: {len(results)}")
    print(f"DOI found: {doi_success}")
    print(f"Download success: {download_success}")


if __name__ == "__main__":
    main()
