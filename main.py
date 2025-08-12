from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Literal
import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime
import subprocess
import shutil
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://localhost:3000", 
        "http://localhost:3001",
        "https://kurmai-1-ekld2utol-enes-kurmaycomts-projects.vercel.app",
        "https://*.vercel.app",  # Tüm Vercel preview deployments
        "*"  # Development için - production'da kaldırın
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    grade: int
    course: str
    topic: str
    videoType: Literal['explanation', 'problem-solving', 'concept']
    duration: Literal['5-10sec', '10-15sec', '15-20sec']
    prompt: str
    style: Literal['minimal', 'colorful', 'professional']
    manimCode: Optional[str] = None

class CreateVideoRequest(BaseModel):
    script: str
    title: str = "solution"
    quality: str = "medium_quality"
    format: str = "mp4"

class VideoJob:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = "pending"
        self.progress = 0
        self.video_path = None
        self.error = None
        self.created_at = datetime.now()

jobs = {}

TEMP_DIR = Path(tempfile.gettempdir()) / "manim_videos"
TEMP_DIR.mkdir(exist_ok=True)

def sanitize_code(code: str) -> str:
    """Sanitize Manim code for security"""
    forbidden_imports = ['os', 'sys', 'subprocess', 'eval', 'exec', '__import__']
    forbidden_keywords = ['open(', 'file(', 'input(', 'raw_input(']
    
    for forbidden in forbidden_imports:
        if f"import {forbidden}" in code or f"from {forbidden}" in code:
            raise ValueError(f"Forbidden import: {forbidden}")
    
    for keyword in forbidden_keywords:
        if keyword in code:
            raise ValueError(f"Forbidden keyword: {keyword}")
    
    return code

def get_base_manim_template(style: str, video_type: str) -> str:
    """Get base Manim template based on style and type"""
    
    color_scheme = {
        'minimal': {'bg': '#FFFFFF', 'primary': '#000000', 'secondary': '#666666'},
        'colorful': {'bg': '#1e1e2e', 'primary': '#f38ba8', 'secondary': '#89b4fa'},
        'professional': {'bg': '#f8f9fa', 'primary': '#212529', 'secondary': '#495057'}
    }
    
    colors = color_scheme.get(style, color_scheme['minimal'])
    
    template = f"""from manim import *

class EducationalVideo(Scene):
    def construct(self):
        # Set background color
        self.camera.background_color = "{colors['bg']}"
        
        # Title
        title = Text("{{title}}", font_size=48, color="{colors['primary']}")
        subtitle = Text("{{subtitle}}", font_size=24, color="{colors['secondary']}")
        
        title.to_edge(UP, buff=1)
        subtitle.next_to(title, DOWN, buff=0.5)
        
        self.play(Write(title))
        self.play(FadeIn(subtitle))
        self.wait(2)
        
        # Main content will be inserted here
        {{content}}
        
        # End screen
        thanks = Text("Ders Sonu", font_size=36, color="{colors['primary']}")
        self.play(FadeOut(title), FadeOut(subtitle))
        self.play(Write(thanks))
        self.wait(2)
"""
    return template

