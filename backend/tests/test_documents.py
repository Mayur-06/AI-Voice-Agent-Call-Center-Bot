import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import io
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.routers.auth import get_current_user
from app.routers.documents import router as documents_router
from app.models.schemas import Document


class MockUser:
    id = "test-user-id"


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: MockUser()
    return TestClient(app)


@pytest.mark.asyncio
async def test_upload_document_success(client):
    mock_pdf_content = b"%PDF-1.4 fake pdf content"
    with patch("app.routers.documents.get_supabase") as mock_get_supabase, \
         patch("app.routers.documents.get_storage_admin") as mock_get_storage, \
         patch("app.routers.documents.PdfReader") as mock_pdf_reader, \
         patch("app.routers.documents.index_document_chunks", new_callable=AsyncMock):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "doc-1", "persona_id": "persona-1", "filename": "test.pdf", "chunks_count": 0, "created_at": "2024-01-01T00:00:00"}
        ]
        mock_supabase.table.return_value.update.return_value.execute.return_value.data = [
            {"id": "doc-1", "persona_id": "persona-1", "filename": "test.pdf", "chunks_count": 2, "created_at": "2024-01-01T00:00:00"}
        ]
        mock_get_supabase.return_value = mock_supabase

        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is test content for the document."
        mock_reader.pages = [mock_page, mock_page]
        mock_pdf_reader.return_value = mock_reader

        response = client.post(
            "/api/documents/upload?persona_id=persona-1",
            files={"file": ("test.pdf", mock_pdf_content, "application/pdf")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "doc-1"
    assert data["filename"] == "test.pdf"
    assert data["chunks_count"] >= 1


@pytest.mark.asyncio
async def test_upload_document_empty_file(client):
    with patch("app.routers.documents.get_supabase") as mock_get_supabase:
        mock_get_supabase.return_value = MagicMock()
        response = client.post(
            "/api/documents/upload?persona_id=persona-1",
            files={"file": ("test.pdf", b"", "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Empty file"


@pytest.mark.asyncio
async def test_upload_document_invalid_pdf(client):
    mock_pdf_content = b"not a pdf"
    with patch("app.routers.documents.get_supabase") as mock_get_supabase, \
         patch("app.routers.documents.get_storage_admin") as mock_get_storage, \
         patch("app.routers.documents.PdfReader") as mock_pdf_reader:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "doc-1", "persona_id": "persona-1", "filename": "bad.pdf", "chunks_count": 0}
        ]
        mock_get_supabase.return_value = mock_supabase
        mock_get_storage.return_value = MagicMock()

        mock_pdf_reader.side_effect = Exception("Invalid PDF")

        response = client.post(
            "/api/documents/upload?persona_id=persona-1",
            files={"file": ("bad.pdf", mock_pdf_content, "application/pdf")},
        )
    assert response.status_code == 400
    assert "Failed to extract text from PDF" in response.json()["detail"]
