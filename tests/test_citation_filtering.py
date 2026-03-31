"""
测试引用标记提取功能，特别是过滤数学公式中的伪引用。
"""

from autocheck.utils.citations import extract_citation_markers, extract_cited_sentences


class TestCitationFiltering:
    """测试引用过滤功能，确保能正确区分真实引用和数学符号"""

    def test_math_interval_exclusion(self):
        """测试排除数学区间表达式"""
        # 数学公式中的区间不应该被识别为引用
        assert extract_citation_markers("x + r ∈ [0, 1]m") == []
        assert extract_citation_markers("value in [0, 1]") == []
        assert extract_citation_markers("range [0, 1]") == []
        assert extract_citation_markers("interval ∈ [0, 100]") == []
        assert extract_citation_markers("vector ∈ [0, 1]^d") == []
        assert extract_citation_markers("probability [0, 1]") == []
        assert extract_citation_markers("x ∈ [0, 1]") == []
        assert extract_citation_markers("[0,1]^n dimensional") == []

    def test_valid_citations(self):
        """测试识别真实的引用"""
        assert extract_citation_markers("This is a claim [1].") == ["[1]"]
        assert extract_citation_markers("This is a claim [1]") == ["[1]"]
        assert extract_citation_markers("The method [5] shows improvement.") == ["[5]"]
        assert extract_citation_markers("according to [8]") == ["[8]"]
        assert extract_citation_markers("see [2] for details") == ["[2]"]

    def test_multiple_citations(self):
        """测试识别多个引用"""
        result = extract_citation_markers("References [1, 2, 3]")
        assert set(result) == {"[1]", "[2]", "[3]"}
        
        result = extract_citation_markers("as shown in [23, 24, 25].")
        assert set(result) == {"[23]", "[24]", "[25]"}
        
        result = extract_citation_markers("The results [12, 13] show")
        assert set(result) == {"[12]", "[13]"}

    def test_citation_range(self):
        """测试引用范围"""
        result = extract_citation_markers("previous work [15-20]")
        assert set(result) == {"[15]", "[16]", "[17]", "[18]", "[19]", "[20]"}

    def test_mixed_context(self):
        """测试混合上下文"""
        # 两个独立引用
        text = "Studies [10] and [11] indicate"
        result = extract_citation_markers(text)
        assert set(result) == {"[10]", "[11]"}
        
        # 引导词后的引用
        assert extract_citation_markers("as shown in [5]") == ["[5]"]

    def test_edge_cases(self):
        """测试边缘情况"""
        # range from 应该被排除
        assert extract_citation_markers("range from [0, 10]") == []
        
        # 较大的数字应该被识别为引用
        assert extract_citation_markers("work [25]") == ["[25]"]
        
        # 数学符号后应该被排除
        assert extract_citation_markers("x + [1, 2]") == []

    def test_extract_cited_sentences(self):
        """测试提取包含引用的句子"""
        text = """
        This is a claim [1]. 
        Here x ∈ [0, 1] is a constraint.
        Another claim with reference [5].
        The probability is in range [0, 1].
        """
        
        sentences = extract_cited_sentences(text)
        
        # 应该只包含真正有引用的句子
        assert len(sentences) == 2
        assert any("claim [1]" in s for s in sentences)
        assert any("reference [5]" in s for s in sentences)
        # 不应该包含数学表达式的句子
        assert not any("x ∈ [0, 1]" in s for s in sentences)
        assert not any("range [0, 1]" in s for s in sentences)

    def test_chinese_context(self):
        """测试中文上下文"""
        # 中文句号后的引用
        assert extract_citation_markers("这是一个声明[1]。") == ["[1]"]
        
        # 中文数学表达式应该被排除
        assert extract_citation_markers("概率值在[0, 1]范围内") == []
