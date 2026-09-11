import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import pytest
from unittest.mock import patch, MagicMock
from httpx import Response
from app.services.stt import transcribe_audio


def _mock_response(status_code=200, json_data=None):
    content = json_module.dumps(json_data or {}).encode()
    response = Response(status_code, content=content)
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_transcribe_audio_success(mock_settings):
    mock_response = _mock_response(json_data={"text": "Hello world"})
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await transcribe_audio(b"fake-audio-bytes")
    assert result == "Hello world"


@pytest.mark.asyncio
async def test_transcribe_audio_empty_result(mock_settings):
    mock_response = _mock_response(json_data={"text": ""})
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await transcribe_audio(b"fake-audio-bytes")
    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_audio_api_error(mock_settings):
    mock_response = _mock_response(status_code=401, json_data={"error": "Unauthorized"})
    mock_response.raise_for_status.side_effect = Exception("HTTP error")
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(Exception):
            await transcribe_audio(b"fake-audio-bytes")


# --- Regression: Whisper hallucinating words out of silence ------------------


def test_whisper_stock_phrases_rejected_when_barely_any_voice():
    """The exact transcripts a real call produced from ~100ms of room tone.

    Each of these became a user turn, so the agent answered phantom input and
    ended up talking to itself.
    """
    from app.services.stt import is_hallucinated_silence

    for phantom in [
        " Thank you.", " So", " Oh", " .", " Okay.", " I'm sorry.",
        " I'm going to go.", " you", " Hmm", "", "   ",
    ]:
        assert is_hallucinated_silence(phantom, voiced_ms=100), phantom


def test_same_words_accepted_when_actually_spoken():
    """The filter must not swallow a caller who really said these."""
    from app.services.stt import is_hallucinated_silence

    for genuine in [" Thank you.", " Hello.", " Okay.", " Yeah."]:
        assert not is_hallucinated_silence(genuine, voiced_ms=700), genuine


def test_real_sentences_never_filtered():
    from app.services.stt import is_hallucinated_silence

    for text in [
        "Thank you for your help with the refund",
        "Hello, can I speak to support?",
        "So what are your business hours?",
        "yes", "no", "25", "my order number is 4471",
    ]:
        assert not is_hallucinated_silence(text, voiced_ms=300), text


def test_unknown_duration_gives_caller_benefit_of_the_doubt():
    """An explicit stop_listening has no VAD measurement; trust it."""
    from app.services.stt import is_hallucinated_silence

    assert not is_hallucinated_silence(" Thank you.", voiced_ms=None)
