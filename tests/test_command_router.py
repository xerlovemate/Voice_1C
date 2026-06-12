from pathlib import Path

from voice_actions.command_router import CommandRouter


def test_command_match_tab():
    router = CommandRouter(Path("voice_actions/command_config.json"))
    result = router.match("таб")
    assert result.handled
    assert result.action == "tab"
