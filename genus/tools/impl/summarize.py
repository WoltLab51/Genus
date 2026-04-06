"""
Summarize Tool

Returns a deterministic summary string of the input text.
"""


def summarize(text: str) -> str:
    """Return a deterministic summary of the text.

    Args:
        text: The text to summarize.

    Returns:
        A string in the format "summary: <text>".
    """
    return "summary: " + text
