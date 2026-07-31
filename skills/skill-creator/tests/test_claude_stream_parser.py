"""unittest suite for scripts.runners.claude_code stream parsing.

Feed synthetic `claude -p --output-format stream-json` lines into
ClaudeStreamTriggerParser and assert the settled decisions. No subprocess or
network involved.
"""

import json
import unittest

from scripts.runners.claude_code import ClaudeStreamTriggerParser

CLEAN_NAME = "my-skill-skill-abc12345"


def stream_event(se_type: str, **extra) -> str:
    ev = {"type": se_type, **extra}
    return json.dumps({"type": "stream_event", "event": ev})


def tool_use_start(tool_name: str) -> str:
    return stream_event("content_block_start", content_block={"type": "tool_use", "name": tool_name})


def input_delta(partial: str) -> str:
    return stream_event(
        "content_block_delta",
        delta={"type": "input_json_delta", "partial_json": partial},
    )


class ClaudeStreamParserTest(unittest.TestCase):
    def test_non_skill_tool_returns_false(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        d = p.feed(tool_use_start("Bash"))
        self.assertIsNotNone(d)
        self.assertTrue(d.settled)
        self.assertFalse(d.triggered)

    def test_skill_tool_with_matching_name_returns_true(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        self.assertIsNone(p.feed(tool_use_start("Skill")))
        self.assertIsNone(p.feed(input_delta('{"skill": "')))
        d = p.feed(input_delta(CLEAN_NAME))
        self.assertIsNotNone(d)
        self.assertTrue(d.triggered)

    def test_read_tool_with_matching_path_returns_true(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        self.assertIsNone(p.feed(tool_use_start("Read")))
        self.assertIsNone(p.feed(input_delta('{"file_path": "skills/')))
        d = p.feed(input_delta(CLEAN_NAME))
        self.assertTrue(d.settled)
        self.assertTrue(d.triggered)

    def test_skill_tool_without_name_in_input_returns_false_on_stop(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        self.assertIsNone(p.feed(tool_use_start("Skill")))
        self.assertIsNone(p.feed(input_delta('{"skill": "other"}')))
        d = p.feed(stream_event("content_block_stop"))
        self.assertTrue(d.settled)
        self.assertFalse(d.triggered)

    def test_message_stop_without_pending_tool_returns_false(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        d = p.feed(stream_event("message_stop"))
        self.assertTrue(d.settled)
        self.assertFalse(d.triggered)

    def test_result_event_returns_current_state(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        d = p.feed(json.dumps({"type": "result", "subtype": "success"}))
        self.assertTrue(d.settled)
        self.assertFalse(d.triggered)

    def test_assistant_message_tool_use_true(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "name": "Skill",
                    "input": {"skill": CLEAN_NAME},
                }],
            },
        })
        d = p.feed(line)
        self.assertTrue(d.settled)
        self.assertTrue(d.triggered)

    def test_assistant_message_unrelated_tool_returns_false(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
            },
        })
        d = p.feed(line)
        self.assertTrue(d.settled)
        self.assertFalse(d.triggered)

    def test_garbage_lines_ignored(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        self.assertIsNone(p.feed(""))
        self.assertIsNone(p.feed("not json"))
        self.assertIsNone(p.feed('{"type": "unknown"}'))
        self.assertIsNone(p.feed(tool_use_start("Skill")))
        self.assertIsNone(p.feed('{"type": "stream_event", "event": {"type": "text_delta"}}'))

    def test_non_skill_tool_false_settles_even_with_later_matches(self):
        p = ClaudeStreamTriggerParser(CLEAN_NAME)
        d = p.feed(tool_use_start("Bash"))
        self.assertTrue(d.settled)
        self.assertFalse(d.triggered)
        # a later feed is still processed but the decision is already made
        d2 = p.feed(tool_use_start("Skill"))
        self.assertIsNone(d2)


if __name__ == "__main__":
    unittest.main()
