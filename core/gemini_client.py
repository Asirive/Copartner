import os
import logging
from typing import List, Union, Generator, Dict, Any
from google import genai
from google.genai import types

logger = logging.getLogger("Copartner.GeminiClient")

class GeminiClient:
    """
    A robust, premium client wrapper around the official google-genai SDK.
    Serves as the primary brain interface for Asirive Copartner.
    Supports text generation, streaming, embeddings, and token counting.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("GEMINI_API_KEY is missing from environment")
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set it in your environment or .env file."
            )
        
        # Initialize the official Google GenAI Client
        self.client = genai.Client(api_key=self.api_key)
        
        # Model definitions (aligned with Build with Gemini XPRIZE)
        self.models = {
            "pro": "gemini-2.5-pro",
            "flash": "gemini-2.5-flash",
            "embedding": "text-embedding-004"
        }
        logger.info("GeminiClient initialized successfully with GenAI SDK.")

    def generate_content(
        self,
        contents: Union[str, List[Any]],
        system_instruction: str = None,
        use_pro: bool = True,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        json_mode: bool = False
    ) -> str:
        """
        Generates standard content block synchronously.
        Routes to Gemini 2.5 Pro by default, or Flash if specified.
        """
        model = self.models["pro"] if use_pro else self.models["flash"]
        logger.debug(f"Generating content using {model}")
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
            response_mime_type="application/json" if json_mode else "text/plain"
        )
        
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            return response.text
        except Exception as e:
            logger.error(f"Error during generate_content with {model}: {e}")
            raise e

    def generate_stream(
        self,
        contents: Union[str, List[Any]],
        system_instruction: str = None,
        use_pro: bool = True,
        temperature: float = 0.7,
        max_output_tokens: int = 4096
    ) -> Generator[str, None, None]:
        """
        Generates streaming content. Essential for real-time thought trace streaming.
        """
        model = self.models["pro"] if use_pro else self.models["flash"]
        logger.debug(f"Generating streaming content using {model}")
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction
        )
        
        try:
            response_stream = self.client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config
            )
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Error during generate_stream with {model}: {e}")
            raise e

    def get_embeddings(self, text: Union[str, List[str]]) -> List[List[float]]:
        """
        Generates text embeddings using text-embedding-004.
        Crucial for the Memory System (ChromaDB) to replace local CPU embeddings.
        """
        model = self.models["embedding"]
        logger.debug(f"Generating embeddings using {model}")
        
        try:
            if isinstance(text, str):
                text = [text]
                
            response = self.client.models.embed_content(
                model=model,
                contents=text
            )
            # Standard GenAI SDK returns embeddings containing list of values
            return [emb.values for emb in response.embeddings]
        except Exception as e:
            logger.error(f"Error generating embeddings with {model}: {e}")
            raise e

    def count_tokens(self, contents: Union[str, List[Any]], use_pro: bool = True) -> int:
        """
        Counts input tokens. Critical for TokenBudget enforcement to prevent cost overrun.
        """
        model = self.models["pro"] if use_pro else self.models["flash"]
        
        try:
            response = self.client.models.count_tokens(
                model=model,
                contents=contents
            )
            return response.total_tokens
        except Exception as e:
            logger.error(f"Error counting tokens with {model}: {e}")
            return 0
