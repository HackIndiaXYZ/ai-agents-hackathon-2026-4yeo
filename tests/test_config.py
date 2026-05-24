from app.core.config import get_settings


def test_settings_load_from_yaml():
    settings = get_settings()

    assert settings.app.name == "Argus Awaaz QA"
    assert settings.app.api_prefix == "/api"
    assert "Hinglish" in settings.workflow.supported_languages
    assert "missed_escalation" in settings.workflow.violation_labels
