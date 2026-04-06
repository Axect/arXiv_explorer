from arxiv_explorer.core.arxiv_categories import ARXIV_CATEGORIES, fuzzy_search, get_all_categories


class TestCategoryData:
    def test_has_physics(self):
        assert "Physics" in ARXIV_CATEGORIES

    def test_has_cs(self):
        assert "Computer Science" in ARXIV_CATEGORIES

    def test_has_math(self):
        assert "Mathematics" in ARXIV_CATEGORIES

    def test_hep_ph_exists(self):
        assert "hep-ph" in ARXIV_CATEGORIES["Physics"]

    def test_cs_ai_exists(self):
        assert "cs.AI" in ARXIV_CATEGORIES["Computer Science"]

    def test_get_all_categories_flat(self):
        cats = get_all_categories()
        assert len(cats) > 100
        codes = {c[0] for c in cats}
        assert "hep-ph" in codes
        assert "cs.AI" in codes


class TestFuzzySearch:
    def test_exact_code_match(self):
        results = fuzzy_search("hep-ph")
        assert results[0][0] == "hep-ph"

    def test_prefix_match(self):
        results = fuzzy_search("hep")
        codes = [r[0] for r in results]
        assert "hep-ph" in codes
        assert "hep-th" in codes

    def test_full_name_match(self):
        results = fuzzy_search("quantum")
        codes = [r[0] for r in results]
        assert "quant-ph" in codes

    def test_partial_name_match(self):
        results = fuzzy_search("mach learn")
        codes = [r[0] for r in results]
        assert "cs.LG" in codes or "stat.ML" in codes

    def test_case_insensitive(self):
        results = fuzzy_search("CS.AI")
        assert results[0][0] == "cs.AI"

    def test_empty_query_returns_all(self):
        results = fuzzy_search("")
        assert len(results) > 100

    def test_no_match(self):
        results = fuzzy_search("xyznonexistent")
        assert len(results) == 0

    def test_returns_code_name_group(self):
        results = fuzzy_search("hep-ph")
        code, name, group = results[0]
        assert code == "hep-ph"
        assert "Phenomenology" in name
        assert group == "Physics"
