"""AI game master runtime. See docs/ai-game-master.md."""


def start():
    """Start observing the game and accepting story plans. Safe to repeat."""
    from dm import observer, story
    observer.start()
    story.start()
