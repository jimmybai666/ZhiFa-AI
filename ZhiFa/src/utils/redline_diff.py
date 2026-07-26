"""
文本红线对比工具 - 生成两段文本的 HTML 差异对比
"""


def compute_redline_diff(text1: str, text2: str) -> str:
    """
    计算两段文本的语义级红线差异对比。
    返回包含 <del> 和 <ins> 标签的 HTML 字符串。
    """
    try:
        import diff_match_patch as dmp_module
    except ImportError:
        return "Error: diff-match-patch library not installed. Please run `pip install diff-match-patch`."

    dmp = dmp_module.diff_match_patch()

    diffs = dmp.diff_main(text1, text2)
    dmp.diff_cleanupSemantic(diffs)

    html_output = dmp.diff_prettyHtml(diffs)
    html_output = html_output.replace("&para;<br>", "<br>")

    return html_output
