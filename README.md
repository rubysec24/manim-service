# Manim Video Service

Educational video generation service using Manim for mathematical animations.

## Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/deploy)

## Features

- Generate educational math videos
- Support for equations, geometry, graphs, and physics animations
- RESTful API with FastAPI
- Async video rendering
- CORS support for web applications

## API Endpoints

- `GET /health` - Health check
- `POST /api/video/create` - Create new video
- `GET /api/video/status/{job_id}` - Check video status
- `GET /api/video/download/{job_id}` - Download video
- `GET /api/video/stream/{job_id}` - Stream video
- `DELETE /api/video/{job_id}` - Delete video

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Environment Variables

- `PORT` - Server port (default: 8001)

## License

MIT