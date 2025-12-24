"""
Video processing - Frame extraction, analysis
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from ..core.logger import get_logger
logger = get_logger(__name__)

try:
    import cv2
    VIDEO_LIBS_AVAILABLE = True
except ImportError:
    VIDEO_LIBS_AVAILABLE = False
    logger.warning("Video processing libraries not available")


class VideoProcessor:
    """Processor for video analysis and frame extraction"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize video processor
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.max_duration_seconds = self.config.get("max_duration_seconds", 300)
        self.extract_frames = self.config.get("extract_frames", True)
    
    async def process_video(self, video_path: str) -> Dict[str, Any]:
        """
        Process a video file
        
        Args:
            video_path: Path to video file
            
        Returns:
            Processing results
        """
        if not VIDEO_LIBS_AVAILABLE:
            return {"success": False, "error": "Video libraries not available"}
        
        try:
            path = Path(video_path)
            if not path.exists():
                return {"success": False, "error": f"Video file not found: {video_path}"}
            
            # Open video
            cap = cv2.VideoCapture(str(path))
            
            if not cap.isOpened():
                return {"success": False, "error": "Failed to open video file"}
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            # Check duration
            if duration > self.max_duration_seconds:
                cap.release()
                return {
                    "success": False,
                    "error": f"Video too long: {duration:.1f}s > {self.max_duration_seconds}s"
                }
            
            result = {
                "success": True,
                "path": str(path),
                "fps": fps,
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "duration_seconds": duration
            }
            
            # Extract frames if enabled
            if self.extract_frames:
                frames = await self._extract_key_frames(cap, fps)
                result["key_frames"] = frames
            
            cap.release()
            return result
            
        except Exception as e:
            logger.error(f"Video processing error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_key_frames(
        self,
        cap: cv2.VideoCapture,
        fps: float,
        interval_seconds: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        Extract key frames from video
        
        Args:
            cap: Video capture object
            fps: Frames per second
            interval_seconds: Interval between frames
            
        Returns:
            List of frame information
        """
        frames = []
        frame_interval = int(fps * interval_seconds)
        frame_number = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_number % frame_interval == 0:
                # Process and store frame with actual image data
                import base64
                import io
                from PIL import Image
                
                # Convert frame to PIL Image
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                
                # Convert to base64 for storage
                buffer = io.BytesIO()
                pil_image.save(buffer, format='JPEG', quality=85)
                frame_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                frames.append({
                    "frame_number": frame_number,
                    "timestamp": frame_number / fps if fps > 0 else 0,
                    "shape": frame.shape,
                    "image_base64": frame_base64,
                    "format": "jpeg"
                })
            
            frame_number += 1
        
        return frames
    
    async def extract_frames_to_images(
        self,
        video_path: str,
        output_dir: str,
        interval_seconds: float = 5.0
    ) -> Dict[str, Any]:
        """
        Extract frames from video and save as images
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frames
            interval_seconds: Interval between frames
            
        Returns:
            Extraction results
        """
        if not VIDEO_LIBS_AVAILABLE:
            return {"success": False, "error": "Video libraries not available"}
        
        try:
            path = Path(video_path)
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                return {"success": False, "error": "Failed to open video"}
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_interval = int(fps * interval_seconds)
            frame_number = 0
            saved_frames = []
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if frame_number % frame_interval == 0:
                    frame_path = output_path / f"frame_{frame_number:06d}.jpg"
                    cv2.imwrite(str(frame_path), frame)
                    saved_frames.append(str(frame_path))
                
                frame_number += 1
            
            cap.release()
            
            return {
                "success": True,
                "frames_saved": len(saved_frames),
                "output_dir": str(output_path),
                "frame_paths": saved_frames
            }
            
        except Exception as e:
            logger.error(f"Frame extraction error: {e}")
            return {"success": False, "error": str(e)}

