"""AI game master runtime. See docs/ai-game-master.md."""


def start():
    """Start observing the game and accepting story plans. Safe to repeat."""
    from dm import feedback, observer, overlay, story
    observer.start()
    story.start()
    overlay.start()
    feedback.start()
