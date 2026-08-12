from graph_orchestrator.tools import edit_file, write_file

def test_edit_file(tmp_path):
    # Setup
    test_file = tmp_path / "test.txt"
    write_file(str(test_file), "Hello World\nHello World\nLine 3")

    # Test ambiguous (multiple occurrences)
    res = edit_file(str(test_file), "Hello World", "Hi World")
    assert "appears 2 times" in res or "Error" in res

    # Test exact match
    res = edit_file(str(test_file), "Line 3", "Line 4")
    assert "Successfully updated" in res
    
    with open(str(test_file), 'r') as f:
        content = f.read()
        assert "Line 4" in content
        assert "Line 3" not in content

    # Test replace_all
    res = edit_file(str(test_file), "Hello World", "Hi World", replace_all=True)
    assert "Successfully updated" in res
    
    with open(str(test_file), 'r') as f:
        content = f.read()
        assert content.count("Hi World") == 2
