"""
测试合同识别功能
使用 tests/contract/ 目录下的真实合同文件（test1.docx, test2.pdf）
验证文件解析和合同审查链的完整流程
"""
import os
import sys
import time

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from src.config.config import config
from src.utils.file_converter import convert_to_markdown
from src.chain.contract_review import get_contract_review_chain


# 测试文件路径
CONTRACT_DIR = os.path.join(PROJECT_ROOT, 'tests', 'contract')
TEST_DOCX = os.path.join(CONTRACT_DIR, 'test1.docx')
TEST_PDF = os.path.join(CONTRACT_DIR, 'test2.pdf')


def test_file_exists():
    """测试1：验证测试合同文件存在"""
    print("=" * 60)
    print("测试1：验证测试合同文件存在")
    print("=" * 60)

    assert os.path.exists(TEST_DOCX), f"找不到测试文件: {TEST_DOCX}"
    print(f"  ✓ test1.docx 存在 ({os.path.getsize(TEST_DOCX)} bytes)")

    assert os.path.exists(TEST_PDF), f"找不到测试文件: {TEST_PDF}"
    print(f"  ✓ test2.pdf 存在 ({os.path.getsize(TEST_PDF)} bytes)")
    print()


def test_docx_recognition():
    """测试2：测试 DOCX 合同文件识别（转换为 Markdown）"""
    print("=" * 60)
    print("测试2：DOCX 合同识别 (test1.docx)")
    print("=" * 60)

    start = time.time()
    markdown_text = convert_to_markdown(TEST_DOCX)
    elapsed = time.time() - start

    assert markdown_text, "DOCX 转换结果为空"
    assert len(markdown_text) > 50, f"转换内容过短 ({len(markdown_text)} 字符)，可能解析失败"

    print(f"  ✓ 转换成功，耗时 {elapsed:.2f}s")
    print(f"  ✓ 提取文本长度: {len(markdown_text)} 字符")
    print(f"\n  --- 前500字预览 ---")
    print(f"  {markdown_text[:500]}")
    print(f"  --- 预览结束 ---\n")
    return markdown_text


def test_pdf_recognition():
    """测试3：测试 PDF 合同文件识别（PaddleOCR）"""
    print("=" * 60)
    print("测试3：PDF 合同识别 (test2.pdf)")
    print("=" * 60)

    start = time.time()
    markdown_text = convert_to_markdown(TEST_PDF)
    elapsed = time.time() - start

    assert markdown_text, "PDF 转换结果为空"
    assert len(markdown_text) > 50, f"转换内容过短 ({len(markdown_text)} 字符)，可能解析失败"

    print(f"  ✓ 转换成功，耗时 {elapsed:.2f}s")
    print(f"  ✓ 提取文本长度: {len(markdown_text)} 字符")
    print(f"\n  --- 前500字预览 ---")
    print(f"  {markdown_text[:500]}")
    print(f"  --- 预览结束 ---\n")
    return markdown_text


def test_contract_review_docx(contract_text=None):
    """测试4：对 DOCX 合同执行完整审查"""
    print("=" * 60)
    print("测试4：DOCX 合同审查 (test1.docx)")
    print("=" * 60)

    if contract_text is None:
        contract_text = convert_to_markdown(TEST_DOCX)

    print("  正在初始化合同审查链...")
    review_chain = get_contract_review_chain(config)

    print("  正在执行审查（可能需要1-2分钟）...")
    start = time.time()
    result = review_chain.invoke({"contract_text": contract_text})
    elapsed = time.time() - start

    # 验证结果结构
    assert "clauses_analysis" in result, "结果缺少 clauses_analysis"
    assert "summary_report" in result, "结果缺少 summary_report"
    assert "total_clauses" in result, "结果缺少 total_clauses"
    assert result["total_clauses"] > 0, "未拆解出任何条款"
    assert len(result["clauses_analysis"]) > 0, "条款分析结果为空"

    print(f"\n  ✓ 审查完成，耗时 {elapsed:.2f}s")
    print(f"  ✓ 拆解条款数: {result['total_clauses']}")
    print(f"  ✓ 分析结果数: {len(result['clauses_analysis'])}")

    # 打印每个条款的风险等级
    print(f"\n  --- 条款风险概览 ---")
    for clause in result["clauses_analysis"]:
        risk = clause.get("risk_level", "未知")
        section = clause.get("section", "")
        print(f"    [{risk}] {section} - {clause['clause_text'][:40]}...")

    print(f"\n  --- 汇总报告(前300字) ---")
    print(f"  {result['summary_report'][:300]}")
    print()
    return result


def test_contract_review_pdf(contract_text=None):
    """测试5：对 PDF 合同执行完整审查"""
    print("=" * 60)
    print("测试5：PDF 合同审查 (test2.pdf)")
    print("=" * 60)

    if contract_text is None:
        contract_text = convert_to_markdown(TEST_PDF)

    print("  正在初始化合同审查链...")
    review_chain = get_contract_review_chain(config)

    print("  正在执行审查（可能需要1-2分钟）...")
    start = time.time()
    result = review_chain.invoke({"contract_text": contract_text})
    elapsed = time.time() - start

    assert "clauses_analysis" in result, "结果缺少 clauses_analysis"
    assert result["total_clauses"] > 0, "未拆解出任何条款"

    print(f"\n  ✓ 审查完成，耗时 {elapsed:.2f}s")
    print(f"  ✓ 拆解条款数: {result['total_clauses']}")
    print(f"  ✓ 分析结果数: {len(result['clauses_analysis'])}")

    print(f"\n  --- 条款风险概览 ---")
    for clause in result["clauses_analysis"]:
        risk = clause.get("risk_level", "未知")
        section = clause.get("section", "")
        print(f"    [{risk}] {section} - {clause['clause_text'][:40]}...")

    print(f"\n  --- 汇总报告(前300字) ---")
    print(f"  {result['summary_report'][:300]}")
    print()
    return result


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  合同识别功能测试")
    print("=" * 60 + "\n")

    # 测试1：文件存在性
    test_file_exists()

    # 测试2：DOCX 识别
    #docx_text = test_docx_recognition()

    # 测试3：PDF 识别
    pdf_text = test_pdf_recognition()

    # 测试4：DOCX 合同审查
    #test_contract_review_docx(docx_text)

    # 测试5：PDF 合同审查
    test_contract_review_pdf(pdf_text)

    print("\n" + "=" * 60)
    print("  ✅ 全部测试通过")
    print("=" * 60)
