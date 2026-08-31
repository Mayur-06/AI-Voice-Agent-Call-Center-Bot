import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import pytest
from unittest.mock import patch, MagicMock
from httpx import Response
from app.services.rag import retrieve_context


def _mock_response(status_code=200, json_data=None):
    content = json_module.dumps(json_data or {}).encode()
    response = Response(status_code, content=content)
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_retrieve_context_success(mock_settings):
    mock_response = _mock_response(json_data={
        "ids": [["chunk1", "chunk2"]],
        "documents": [["doc1", "doc2"]],
    })
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await retrieve_context("query text", top_k=2)
    assert result == ["doc1", "doc2"]


@pytest.mark.asyncio
async def test_retrieve_context_chromadb_down(mock_settings):
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection refused")):
        result = await retrieve_context("query text")
    assert result == []
