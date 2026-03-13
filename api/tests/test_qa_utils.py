from app.services.qa.utils import detect_language_hint, normalize_question_items, to_anki_qa


def test_detect_language_hint_ru_en_and_mixed():
    assert detect_language_hint("Neural network and optimization") == "en"
    assert detect_language_hint("Нейронные сети и оптимизация") == "ru"
    assert detect_language_hint("Neural сети") == "mixed"


def test_to_anki_qa_tf_keeps_english_without_russian_prefix():
    item = {"type": "tf", "question": "The loss decreases after normalization?", "answer": "true", "tags": ["tf"]}
    out = to_anki_qa(item)
    assert out["type"] == "open"
    assert out["question"] == "The loss decreases after normalization?"
    assert out["answer"] == "True"


def test_to_anki_qa_tf_uses_russian_labels_for_cyrillic_question():
    item = {"type": "tf", "question": "Переобучение ухудшает обобщение?", "answer": "false", "tags": ["tf"]}
    out = to_anki_qa(item)
    assert out["type"] == "open"
    assert out["answer"] == "Неверно"


def test_normalize_question_items_filters_structural_questions():
    items = [
        {"type": "open", "question": "Что говорится об этом в 8 главе?", "answer": "..."},  # should be dropped
        {"type": "open", "question": "What does chapter 4 say about this?", "answer": "..."},
        {"type": "open", "question": "What is gradient descent?", "answer": "Optimization algorithm"},
    ]
    out = normalize_question_items(items, "medium")
    questions = [x["question"] for x in out]
    assert questions == ["What is gradient descent?"]
