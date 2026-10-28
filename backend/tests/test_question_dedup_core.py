"""题目查重:归一化与签名的纯函数测试。"""
import pytest

from app.services.question_dedup_core import (
    MIN_FUZZY_LENGTH,
    SIMILAR_THRESHOLD,
    band_hashes,
    build_key,
    diff_snippets,
    normalize_latex,
    normalize_text,
    similarity,
)


def doc(*parts):
    content = []
    for p in parts:
        if isinstance(p, tuple):
            content.append({"type": "inlineMath", "attrs": {"latex": p[0]}})
        elif isinstance(p, dict):
            content.append(p)
        else:
            content.append({"type": "text", "text": p})
    return {"type": "doc", "content": [{"type": "paragraph", "content": content}]}


def opts(*texts):
    return [{"id": f"o{i}", "label": chr(65 + i), "content": doc(t)} for i, t in enumerate(texts)]


def key(content, q_type="free_response", options=None, stimulus=None):
    return build_key(q_type=q_type, content=content, options=options, stimulus_content=stimulus)


@pytest.mark.parametrize("a, b", [
    ("下列说法正确的是", "下列  说法\n正确的是"),           # 空白
    ("已知函数,求值。", "已知函数，求值."),               # 中英文标点
    ("ＡＢＣ１２３", "abc123"),                           # 全角 + 大小写
    ("1. 计算面积", "计算面积"),                         # 题号
    ("（2）计算面积", "计算面积"),
    ("① 计算面积", "计算面积"),
    ("例3、计算面积", "计算面积"),
    ("填空：____", "填空:（  ）"),                       # 填空占位
    ("求面积。", "求面积"),                               # 句末标点
])
def test_text_normalization_equivalences(a, b):
    assert normalize_text(a) == normalize_text(b)


def test_decimal_is_not_a_question_number():
    assert normalize_text("12.5 是多少") == "12.5是多少"


@pytest.mark.parametrize("a, b", [
    (r"X \sim B\left( {2,p} \right)", r"X\sim B( 2,p )"),
    (r"\dfrac{1}{2}", r"\frac {1}{2}"),
    (r"x^{2}", r"x^2"),
    (r"a \leq b", r"a\le b"),
    (r"\displaystyle \sum_{i=1}^{n} i", r"\sum_{i=1}^n i"),
])
def test_latex_equivalences(a, b):
    assert normalize_latex(a) == normalize_latex(b)


@pytest.mark.parametrize("a, b", [
    (r"\frac{1}{23}", r"\frac{12}{3}"),
    (r"\sin B", r"\sinB"),
    (r"x^{12}", r"x^{1}2"),
])
def test_latex_distinctions(a, b):
    assert normalize_latex(a) != normalize_latex(b)


def test_fingerprint_ignores_formatting_and_option_order():
    a = key(doc("1. 首都是（ ）"), "single_choice", opts("北京", "上海"))
    b = key(doc("首都是(    )"), "single_choice", opts(" 上海", "北京 "))
    assert a.fingerprint == b.fingerprint


def test_fingerprint_depends_on_type_options_and_stimulus():
    base = key(doc("首都是"), "single_choice", opts("北京", "上海"))
    assert base.fingerprint != key(doc("首都是"), "multiple_choice", opts("北京", "上海")).fingerprint
    assert base.fingerprint != key(doc("首都是"), "single_choice", opts("北京", "广州")).fingerprint
    q = doc("(1) 求 x 的值")
    assert key(q, stimulus=doc("材料一")).fingerprint != key(q, stimulus=doc("材料二")).fingerprint


def test_answer_does_not_matter_and_images_compare_by_asset():
    img1 = {"type": "image", "attrs": {"assetId": 7, "src": "/a"}}
    img2 = {"type": "image", "attrs": {"assetId": 7, "src": "/b"}}
    img3 = {"type": "image", "attrs": {"assetId": 8, "src": "/a"}}
    assert key(doc("如图", img1)).fingerprint == key(doc("如图", img2)).fingerprint
    assert key(doc("如图", img1)).fingerprint != key(doc("如图", img3)).fingerprint


