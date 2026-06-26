from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.answer_quality import detect_unreliable_answer


def test_clean_answer_is_reliable():
    answer = "The MPG transaction endpoint is POST /MPG/mpg_gateway with AES256."
    assert detect_unreliable_answer(answer) is None


@pytest.mark.parametrize(
    "answer",
    [
        "我目前無法回覆。",
        "It looks like your message was cut off and contains a partial quote "
        "from our previous conversation (\"...integrate NewebPay's\").",
        "Could you please clarify what you would like to know about the manual?",
        "I'm sorry, but I cannot answer that right now.",
        # zh-TW confusion replies NotebookLM emits when context looks truncated
        "看來您的訊息似乎被截斷了！不過沒關係，請問您想先探討哪一個部分？",
        "看來您似乎貼上了一段之前的對話或是被截斷的訊息！",
    ],
)
def test_refusal_and_confusion_answers_are_unreliable(answer):
    reason = detect_unreliable_answer(answer)
    assert reason is not None
    assert isinstance(reason, str) and reason


def test_detection_is_case_insensitive():
    assert detect_unreliable_answer("YOUR MESSAGE WAS CUT OFF") is not None


def test_blank_answer_is_unreliable():
    assert detect_unreliable_answer("   ") is not None