async def render_video(job_id: str, code: str, output_quality: str = "medium"):
    """Render Manim video asynchronously"""
    job = jobs[job_id]
    
    try:
        job.status = "rendering"
        job.progress = 10
        
        # Sanitize code
        safe_code = sanitize_code(code)
        job.progress = 20
        
        # Create temporary Python file
        temp_py = TEMP_DIR / f"{job_id}.py"
        temp_py.write_text(safe_code, encoding='utf-8')
        job.progress = 30
        
        # Manim render command
        quality_map = {
            "low": "-ql",
            "medium": "-qm", 
            "high": "-qh"
        }
        
        quality_flag = quality_map.get(output_quality, "-qm")
        
        # Add PATH for manim
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/Users/ruby/Library/Python/3.9/bin:" + env.get("PATH", "")
        
        cmd = [
            "python3", "-m", "manim", 
            quality_flag,
            "--disable_caching",
            "--format", "mp4",
            str(temp_py),
            "EducationalVideo"
        ]
        
        job.progress = 40
        
        # Execute Manim with timeout
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(TEMP_DIR),
            env=env
        )
        
        # Wait for completion with timeout (5 minutes)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=300
            )
            job.progress = 80
            
            if process.returncode != 0:
                raise Exception(f"Manim render failed: {stderr.decode()}")
            
            # Find output video - try multiple possible locations
            possible_dirs = [
                TEMP_DIR / "media" / "videos" / job_id / "480p15",
                TEMP_DIR / "media" / "videos" / job_id / "720p30",
                TEMP_DIR / "media" / "videos" / job_id / "1080p60",
                TEMP_DIR / "media" / "videos" / f"{job_id[0:8]}" / "480p15",  # Sometimes uses short ID
            ]
            
            video_files = []
            for media_dir in possible_dirs:
                if media_dir.exists():
                    video_files = list(media_dir.glob("*.mp4"))
                    if video_files:
                        logger.info(f"Found video in {media_dir}")
                        break
            
            if not video_files:
                # Log the actual structure for debugging
                logger.error(f"No video found. Checking structure of {TEMP_DIR / 'media'}")
                if (TEMP_DIR / "media").exists():
                    for p in (TEMP_DIR / "media").rglob("*.mp4"):
                        logger.info(f"Found mp4 at: {p}")
                raise Exception("No video file generated")
            
            video_path = video_files[0]
            
            # Move to permanent location
            final_path = TEMP_DIR / f"{job_id}_final.mp4"
            shutil.move(str(video_path), str(final_path))
            
            job.video_path = str(final_path)
            job.progress = 100
            job.status = "completed"
            
        except asyncio.TimeoutError:
            job.status = "failed"
            job.error = "Rendering timeout (5 minutes exceeded)"
            
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        logger.error(f"Render error for job {job_id}: {e}")
    
    finally:
        # Cleanup temporary files
        if temp_py.exists():
            temp_py.unlink()
        
        # Clean up Manim media folder
        media_folder = TEMP_DIR / "media"
        if media_folder.exists():
            shutil.rmtree(media_folder, ignore_errors=True)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "manim-video-generator", "version": "1.0.0"}

@app.post("/api/video/create")
async def create_video(request: VideoRequest, background_tasks: BackgroundTasks):
    """Create a new video rendering job"""
    job_id = str(uuid.uuid4())
    job = VideoJob(job_id)
    jobs[job_id] = job
    
    # Use provided Manim code or generate from template
    if request.manimCode:
        manim_code = request.manimCode
    else:
        # Generate basic template (in production, this would use AI)
        template = get_base_manim_template(request.style, request.videoType)
        manim_code = template.format(
            title=request.topic,
            subtitle=f"{request.grade}. Sınıf - {request.course}",
            content="""
        # Example content
        equation = MathTex(r"a^2 + b^2 = c^2", font_size=48)
        self.play(Write(equation))
        self.wait(3)
            """
        )
    
    # Start background rendering
    background_tasks.add_task(render_video, job_id, manim_code)
    
    return {"job_id": job_id, "status": "started"}

@app.get("/api/video/status/{job_id}")
async def get_video_status(job_id: str):
    """Get video rendering job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error
    }

@app.get("/api/video/download/{job_id}")
async def download_video(job_id: str):
    """Download completed video"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Video not ready")
    
    if not job.video_path or not Path(job.video_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        job.video_path,
        media_type="video/mp4",
        filename=f"educational_video_{job_id}.mp4"
    )

