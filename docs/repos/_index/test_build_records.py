import json
import build_records as br


def test_normalize_chapter_folder_variants():
    assert br.normalize_chapter("Chapter_13") == "ch13"
    assert br.normalize_chapter("chapter1") == "ch01"
    assert br.normalize_chapter("ch2") == "ch02"
    assert br.normalize_chapter("Chapter01") == "ch01"
    assert br.normalize_chapter("commons") is None
    assert br.normalize_chapter("writing_assistant") is None
    assert br.normalize_chapter(".git") is None


def test_whitelist_and_skip():
    assert br.is_code_file("a.py")
    assert br.is_code_file("notebook.ipynb")
    assert br.is_code_file("Dockerfile")
    assert br.is_code_file("requirements.txt")
    assert not br.is_code_file("data.csv")
    assert not br.is_code_file("fig.png")
    assert not br.is_code_file("model.pkl")


def test_parse_imports_python():
    src = "import os\nfrom langchain.chat_models import ChatOpenAI\nimport neo4j.graph\n"
    assert br.parse_imports(src, "py") == {"os", "langchain", "neo4j"}


def test_parse_imports_python_multi():
    assert br.parse_imports("import os, sys\nimport json\n", "py") == {"os", "sys", "json"}


def test_parse_imports_js():
    src = "import { foo } from 'langchain';\nconst x = require('neo4j-driver');\n"
    assert br.parse_imports(src, "js") == {"langchain", "neo4j-driver"}


def test_parse_entities_python():
    src = "import x\n\ndef build_graph():\n    pass\n\nclass Retriever:\n    def m(self): pass\n"
    assert br.parse_entities(src) == ["build_graph", "Retriever"]


def test_extract_notebook_cells():
    nb = json.dumps({
        "cells": [
            {"cell_type": "markdown", "source": ["# Title\n", "text"]},
            {"cell_type": "code", "source": ["import langchain\n", "x=1"]},
            {"cell_type": "raw", "source": ["ignore"]},
        ]
    })
    code, md = br.extract_notebook(nb)
    assert "import langchain" in code
    assert "# Title" in md
    assert "ignore" not in code and "ignore" not in md
