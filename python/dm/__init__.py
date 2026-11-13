"""AI game master runtime. See docs/ai-game-master.md."""


def start():
    """Start observing the game and accepting story plans. Safe to repeat."""
    from dm import climate, feedback, magic_weather, observer, overlay, shelter, story, summer, trip, weather, weather_talk
    observer.start()
    story.start()
    overlay.start()
    feedback.start()
    trip.start_ticking()
    weather.start_ticking()
    climate.start()
    weather_talk.start()
    summer.start()
    magic_weather.start()
    shelter.start()
