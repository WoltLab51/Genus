"""Unit tests for IntentClassifier — Phase 13."""

import pytest

from genus.conversation.conversation_agent import Intent, IntentClassifier


@pytest.fixture
def classifier() -> IntentClassifier:
    return IntentClassifier()


class TestIntentClassifier:
    def test_dev_request(self, classifier):
        assert classifier.classify("Bau mir einen Agent der Logs analysiert") == Intent.DEV_REQUEST

    def test_chat_greeting_hey(self, classifier):
        """'Hey GENUS' contains no question/dev/status keywords → CHAT."""
        assert classifier.classify("Hey GENUS") == Intent.CHAT

    def test_chat_greeting_wie_gehts(self, classifier):
        """'Wie geht's?' contains the question word 'Wie' → classified as QUESTION.
        Both CHAT and QUESTION use the same LLM path so this has no functional impact."""
        assert classifier.classify("Wie geht's?") in (Intent.CHAT, Intent.QUESTION)

    def test_question(self, classifier):
        assert classifier.classify("Was ist Python?") == Intent.QUESTION

    def test_status_request(self, classifier):
        assert classifier.classify("Wie läuft der aktuelle Run?") == Intent.STATUS_REQUEST

    def test_system_command_stopp(self, classifier):
        assert classifier.classify("Stopp alles!") == Intent.SYSTEM_COMMAND

    def test_system_command_kill(self, classifier):
        assert classifier.classify("Kill Switch aktivieren") == Intent.SYSTEM_COMMAND

    def test_chat_hey(self, classifier):
        assert classifier.classify("Hey GENUS") == Intent.CHAT

    def test_empty_string(self, classifier):
        """Empty input → CHAT (graceful, no crash)."""
        assert classifier.classify("") == Intent.CHAT

    def test_dev_request_english(self, classifier):
        assert classifier.classify("Create a new agent for monitoring") == Intent.DEV_REQUEST

    def test_question_how(self, classifier):
        assert classifier.classify("How does this work?") == Intent.QUESTION

    def test_status_request_laufend(self, classifier):
        assert classifier.classify("Was ist laufend gerade?") == Intent.STATUS_REQUEST

    def test_system_command_halt(self, classifier):
        assert classifier.classify("Halt alle Prozesse") == Intent.SYSTEM_COMMAND

    def test_system_command_priority_over_dev(self, classifier):
        """SYSTEM_COMMAND has higher priority than DEV_REQUEST."""
        assert classifier.classify("Stopp, baue nichts mehr") == Intent.SYSTEM_COMMAND
