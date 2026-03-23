from autocheck.cli.main import build_parser


def test_build_parser_accepts_run_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "tests/fixtures/sample_draft.txt", "--skip-download"])
    assert args.command == "run"
    assert args.source == "tests/fixtures/sample_draft.txt"
    assert args.skip_download is True