@app.get("/videos/{job_id}")
async def get_video(job_id: str):
    """Get video file"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job.status == "processing":
        return {"status": "processing", "message": "Video is still being generated"}
    
    if job.status == "failed":
        raise HTTPException(status_code=500, detail=f"Video generation failed: {job.error}")
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Video not ready")
    
    if not job.video_path or not Path(job.video_path).exists():
        # Log available files for debugging
        logger.error(f"Video path not found: {job.video_path}")
        if TEMP_DIR.exists():
            mp4_files = list(TEMP_DIR.rglob("*.mp4"))
            logger.info(f"Available MP4 files: {mp4_files}")
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        job.video_path,
        media_type="video/mp4",
        filename=f"solution_video_{job_id}.mp4"
    )

@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    return {
        "job_id": job_id,
        "status": job.status,
        "progress": job.progress,
        "video_path": job.video_path,
        "error": job.error,
        "created_at": job.created_at.isoformat()
    }

@app.get("/api/video/stream/{job_id}")
async def stream_video(job_id: str):
    """Stream video for preview"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Video not ready")
    
    if not job.video_path or not Path(job.video_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    
    def iterfile():
        with open(job.video_path, "rb") as f:
            yield from f
    
    return StreamingResponse(iterfile(), media_type="video/mp4")

@app.delete("/api/video/{job_id}")
async def delete_video(job_id: str):
    """Delete video and clean up"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    # Delete video file if exists
    if job.video_path and Path(job.video_path).exists():
        Path(job.video_path).unlink()
    
    # Remove from jobs
    del jobs[job_id]
    
    return {"message": "Video deleted successfully"}

@app.post("/create-video")
async def create_video(request: CreateVideoRequest, background_tasks: BackgroundTasks):
    """Create a Manim video from a Python script"""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        job = VideoJob(job_id)
        jobs[job_id] = job
        
        # Create temp file for the script
        script_path = TEMP_DIR / f"{request.title}_{job_id}.py"
        with open(script_path, 'w') as f:
            f.write(request.script)
        
        # Run Manim in background
        background_tasks.add_task(generate_manim_video, job, script_path, request.quality, request.format, job_id)
        
        return {
            "job_id": job_id,
            "status": "processing",
            "video_url": f"/videos/{job_id}",
            "message": "Video generation started"
        }
        
    except Exception as e:
        logger.error(f"Error creating video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def generate_manim_video(job: VideoJob, script_path: Path, quality: str, format: str, job_id: str):
    """Generate Manim video in background"""
    try:
        job.status = "processing"
        
        # Map quality to Manim quality flags
        quality_map = {
            "low_quality": "-ql",
            "medium_quality": "-qm",
            "high_quality": "-qh",
            "production_quality": "-qp"
        }
        quality_flag = quality_map.get(quality, "-qm")
        
        # Run Manim - use full path
        manim_path = "/Users/ruby/Library/Python/3.9/bin/manim"
        if not Path(manim_path).exists():
            # Try alternative path
            manim_path = "manim"
        
        cmd = [
            manim_path, 
            quality_flag,
            f"--format={format}",
            "--disable_caching",
            str(script_path),
            "SolutionVideo"  # Class name in the script
        ]
        
        logger.info(f"Running Manim command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(TEMP_DIR))
        
        if result.returncode != 0:
            logger.error(f"Manim stderr: {result.stderr}")
            raise Exception(f"Manim error: {result.stderr}")
        
        # Find the generated video
        video_pattern = f"**/SolutionVideo.{format}"
        video_files = list(TEMP_DIR.rglob(video_pattern))
        
        if not video_files:
            # Try alternative patterns
            video_files = list(TEMP_DIR.rglob(f"**/*.{format}"))
        
        if video_files:
            job.video_path = str(video_files[0])
            job.status = "completed"
            job.progress = 100
            logger.info(f"Video generated successfully: {job.video_path}")
        else:
            raise Exception("Video file not found after generation")
            
    except Exception as e:
        logger.error(f"Error generating video: {e}")
        job.status = "failed"
        job.error = str(e)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if Manim is installed - use full path
        manim_path = "/Users/ruby/Library/Python/3.9/bin/manim"
        if Path(manim_path).exists():
            result = subprocess.run([manim_path, "--version"], capture_output=True, text=True)
        else:
            result = subprocess.run(["manim", "--version"], capture_output=True, text=True)
        manim_installed = result.returncode == 0
        manim_version = result.stdout.strip() if manim_installed else "Not installed"
    except Exception as e:
        manim_installed = False
        manim_version = "Not installed"
    
    return {
        "status": "healthy" if manim_installed else "degraded",
        "manim_installed": manim_installed,
        "manim_version": manim_version,
        "temp_dir": str(TEMP_DIR),
        "active_jobs": len(jobs)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)