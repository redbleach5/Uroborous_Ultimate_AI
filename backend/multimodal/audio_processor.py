"""
Audio processing - Transcription, analysis
"""

from typing import Dict, Any, Optional
from pathlib import Path
from ..core.logger import get_logger
logger = get_logger(__name__)

try:
    import whisper
    AUDIO_LIBS_AVAILABLE = True
except ImportError:
    AUDIO_LIBS_AVAILABLE = False
    logger.warning("Audio processing libraries not available")


class AudioProcessor:
    """Processor for audio transcription and analysis"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize audio processor
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.transcription_enabled = self.config.get("transcription", True)
        self.model_name = self.config.get("model", "base")
        self._model = None
    
    async def initialize(self) -> None:
        """Initialize Whisper model"""
        if not AUDIO_LIBS_AVAILABLE:
            return
        
        if self.transcription_enabled:
            try:
                self._model = whisper.load_model(self.model_name)
                logger.info(f"Loaded Whisper model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Failed to load Whisper model: {e}")
    
    async def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribe audio file
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Transcription results
        """
        if not AUDIO_LIBS_AVAILABLE:
            return {"success": False, "error": "Audio libraries not available"}
        
        if not self._model:
            await self.initialize()
        
        try:
            path = Path(audio_path)
            if not path.exists():
                return {"success": False, "error": f"Audio file not found: {audio_path}"}
            
            # Transcribe
            result = self._model.transcribe(str(path))
            
            return {
                "success": True,
                "text": result["text"],
                "language": result.get("language", "unknown"),
                "segments": [
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": seg["text"]
                    }
                    for seg in result.get("segments", [])
                ]
            }
            
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            return {"success": False, "error": str(e)}
    
    async def analyze_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Analyze audio file
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Analysis results
        """
        try:
            path = Path(audio_path)
            if not path.exists():
                return {"success": False, "error": f"Audio file not found: {audio_path}"}
            
            # Basic file info
            file_size = path.stat().st_size
            extension = path.suffix.lower()
            
            return {
                "success": True,
                "path": str(path),
                "size_mb": file_size / (1024 * 1024),
                "format": extension,
                "supported_formats": [".mp3", ".wav", ".m4a", ".flac", ".ogg"]
            }
            
        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
            return {"success": False, "error": str(e)}

