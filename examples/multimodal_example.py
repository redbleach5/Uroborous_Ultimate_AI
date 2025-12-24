"""
Example: Multimodal processing
"""

import asyncio
from backend.multimodal import ImageProcessor, AudioProcessor, VideoProcessor


async def main():
    """Example multimodal processing"""
    
    # Image processing
    print("=== Image Processing ===")
    image_processor = ImageProcessor({"ocr": True})
    
    # Process image (replace with actual image path)
    # result = await image_processor.process_image("path/to/image.png")
    # print(f"Image processing result: {result}")
    
    # Extract text from image
    # text = await image_processor.extract_text_from_image("path/to/image.png")
    # print(f"Extracted text: {text}")
    
    # Audio processing
    print("\n=== Audio Processing ===")
    audio_processor = AudioProcessor({"transcription": True, "model": "base"})
    await audio_processor.initialize()
    
    # Transcribe audio (replace with actual audio path)
    # result = await audio_processor.transcribe_audio("path/to/audio.mp3")
    # print(f"Transcription: {result.get('text', '')}")
    
    # Video processing
    print("\n=== Video Processing ===")
    video_processor = VideoProcessor({"extract_frames": True})
    
    # Process video (replace with actual video path)
    # result = await video_processor.process_video("path/to/video.mp4")
    # print(f"Video info: {result}")
    
    # Extract frames
    # result = await video_processor.extract_frames_to_images(
    #     "path/to/video.mp4",
    #     "output/frames",
    #     interval_seconds=5.0
    # )
    # print(f"Extracted {result.get('frames_saved', 0)} frames")


if __name__ == "__main__":
    asyncio.run(main())

