import pytest

from minerva_hc.tools import read_file


@pytest.mark.docs
def test_read_valid_name():
    ok, text = read_file("evidencebased")
    assert ok and text.startswith("# #evidencebased")


@pytest.mark.docs
def test_read_hashtag_name():
    assert read_file("#EvidenceBased")[0]


def test_rejects_paths():
    for name in ("../.env", "a/b", "../../pyproject"):
        ok, text = read_file(name)
        assert not ok and "invalid name" in text


@pytest.mark.docs
def test_unknown_name_suggests():
    ok, text = read_file("evidencebase")
    assert not ok and "evidencebased" in text
