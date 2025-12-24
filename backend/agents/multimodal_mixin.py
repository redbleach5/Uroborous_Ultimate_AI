"""
Multimodal Mixin - Adds multimodal capabilities to agents
"""

from typing import Dict, Any, Optional
from ..core.logger import get_logger
logger = get_logger(__name__)

from ..multimodal import ImageProcessor, AudioProcessor, VideoProcessor
from ..core.exceptions import AgentException
from ..core.pydantic_utils import pydantic_to_dict


class MultimodalMixin:
    """Mixin for adding multimodal processing capabilities to agents"""
    
    def __init__(self):
        """Initialize multimodal processors"""
        self.image_processor: Optional[ImageProcessor] = None
        self.audio_processor: Optional[AudioProcessor] = None
        self.video_processor: Optional[VideoProcessor] = None
        self._multimodal_initialized = False
    
    async def initialize_multimodal(self, config: Optional[Dict[str, Any]] = None):
        """Initialize multimodal processors"""
        if self._multimodal_initialized:
            return
        
        try:
            from ..config import get_config
            if not config:
                cfg = get_config()
                if hasattr(cfg, "multimodal"):
                    config = pydantic_to_dict(cfg.multimodal)
                else:
                    config = {}
            
            if config.get("enabled", True):
                if config.get("image", {}).get("enabled", True):
                    self.image_processor = ImageProcessor(config.get("image", {}))
                
                if config.get("audio", {}).get("enabled", True):
                    self.audio_processor = AudioProcessor(config.get("audio", {}))
                    await self.audio_processor.initialize()
                
                if config.get("video", {}).get("enabled", True):
                    self.video_processor = VideoProcessor(config.get("video", {}))
            
            self._multimodal_initialized = True
            logger.info("Multimodal processors initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize multimodal processors: {e}")
    
    async def process_multimodal_input(
        self,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process multimodal input (images, audio, video)
        
        Args:
            input_data: Input data with file paths
            
        Returns:
            Processed content
        """
        if not self._multimodal_initialized:
            await self.initialize_multimodal()
        
        processed = {
            "text": "",
            "images": [],
            "audio": None,
            "video": None
        }
        
        # Process images
        if "image_paths" in input_data and self.image_processor:
            for image_path in input_data["image_paths"]:
                try:
                    result = await self.image_processor.process_image(image_path)
                    if result.get("success"):
                        ocr_text = result.get("ocr_text", "")
                        if ocr_text:
                            processed["text"] += f"\n\nImage {image_path}:\n{ocr_text}"
                        processed["images"].append(result)
                except Exception as e:
                    logger.warning(f"Failed to process image {image_path}: {e}")
        
        # Process audio
        if "audio_path" in input_data and self.audio_processor:
            try:
                result = await self.audio_processor.transcribe_audio(input_data["audio_path"])
                if result.get("success"):
                    processed["text"] += f"\n\nAudio transcription:\n{result.get('text', '')}"
                    processed["audio"] = result
            except Exception as e:
                logger.warning(f"Failed to process audio: {e}")
        
        # Process video
        if "video_path" in input_data and self.video_processor:
            try:
                result = await self.video_processor.process_video(input_data["video_path"])
                if result.get("success"):
                    processed["video"] = result
            except Exception as e:
                logger.warning(f"Failed to process video: {e}")
        
        return processed

