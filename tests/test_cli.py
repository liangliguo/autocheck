from autocheck.cli.main import build_parser


def test_build_parser_accepts_run_command() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["run", "tests/fixtures/sample_draft.txt", "-s", "-n", "2", "-o", "/tmp/out"]
    )
    assert args.command == "run"
    assert args.source == "tests/fixtures/sample_draft.txt"
    assert args.skip_download is True
    assert args.max_references == 2
    assert args.report_dir == "/tmp/out"
