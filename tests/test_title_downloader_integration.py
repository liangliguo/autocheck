"""
Integration test for TitleDownloader with real network calls.

Tests downloading papers by title using arXiv and Sci-Hub fallback.
Run with: uv run pytest tests/test_title_downloader_integration.py -v -s
"""
from __future__ import annotations

import pytest
from pathlib import Path

from autocheck.resolvers.title_downloader import TitleDownloader
from autocheck.schemas.models import ReferenceEntry


# Test papers from testpaper.md - classic ML/DL papers
TEST_PAPERS = [
    # Paper title, expected to have arXiv version
    ("Imagenet classification with deep convolutional neural networks", True),  # AlexNet - famous paper
    ("Visualizing and understanding convolutional neural networks", True),  # ZFNet
    ("Rich feature hierarchies for accurate object detection and semantic segmentation", True),  # R-CNN
    ("Efficient estimation of word representations in vector space", True),  # Word2Vec
    ("Building high-level features using large scale unsupervised learning", True),  # Google Brain cat paper
]


class TestTitleDownloaderIntegration:
    """Integration tests that make real network calls."""

    @pytest.fixture
    def downloader(self):
        return TitleDownloader()

    @pytest.mark.parametrize("title,_expected_arxiv", TEST_PAPERS)
    def test_download_paper_by_title(self, downloader, title, _expected_arxiv, tmp_path):
        """Test downloading a paper by title."""
        output_path = tmp_path / "paper.pdf"
        
        pdf_bytes, match = downloader.download_by_title(title, output_path=output_path)
        
        if pdf_bytes is not None:
            print(f"\n✓ Downloaded: {title[:50]}...")
            print(f"  Resolver: {match.resolver_name}")
            print(f"  Match score: {match.score:.2f}")
            print(f"  PDF size: {len(pdf_bytes)} bytes")
            assert output_path.exists()
            assert output_path.stat().st_size > 1000  # Should be more than 1KB
            assert pdf_bytes.startswith(b"%PDF")
        else:
            print(f"\n✗ Failed to download: {title[:50]}...")
            # Don't fail the test - some papers may not be available
            pytest.skip(f"Could not download: {title}")

    def test_download_with_arxiv_id(self, downloader, tmp_path):
        """Test downloading a paper using arXiv ID."""
        reference = ReferenceEntry(
            ref_id="test",
            raw_text="Visualizing and understanding convolutional neural networks",
            title="Visualizing and understanding convolutional neural networks",
            arxiv_id="1311.2901",
        )
        
        output_path = tmp_path / "paper.pdf"
        pdf_bytes, match = downloader.download_reference(reference, output_path=output_path)
        
        if pdf_bytes:
            print(f"\n✓ Downloaded via arXiv ID: {reference.arxiv_id}")
            print(f"  Resolver: {match.resolver_name}")
            print(f"  PDF size: {len(pdf_bytes)} bytes")
            assert match.resolver_name == "arxiv"
            assert output_path.exists()
        else:
            pytest.skip("Could not download via arXiv ID")

    def test_download_with_doi(self, downloader, tmp_path):
        """Test downloading a paper using DOI via Sci-Hub."""
        # Using a well-known paper DOI
        reference = ReferenceEntry(
            ref_id="test",
            raw_text="ImageNet Large Scale Visual Recognition Challenge",
            title="ImageNet Large Scale Visual Recognition Challenge",
            doi="10.1007/s11263-015-0816-y",
        )
        
        output_path = tmp_path / "paper.pdf"
        pdf_bytes, match = downloader.download_reference(reference, output_path=output_path)
        
        if pdf_bytes:
            print(f"\n✓ Downloaded via DOI: {reference.doi}")
            print(f"  Resolver: {match.resolver_name}")
            print(f"  PDF size: {len(pdf_bytes)} bytes")
            assert output_path.exists()
        else:
            pytest.skip("Could not download via DOI (Sci-Hub may be unavailable)")


class TestArxivDownload:
    """Test arXiv-specific downloads."""

    @pytest.fixture
    def downloader(self):
        return TitleDownloader()

    def test_arxiv_search_by_title(self, downloader):
        """Test that arXiv search finds papers by title."""
        # "Attention Is All You Need" - famous transformer paper
        title = "Attention Is All You Need"
        
        pdf_bytes, match = downloader.download_by_title(title)
        
        if pdf_bytes:
            print(f"\n✓ Found: {title}")
            print(f"  Resolver: {match.resolver_name}")
            print(f"  Title: {match.title}")
            print(f"  Score: {match.score:.2f}")
            assert match.resolver_name == "arxiv"
        else:
            pytest.skip("Could not find paper on arXiv")


class TestScihubDownload:
    """Test Sci-Hub specific downloads."""

    @pytest.fixture
    def downloader(self):
        return TitleDownloader()

    def test_scihub_via_crossref_lookup(self, downloader, tmp_path):
        """Test Sci-Hub download after CrossRef DOI lookup."""
        # Paper that's likely only on Sci-Hub (not arXiv)
        title = "The mnist database of handwritten digits"
        
        pdf_bytes, match = downloader.download_by_title(title)
        
        if pdf_bytes:
            print(f"\n✓ Downloaded: {title}")
            print(f"  Resolver: {match.resolver_name}")
            if match.external_id:
                print(f"  DOI: {match.external_id}")
        else:
            print(f"\n✗ Could not download: {title}")
            pytest.skip("Sci-Hub may be unavailable")


def test_download_summary():
    """Summary test that tries all papers and reports results."""
    downloader = TitleDownloader()
    
    papers = [
        "Imagenet classification with deep convolutional neural networks",
        "Visualizing and understanding convolutional neural networks", 
        "Rich feature hierarchies for accurate object detection and semantic segmentation",
        "Efficient estimation of word representations in vector space",
        "Attention Is All You Need",
    ]
    
    results = {"success": [], "failed": []}
    
    print("\n" + "=" * 60)
    print("Download Summary Test")
    print("=" * 60)
    
    for title in papers:
        pdf_bytes, match = downloader.download_by_title(title)
        
        if pdf_bytes:
            results["success"].append((title, match.resolver_name, len(pdf_bytes)))
            print(f"✓ {title[:45]}... [{match.resolver_name}]")
        else:
            results["failed"].append(title)
            print(f"✗ {title[:45]}...")
    
    print("\n" + "-" * 60)
    print(f"Success: {len(results['success'])}/{len(papers)}")
    print(f"Failed: {len(results['failed'])}/{len(papers)}")
    
    # At least some papers should download successfully
    assert len(results["success"]) > 0, "No papers could be downloaded"
    
    if results["failed"]:
        print("\nFailed papers:")
        for title in results["failed"]:
            print(f"  - {title}")


if __name__ == "__main__":
    # Run summary test directly
    test_download_summary()
