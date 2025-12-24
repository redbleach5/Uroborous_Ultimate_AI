"""
Image processing - OCR, analysis, image-to-code
"""

from typing import Dict, Any, Optional
from pathlib import Path
from ..core.logger import get_logger
logger = get_logger(__name__)

try:
    from PIL import Image
    import pytesseract
    import cv2
    import numpy as np
    IMAGE_LIBS_AVAILABLE = True
except ImportError:
    IMAGE_LIBS_AVAILABLE = False
    logger.warning("Image processing libraries not available")


class ImageProcessor:
    """Processor for image analysis and OCR"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize image processor
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.ocr_enabled = self.config.get("ocr", True)
        self.max_size_mb = self.config.get("max_size_mb", 10)
    
    async def process_image(self, image_path: str) -> Dict[str, Any]:
        """
        Process an image
        
        Args:
            image_path: Path to image file
            
        Returns:
            Processing results
        """
        if not IMAGE_LIBS_AVAILABLE:
            return {"success": False, "error": "Image libraries not available"}
        
        try:
            path = Path(image_path)
            if not path.exists():
                return {"success": False, "error": f"Image not found: {image_path}"}
            
            # Check file size
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > self.max_size_mb:
                return {"success": False, "error": f"Image too large: {size_mb:.2f}MB > {self.max_size_mb}MB"}
            
            # Load image
            image = Image.open(path)
            
            result = {
                "success": True,
                "path": str(path),
                "size": image.size,
                "format": image.format,
                "mode": image.mode
            }
            
            # OCR if enabled
            if self.ocr_enabled:
                try:
                    text = pytesseract.image_to_string(image)
                    result["ocr_text"] = text
                    result["has_text"] = bool(text.strip())
                except Exception as e:
                    logger.warning(f"OCR failed: {e}")
                    result["ocr_error"] = str(e)
            
            # Basic analysis
            result["analysis"] = await self._analyze_image(image)
            
            return result
            
        except Exception as e:
            logger.error(f"Image processing error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _analyze_image(self, image: Image.Image) -> Dict[str, Any]:
        """Analyze image content"""
        analysis = {
            "width": image.width,
            "height": image.height,
            "aspect_ratio": image.width / image.height if image.height > 0 else 0,
            "is_grayscale": image.mode == "L",
            "has_alpha": image.mode in ("RGBA", "LA", "P")
        }
        
        # Convert to numpy for analysis
        try:
            img_array = np.array(image)
            
            # Basic statistics
            if len(img_array.shape) == 3:
                analysis["channels"] = img_array.shape[2]
                analysis["mean_brightness"] = float(np.mean(img_array))
            else:
                analysis["channels"] = 1
                analysis["mean_brightness"] = float(np.mean(img_array))
            
        except Exception as e:
            logger.warning(f"Image analysis error: {e}")
        
        return analysis
    
    async def extract_text_from_image(self, image_path: str) -> str:
        """
        Extract text from image using OCR
        
        Args:
            image_path: Path to image
            
        Returns:
            Extracted text
        """
        if not IMAGE_LIBS_AVAILABLE or not self.ocr_enabled:
            return ""
        
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return ""
    
    async def image_to_code_description(self, image_path: str, llm_provider=None) -> str:
        """
        Convert image to code description using LLM vision capabilities
        
        Args:
            image_path: Path to image
            llm_provider: LLM provider for vision models (should support vision API)
            
        Returns:
            Code description
        """
        if not IMAGE_LIBS_AVAILABLE:
            return ""
        
        # Try to use LLM vision API if available
        if llm_provider:
            try:
                # Check if provider supports vision models
                vision_models = self._get_vision_models(llm_provider)
                if vision_models:
                    # Encode image to base64
                    import base64
                    with open(image_path, "rb") as image_file:
                        image_data = base64.b64encode(image_file.read()).decode('utf-8')
                    
                    # Determine image format
                    image = Image.open(image_path)
                    image_format = image.format.lower() if image.format else "png"
                    mime_type = f"image/{image_format}"
                    
                    # Prepare vision message
                    from ..llm.base import LLMMessage
                    
                    # Use vision-capable model
                    vision_model = vision_models[0] if isinstance(vision_models, list) else vision_models
                    
                    system_prompt = """You are an expert at analyzing images and describing code, UI components, or technical diagrams. 
Analyze the provided image and describe what you see in detail, focusing on:
- Code structure, syntax, and logic (if code is visible)
- UI components and layout (if it's a screenshot)
- Diagrams, flowcharts, or technical drawings
- Any text or labels visible in the image

Provide a clear, detailed description that could be used to recreate or understand what's shown."""
                    
                    user_content = [
                        {
                            "type": "text",
                            "text": "Analyze this image and provide a detailed description of what you see, especially any code, UI elements, or technical content."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            }
                        }
                    ]
                    
                    # Use vision API with structured image content
                    # The provider will handle vision-capable models appropriately
                    # Image is encoded as base64 data URL in the message content
                    
                    messages = [
                        LLMMessage(role="system", content=system_prompt),
                        LLMMessage(role="user", content=str(user_content))
                    ]
                    
                    # Generate description using vision model
                    response = await llm_provider.generate(
                        messages=messages,
                        model=vision_model,
                        max_tokens=2000,
                        temperature=0.3
                    )
                    
                    if response and response.content:
                        logger.info(f"Generated code description from image using vision model: {vision_model}")
                        return response.content
                    else:
                        logger.warning("Vision API returned empty response, falling back to OCR")
                else:
                    logger.debug("No vision models available, falling back to OCR")
            except Exception as e:
                logger.warning(f"Vision API failed: {e}, falling back to OCR")
                # Fall through to OCR fallback
        
        # Fallback to OCR
        return await self.extract_text_from_image(image_path)
    
    def _get_vision_models(self, llm_provider) -> Optional[list]:
        """
        Get list of vision-capable models from provider
        
        Args:
            llm_provider: LLM provider instance
            
        Returns:
            List of vision model names, or None if not supported
        """
        if not llm_provider:
            return None
        
        provider_name = getattr(llm_provider, 'name', '').lower()
        
        # Vision-capable models by provider
        vision_models_map = {
            'openai': [
                'gpt-4-vision-preview',
                'gpt-4-turbo',
                'gpt-4o',
                'gpt-4o-mini'
            ],
            'anthropic': [
                'claude-3-opus-20240229',
                'claude-3-sonnet-20240229',
                'claude-3-haiku-20240307',
                'claude-3-5-sonnet-20241022',
                'claude-3-5-haiku-20241022'
            ],
            'ollama': [
                'llava',
                'bakllava',
                'llava:latest'
            ]
        }
        
        # Check if provider has vision models
        if provider_name in vision_models_map:
            available_models = vision_models_map[provider_name]
            # Filter to only models that are actually available
            try:
                all_models = llm_provider.list_models()
                if isinstance(all_models, list):
                    available_models = [m for m in available_models if m in all_models]
            except Exception:
                pass  # If we can't list models, use the default list
            
            return available_models if available_models else None
        
        return None

