from input.text_inserter import TextInserter


def test_configure_method():
    inserter = TextInserter(method="clipboard")
    inserter.configure(method="keyboard")
    assert inserter.method == "keyboard"
