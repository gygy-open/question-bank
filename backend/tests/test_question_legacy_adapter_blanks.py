from app.services.question_content import collect_blank_ids
from app.services.question_legacy_adapter import adapt_legacy_question


def test_fill_blank_stem_gets_blank_nodes_matching_answer():
    v2 = adapt_legacy_question(
        q_type="fill_in_the_blank",
        content="甲\\_\\_\\_\\_乙\\_\\_\\_\\_",
        answer=[["x"], ["y"]],
    )
    assert collect_blank_ids(v2["content"]) == ["blk_1", "blk_2"]
    assert [b["id"] for b in v2["answer"]["blanks"]] == ["blk_1", "blk_2"]


def test_mismatched_blank_count_falls_back_to_underscore_text():
    v2 = adapt_legacy_question(
        q_type="fill_in_the_blank",
        content="甲\\_\\_\\_\\_乙\\_\\_\\_\\_",
        answer=[["x"]],
    )
    assert collect_blank_ids(v2["content"]) == []


def test_non_fill_questions_keep_underscores_as_text():
    v2 = adapt_legacy_question(q_type="free_response", content="甲\\_\\_\\_\\_乙", answer="x")
    assert collect_blank_ids(v2["content"]) == []
