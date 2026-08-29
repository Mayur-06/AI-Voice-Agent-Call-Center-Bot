import uvicorn
from chromadb.server.fastapi import FastAPI
from chromadb.config import Settings

settings = Settings()
settings.chroma_server_host = "0.0.0.0"
settings.chroma_server_http_port = 8001
settings.chroma_server_headers = {}

app = FastAPI(settings).app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
