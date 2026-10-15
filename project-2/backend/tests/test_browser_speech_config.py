from app.core.config import Settings
from app.services.speech import SpeechService

def test_browser_defaults_do_not_require_model_weights():
    s=Settings(_env_file=None)
    assert s.stt_provider=='browser' and s.stt_model=='web-speech'
    assert s.browser_stt_mode=='browser' and not s.browser_phrase_bias

def test_browser_mode_separate_from_backend_provider(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'stt_provider','faster_whisper')
    monkeypatch.setattr(settings,'browser_stt_mode','browser')
    monkeypatch.setattr(settings,'browser_phrase_bias',False)
    c=SpeechService().configuration()
    assert c['browser_mode']=='browser' and c['browser_provider']=='browser-web-speech'
    assert c['browser_phrase_bias'] is False
