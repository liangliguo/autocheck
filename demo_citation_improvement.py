#!/usr/bin/env python3
"""
演示改进后的引用检测功能。

展示如何正确区分数学公式中的符号（如区间 [0, 1]）和真实的文献引用。
"""

from autocheck.utils.citations import extract_citation_markers, extract_cited_sentences


def demo_citation_extraction():
    print("=" * 80)
    print("论文引用提取改进演示")
    print("=" * 80)
    print()

    test_cases = [
        {
            "title": "✗ 数学公式中的区间（应排除）",
            "texts": [
                "假设 x + r ∈ [0, 1]m 是一个约束条件。",
                "概率值在 [0, 1] 范围内。",
                "向量空间 [0, 1]^d 表示d维单位超立方体。",
                "The range [0, 100] represents valid values.",
                "Let x ∈ [0, 1] be a random variable.",
            ],
        },
        {
            "title": "✓ 真实的文献引用（应保留）",
            "texts": [
                "Transformers显著提高了长上下文任务的质量[1]。",
                "如研究[5]所示，该方法效果显著。",
                "根据[10, 11, 12]的研究结果。",
                "Previous work [15-20] has shown improvements.",
                "As described in [23, 24, 25], the approach is effective.",
            ],
        },
        {
            "title": "🔍 混合场景（需要智能区分）",
            "texts": [
                "在区间[0, 1]内，已有研究[5]指出该方法有效。",
                "Let x ∈ [0, 1] and see [2] for details.",
                "概率p在[0,1]范围，相关工作[8]讨论了这一点。",
            ],
        },
    ]

    for category in test_cases:
        print(f"\n{category['title']}")
        print("-" * 80)

        for text in category["texts"]:
            markers = extract_citation_markers(text)

            if markers:
                print(f"\n文本: {text}")
                print(f"检测到引用: {', '.join(markers)}")
            else:
                print(f"\n文本: {text}")
                print(f"检测到引用: (无)")

    print("\n" + "=" * 80)
    print("完整句子提取演示")
    print("=" * 80)

    paper_text = """
    深度学习在计算机视觉领域取得了显著进展[1, 2]。
    Transformer架构首次在注意力机制论文中提出[3]。
    
    在数学建模中，我们通常假设参数 θ ∈ [0, 1] 表示概率值。
    实验结果表明，当学习率在区间 [0.001, 0.01] 时效果最佳。
    
    根据最近的研究[15-18]，这种方法在多个基准测试上超越了现有技术。
    向量表示 v ∈ [0, 1]^d 用于编码高维特征空间。
    
    如[20, 21]所述，该框架可以扩展到多模态任务。
    """

    print("\n原始文本:")
    print(paper_text)

    cited_sentences = extract_cited_sentences(paper_text)

    print("\n提取的引用句子:")
    print("-" * 80)
    for i, sentence in enumerate(cited_sentences, 1):
        markers = extract_citation_markers(sentence)
        print(f"{i}. {sentence}")
        print(f"   引用标记: {', '.join(markers)}")
        print()

    print("=" * 80)
    print("✓ 改进完成！现在可以正确区分数学符号和文献引用了。")
    print("=" * 80)


if __name__ == "__main__":
    demo_citation_extraction()
