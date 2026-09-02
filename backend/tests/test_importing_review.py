from app.models.question import QuestionStatus
from app.services.importing.review import extracted_to_v2_review


def test_review_strips_numbering_and_maps_tags():
    items = extracted_to_v2_review(
        [
            {
                "content": "1. 计算 **1 + 1**。",
                "q_type": "free_response",
                "answer": "答案是 $2$。",
                "difficulty": 2,
                "year": "2023",
                "tags": ["期末"],
            }
        ],
        subject_id=7,
    )

    assert len(items) == 1
    item = items[0]
    # 行首题号被去掉，题干转成 v2 RichDoc。
    assert item["content"]["type"] == "doc"
    plain = item["content"]["content"][0]["content"][0]["text"]
    assert plain.startswith("计算")
    assert item["answer"]["kind"] == "free_response"
    assert item["difficulty"] == 2
    assert item["subject_id"] == 7
    assert item["ai_suggested_tags"]["year"] == ["2023"]
    assert item["ai_suggested_tags"]["ai_extracted"] == ["期末"]
    assert item["warnings"] == []


def test_review_degrades_unparseable_answer_and_skips_empty_content():
    items = extracted_to_v2_review(
        [
            {
                "content": "无法确定答案的选择题",
                "q_type": "single_choice",
                "options": ["A. 甲", "B. 乙"],
                "answer": "见解析",
            },
            {"content": "", "q_type": "free_response", "answer": "空题干"},
        ],
        default_status=QuestionStatus.PENDING,
    )

    # 空题干被跳过；答案无法解析的题保留内容、答案降级为 None 并附 warning。
    assert len(items) == 1
    item = items[0]
    assert item["content"]["type"] == "doc"
    assert item["options"] is not None
    assert item["answer"] is None
    assert item["warnings"]
    # 无答案 → 状态从 pending 降级为 draft。
    assert item["status"] == "draft"
