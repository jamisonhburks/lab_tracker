"""import_publications — the dependency-free BibTeX parse used to seed the coverage map (day-0)."""
import import_publications as ip


def test_parse_extracts_title_and_year_braced_and_quoted():
    bib = """
    @article{smith2024,
      title = {Multimodal foundation model for OCT and fundus disease classification},
      year = {2024},
      author = {Smith, Jane and Doe, John}
    }
    @inproceedings{jones2023,
      title = "Self-supervised pretraining of ECG representations",
      year = {2023},
      author = {Jones, Amy}
    }
    """
    entries = ip.parse_bibtex(bib)
    assert len(entries) == 2
    assert entries[0]["title"].startswith("Multimodal foundation model")
    assert entries[0]["year"] == 2024
    assert entries[1]["title"].startswith("Self-supervised")
    assert entries[1]["year"] == 2023


def test_parse_handles_nested_braces_and_skips_titleless():
    bib = """
    @article{a, title = {{Deep} Learning for {ECG}}, year={2022}}
    @misc{b, author = {No Title Here}, year = {2020}}
    """
    entries = ip.parse_bibtex(bib)
    assert len(entries) == 1
    assert entries[0]["title"] == "Deep Learning for ECG"


def test_parse_non_numeric_year_is_none_and_garbage_is_empty():
    assert ip.parse_bibtex("not bibtex at all") == []
    entries = ip.parse_bibtex("@x{k, title={T}, year={in press}}")
    assert entries[0]["year"] is None
