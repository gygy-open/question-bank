import pytest
from pydantic import ValidationError

from app.models.question import QuestionType
from app.schemas.question import QuestionCreate


def test_string_options_are_parsed_into_label_content():
    q = QuestionCreate(
        content="题干",
        q_type=QuestionType.SINGLE_CHOICE,
        options=["A. 甲", "B. 乙"],
    )

    assert q.options == [
        {"label": "A", "content": "甲"},
        {"label": "B", "content": "乙"},
    ]


def test_unlabeled_string_options_get_generated_labels():
    q = QuestionCreate(
        content="题干",
        q_type=QuestionType.SINGLE_CHOICE,
        options=["第一项", "第二项"],
    )

    assert [o["label"] for o in q.options] == ["A", "B"]


def test_fill_in_blank_accepts_valid_json_answer():
    q = QuestionCreate(
        content="___ 是首都",
        q_type=QuestionType.FILL_IN_THE_BLANK,
        answer='[["北京"]]',
    )

    assert q.answer == '[["北京"]]'


def test_fill_in_blank_rejects_non_json_answer():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content="___ 是首都",
            q_type=QuestionType.FILL_IN_THE_BLANK,
            answer="北京",
        )


def test_fill_in_blank_rejects_json_that_is_not_a_list():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content="___ 是首都",
            q_type=QuestionType.FILL_IN_THE_BLANK,
            answer='{"a": 1}',
        )
