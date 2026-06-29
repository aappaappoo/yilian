from core.conversation.runtime_session import _normalize_assistant_reply_text


def test_normalize_assistant_reply_removes_numbered_reference_heading():
    text = "\n".join([
        "厦门攻略：",
        "",
        "六、参考来源",
        "海滨之城，厦门旅游攻略",
    ])

    normalized = _normalize_assistant_reply_text(
        text,
        artifact={
            "tool": "web_search",
            "references": [
                {"title": "厦门文旅", "url": "https://example.com/xiamen"},
            ],
        },
    )

    assert "六、参考来源" not in normalized
    assert "海滨之城" not in normalized
    assert "参考链接" in normalized
    assert "https://example.com/xiamen" in normalized