def test_variant_numbers_change_signature_but_stay_similar():
    a = key(doc("一个长方形的长是 12 厘米，宽是 8 厘米，求它的面积和周长。"))
    b = key(doc("一个长方形的长是 15 厘米，宽是 8 厘米，求它的面积和周长。"))
    assert a.fingerprint != b.fingerprint
    assert a.numeric_signature != b.numeric_signature
    assert similarity(a.text, b.text) >= SIMILAR_THRESHOLD


def test_typo_is_similar():
    a = key(doc("在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长度为二，求三角形面积的最大值。"))
    b = key(doc("在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长为二，求三角形面积的最大值。"))
    assert similarity(a.text, b.text) >= SIMILAR_THRESHOLD
    assert a.numeric_signature == b.numeric_signature


def test_different_questions_are_not_similar():
    a = key(doc("在三角形 ABC 中，已知角 A 等于六十度，求三角形面积的最大值。"))
    b = key(doc("已知数列的前 n 项和为 Sn，且满足递推关系，求数列的通项公式。"))
    assert similarity(a.text, b.text) < 0.5


def test_short_text_skips_fuzzy_bands():
    short = key(doc("1+1=?"))
    assert len(short.text) < MIN_FUZZY_LENGTH
    assert band_hashes(short) == []


def test_similar_texts_share_a_band():
    a = key(doc("在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长度为二，求三角形面积的最大值。"))
    b = key(doc("在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长为二，求三角形面积的最大值。"))
    assert set(band_hashes(a)) & set(band_hashes(b))
    # 题型不同不互相召回
    c = key(doc("在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长度为二，求三角形面积的最大值。"), "single_choice")
    assert not set(band_hashes(a)) & set(band_hashes(c))


def test_diff_snippets():
    out = diff_snippets("长是12厘米", "长是15厘米")
    assert out and out[0]["existing"] == "2" and out[0]["incoming"] == "5"


def test_material_sub_questions_are_not_similar_by_shared_material():
    from app.services.question_dedup_core import match_score

    material = doc("阅读下面的材料，回答问题。某地区近十年的气温变化数据如下表所示，请据此分析。")
    a = key(doc("第一小题"), stimulus=material)
    b = key(doc("第二小题"), stimulus=material)
    assert not a.fuzzy  # 本体太短,只做精确比对
    long_a = key(doc("根据材料，说明该地区气温变化的总体趋势"), stimulus=material)
    long_b = key(doc("根据材料，分析导致该地区降水减少的主要原因"), stimulus=material)
    assert match_score(long_a.text, long_b.text) < SIMILAR_THRESHOLD
    same = key(doc("根据材料，说明该地区气温变化的总体趋势。"), stimulus=material)
    assert match_score(long_a.text, same.text) == 1.0


def test_same_question_under_different_materials_is_not_similar():
    """不同材料下问法相同的小题:不判重复、也不判相似。"""
    from app.services.question_dedup_core import match_score

    ask = doc("根据材料，概括该地区气候变化的主要趋势，并说明理由")
    m1 = doc("某地区近十年的气温变化数据如下表所示，年平均气温逐年上升，降水量明显减少。")
    m2 = doc("阅读下面关于某城市人口迁移的材料，近年来大量年轻人口流向沿海城市。")
    a, b = key(ask, stimulus=m1), key(ask, stimulus=m2)
    assert a.fingerprint != b.fingerprint
    assert match_score(a.text, b.text) < SIMILAR_THRESHOLD


def test_standalone_vs_material_sub_question_is_not_similar():
    from app.services.question_dedup_core import match_score

    ask = doc("根据材料，概括该地区气候变化的主要趋势，并说明理由")
    material = doc("某地区近十年的气温变化数据如下表所示，年平均气温逐年上升，降水量明显减少。")
    standalone, sub = key(ask), key(ask, stimulus=material)
    assert standalone.fingerprint != sub.fingerprint
    assert match_score(standalone.text, sub.text) == 0.0


def test_same_material_same_question_with_typo_is_similar():
    from app.services.question_dedup_core import match_score

    material = doc("某地区近十年的气温变化数据如下表所示，年平均气温逐年上升，降水量明显减少。")
    a = key(doc("根据材料，概括该地区气候变化的主要趋势，并说明理由"), stimulus=material)
    b = key(doc("根据材料，概括该地区气候变化的主要趋势，并说明原因"), stimulus=material)
    assert match_score(a.text, b.text) >= SIMILAR_THRESHOLD
