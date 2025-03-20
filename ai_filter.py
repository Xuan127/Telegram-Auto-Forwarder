"""
AI filtering functionality for the Telegram Auto Forwarder.
Uses OpenRouter API to determine if messages are of interest.
"""
import os
import requests
from typing import Optional

from logger import logger
import config

class AIFilter:
    """Handles AI-based filtering of messages."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the AI filter.
        
        Args:
            api_key: OpenRouter API key. If None, uses the one from config.
        """
        self.api_key = api_key or config.OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OpenRouter API key not provided and not found in config")
        
        # AI model configuration
        self.model = "google/gemini-2.0-flash-thinking-exp:free"
        
        # Prompt template for filtering
        self.prompt_template = """You are given some content to evaluate, you need to decide if it is of interest to me.
        Answer with ONLY the word 'True' or the word 'False', nothing else.

        RULES:
        1. If the content is about a event that is only physically in Singapore, return False
        2. If it is a virtual event, then override the previous rule and return True
        3. If it is a event selling tickets, return False
        4. If it is volunteering related, return False
        5. If it is related to NUS orientations, return False
        6. Everything else, return True
        7. If you are unsure of anything, just answer True and I will take a look.

        CONTEXT:
        - NTU and NUS are universities in Singapore
        
        Content: {content}"""
    
    def is_content_interesting(self, content: str) -> bool:
        """
        Determine if the content is interesting based on AI evaluation.
        
        Args:
            content: The content to evaluate
            
        Returns:
            bool: True if the content is interesting, False otherwise
            
        Raises:
            ValueError: If the response can't be interpreted as True/False
        """
        if not content.strip():
            logger.debug("Empty content, defaulting to True")
            return True
            
        # API endpoint and headers
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Format the prompt with the content
        user_message = self.prompt_template.format(content=content)
        
        # Request data
        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": user_message}
            ]
        }
        
        try:
            # Make API request
            logger.debug(f"Sending request to OpenRouter for content: {content[:50]}...")
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            # Process response
            result = response.json()
            response_text = result["choices"][0]["message"]["content"].strip().lower()
            logger.info(f"Response from OpenRouter: {response_text}")
            
            # Return boolean result
            if response_text == "true":
                return True
            elif response_text == "false":
                return False
            else:
                # Attempt to extract true/false if model didn't follow instructions exactly
                if "true" in response_text and "false" not in response_text:
                    logger.warning(f"Ambiguous response, interpreting as True: {response_text}")
                    return True
                elif "false" in response_text and "true" not in response_text:
                    logger.warning(f"Ambiguous response, interpreting as False: {response_text}")
                    return False
                else:
                    raise ValueError(f"Could not determine True/False from response: {response_text}")
        except requests.RequestException as e:
            logger.error(f"API request error: {e}")
            # Default to True in case of API errors to avoid missing potentially important messages
            return True
        except Exception as e:
            logger.error(f"Error in AI filtering: {e}")
            # Default to True in case of errors
            return True
