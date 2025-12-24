"""
Multimodal router - Image, audio, video processing
"""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import tempfile
import os

router = APIRouter()


class ProcessImageRequest(BaseModel):
    image_path: str


class ProcessAudioRequest(BaseModel):
    audio_path: str


class ProcessVideoRequest(BaseModel):
    video_path: str


@router.post("/multimodal/image/process")
async def process_image(request: Request, image_request: ProcessImageRequest):
    """Обработать изображение (OCR, анализ)"""
    engine = request.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Движок не инициализирован")
    
    try:
        from backend.multimodal import ImageProcessor
        from backend.config import get_config
        from backend.core.pydantic_utils import pydantic_to_dict
        
        config = get_config()
        image_config = pydantic_to_dict(config.multimodal.image) if hasattr(config.multimodal, "image") else {}
        processor = ImageProcessor(image_config)
        
        result = await processor.process_image(image_request.image_path)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multimodal/image/ocr")
async def extract_text_from_image(request: Request, image_request: ProcessImageRequest):
    """Извлечь текст из изображения с помощью OCR"""
    engine = request.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Движок не инициализирован")
    
    try:
        from backend.multimodal import ImageProcessor
        from backend.config import get_config
        from backend.core.pydantic_utils import pydantic_to_dict
        
        config = get_config()
        image_config = pydantic_to_dict(config.multimodal.image) if hasattr(config.multimodal, "image") else {}
        processor = ImageProcessor(image_config)
        
        text = await processor.extract_text_from_image(image_request.image_path)
        return {"text": text, "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multimodal/audio/transcribe")
async def transcribe_audio(request: Request, audio_request: ProcessAudioRequest):
    """Транскрибировать аудио файл"""
    engine = request.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Движок не инициализирован")
    
    try:
        from backend.multimodal import AudioProcessor
        from backend.config import get_config
        from backend.core.pydantic_utils import pydantic_to_dict
        
        config = get_config()
        audio_config = pydantic_to_dict(config.multimodal.audio) if hasattr(config.multimodal, "audio") else {}
        processor = AudioProcessor(audio_config)
        await processor.initialize()
        
        result = await processor.transcribe_audio(audio_request.audio_path)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multimodal/video/process")
async def process_video(request: Request, video_request: ProcessVideoRequest):
    """Обработать видео файл"""
    engine = request.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Движок не инициализирован")
    
    try:
        from backend.multimodal import VideoProcessor
        from backend.config import get_config
        from backend.core.pydantic_utils import pydantic_to_dict
        
        config = get_config()
        video_config = pydantic_to_dict(config.multimodal.video) if hasattr(config.multimodal, "video") else {}
        processor = VideoProcessor(video_config)
        
        result = await processor.process_video(video_request.video_path)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

