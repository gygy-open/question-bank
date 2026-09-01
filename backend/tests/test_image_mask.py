"""图片 token 遮罩/还原(app.services.importing.image_mask)。"""

from app.services.importing.image_mask import mask_images, restore_images, unmask


def test_mask_images_no_op_without_images():
    masked, mapping = mask_images("普通文本，没有图片。")
    assert masked == "普通文本，没有图片。"
    assert mapping == {}


def test_mask_single_image_without_attrs():
    masked, mapping = mask_images("题干 ![](/static/media/t1/a.png) 结尾")
    assert masked == "题干 @@IMG0@@ 结尾"
    assert mapping == {"@@IMG0@@": "![](/static/media/t1/a.png)"}


def test_mask_image_with_same_line_attrs():
    original = '![](/static/media/t1/a.png){width="1.59in" height="1.18in"}'
    masked, mapping = mask_images(f"题干 {original} 结尾")
    assert masked == "题干 @@IMG0@@ 结尾"
    assert mapping == {"@@IMG0@@": original}


def test_mask_image_with_detached_next_line_attrs():
    original = '![](/static/media/t1/a.png)\n{width="2.54cm" height="25.4mm"}'
    masked, mapping = mask_images(f"题干\n{original}\n结尾")
    assert masked == "题干\n@@IMG0@@\n结尾"
    assert mapping == {"@@IMG0@@": original}


def test_mask_image_with_pandoc_hard_wrapped_alt_and_attrs():
    # pandoc 把过长的行硬换行:alt 文本和尺寸属性块里都夹着 \n(真实导入数据的形态)。
    original = (
        "![Question 8\n"
        'diagram](/static/media/t1/image2.png){width="5.833333333333333in"\n'
        'height="1.9444444444444444in"}'
    )
    masked, mapping = mask_images(f"题干\n\n{original}\n\n结尾")
    assert masked == "题干\n\n@@IMG0@@\n\n结尾"
    assert mapping == {"@@IMG0@@": original}


def test_mask_multiple_images_numbered_in_order():
    md = "![](/static/media/t1/a.png) 文字 ![](/static/media/t1/b.png)"
    masked, mapping = mask_images(md)
    assert masked == "@@IMG0@@ 文字 @@IMG1@@"
    assert mapping == {
        "@@IMG0@@": "![](/static/media/t1/a.png)",
        "@@IMG1@@": "![](/static/media/t1/b.png)",
    }


def test_unmask_restores_placeholders_in_nested_structures():
    mapping = {"@@IMG0@@": "![](/static/media/t1/a.png)", "@@IMG1@@": "![](/static/media/t1/b.png)"}
    value = {
        "content": "见图 @@IMG0@@",
        "options": ["A. @@IMG1@@", "B. 无图"],
        "answer": [["@@IMG0@@"], ["纯文本"]],
    }
    restored = unmask(value, mapping)
    assert restored == {
        "content": "见图 ![](/static/media/t1/a.png)",
        "options": ["A. ![](/static/media/t1/b.png)", "B. 无图"],
        "answer": [["![](/static/media/t1/a.png)"], ["纯文本"]],
    }


def test_unmask_leaves_unknown_placeholder_untouched():
    restored = unmask("见图 @@IMG9@@", {"@@IMG0@@": "![](/static/media/t1/a.png)"})
    assert restored == "见图 @@IMG9@@"


def test_unmask_empty_mapping_is_no_op():
    value = {"content": "@@IMG0@@", "options": ["x"]}
    assert unmask(value, {}) == value


def test_restore_images_strips_hallucinated_placeholder_with_no_image_left():
    # AI 幻觉出映射表里不存在的编号,且没有剩余图片可配(只遮罩了 1 张图却输出了 @@IMG1@@)。
    mapping = {"@@IMG0@@": "![](/static/media/t1/a.png)"}
    dumped = {"content": "见图 @@IMG0@@", "options": ["A. 正常", "B. 幻觉图 @@IMG1@@"]}

    restored, dropped, unresolved = restore_images(dumped, mapping)

    assert restored == {
        "content": "见图 ![](/static/media/t1/a.png)",
        "options": ["A. 正常", "B. 幻觉图 "],
    }
    assert dropped == 1
    assert unresolved == 0


def test_restore_images_recovers_wrong_number_by_position():
    # 复现实测 bug:文档有 2 张图,AI 把第 2 张的编号写错(写成了不存在的 @@IMG2@@),
    # 但第一张(@@IMG0@@)是对的。应该按出现顺序把剩下的 @@IMG2@@ 补配给唯一"从未被引用"的图(IMG1)。
    mapping = {
        "@@IMG0@@": "![](/static/media/t1/a.png)",
        "@@IMG1@@": "![](/static/media/t1/b.png){width=\"3in\"}",
    }
    dumped = [
        {"content": "第一题 @@IMG0@@"},
        {"content": "第二题，见图 @@IMG2@@"},
    ]

    restored, dropped, unresolved = restore_images(dumped, mapping)

    assert restored == [
        {"content": "第一题 ![](/static/media/t1/a.png)"},
        {"content": '第二题，见图 ![](/static/media/t1/b.png){width="3in"}'},
    ]
    assert dropped == 0
    assert unresolved == 0


def test_restore_images_reports_unresolved_when_image_never_referenced():
    # AI 完全没提到第二张图(既没权号对的,也没形状像占位符的残留),只能计入未解决计数。
    mapping = {
        "@@IMG0@@": "![](/static/media/t1/a.png)",
        "@@IMG1@@": "![](/static/media/t1/b.png)",
    }
    dumped = {"content": "只提到了一张图 @@IMG0@@"}

    restored, dropped, unresolved = restore_images(dumped, mapping)

    assert restored == {"content": "只提到了一张图 ![](/static/media/t1/a.png)"}
    assert dropped == 0
    assert unresolved == 1


def test_restore_images_strips_stray_placeholder_even_with_empty_mapping():
    # 文档没有任何图片(mapping 空),但 AI 被 prompt 诱导凭空写出占位符——必须清掉,不能落库。
    value = {"content": "凭空的 @@IMG0@@ 占位符"}
    restored, dropped, unresolved = restore_images(value, {})
    assert restored == {"content": "凭空的  占位符"}
    assert dropped == 1
    assert unresolved == 0


def test_restore_images_true_no_op_when_empty_mapping_and_no_placeholder():
    value = {"content": "完全没有图片也没有占位符"}
    restored, dropped, unresolved = restore_images(value, {})
    assert restored == value
    assert dropped == 0
    assert unresolved == 0
