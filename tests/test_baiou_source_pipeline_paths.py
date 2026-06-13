from baiou.source_pipeline.run_pipeline import ROOT, display_output_dir


def test_display_output_dir_accepts_external_output_root() -> None:
    external_output = ROOT.parent / "external_outputs" / "baiou" / "source" / "case_runs" / "case_001" / "group"

    assert display_output_dir(external_output) == str(external_output)
