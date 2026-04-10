import sys
import os
import logging
from typing import List, Dict, Any, Union
from typing import Optional
from google import genai
from google.genai import types
from pathlib import Path
import time
import datetime

# Add project root to path to import tool.gemini_interface
# sys.path.append(r"E:\Project\paperreader\code2")

# from tool.gemini_interface import Gemini_interface

logger = logging.getLogger(__name__)


class Gemini_interface:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = "gemini-3-flash-preview"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("API key must be provided or set in GEMINI_API_KEY environment variable.")
        self.client = genai.Client(api_key=self.api_key, http_options={"api_version": "v1beta"})
        # Fixed model names: gemini-3-pro-preview, gemini-3-flash-preview
        self.model_name = model_name 

    def _create_pdf_cache(self, file_path: str, ttl: str = "600s", system_instruction: Optional[str] = None) -> Any:
        """Creates a cache entry for a PDF file with a specified TTL."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are supported for caching.")

        target_display_name = path.name
        
        file_list = self.client.files.list()
        for file in file_list:
            if file.display_name == target_display_name:
                uploaded_file = file
                break
        else:
            uploaded_file = self.client.files.upload(file=path, config={"mime_type": "application/pdf", "display_name": target_display_name})
            
        cache = self.client.caches.create(
            model=self.model_name,
            config=types.CreateCachedContentConfig(
                system_instruction=system_instruction,
                contents=[uploaded_file],
                display_name=target_display_name,
                ttl=ttl,
            )
        )
        return cache

    def _calculate_cost(self, usage_metadata: Any, model_name: str, is_cache_creation: bool = False) -> float:
        """
        Calculates cost based on token usage and model pricing.
        Includes Context Caching pricing.
        
        - Cached Input (Cache Hit) = Sum of 'IMAGE' tokens in `prompt_tokens_details`.
        - Non-Cached Input (Query) = Sum of 'TEXT' tokens in `prompt_tokens_details`.
        - Storage Cost = Ignored.
        
        Args:
            usage_metadata: The usage metadata from the response.
            model_name: The model name.
            is_cache_creation: If True, treats the cached tokens (IMAGE) as Standard Input (creation cost),
                               and ignores the Cache Hit cost for this turn.
        """
        if not usage_metadata:
            return 0.0
            
        cached_count = 0
        non_cached_prompt_count = 0
        
        # Parse prompt_tokens_details to distinguish Cache (IMAGE) vs Query (TEXT)
        if hasattr(usage_metadata, 'prompt_tokens_details'):
            for detail in usage_metadata.prompt_tokens_details:
                if detail.modality == 'IMAGE':
                    # User instruction: IMAGE tokens represent the cached content
                    cached_count += detail.token_count
                elif detail.modality == 'TEXT':
                    # TEXT tokens represent the user query/input
                    non_cached_prompt_count += detail.token_count
        else:
            # Fallback if details are missing
            print("Warning: prompt_tokens_details missing in usage_metadata. Assuming all tokens are non-cached TEXT.")
            non_cached_prompt_count = usage_metadata.prompt_token_count if usage_metadata else 0
 
        output_count = usage_metadata.candidates_token_count 
        
        cost = 0.0
        
        # Pricing Logic
        if "gemini-3-pro-preview" in model_name:
            # Pro Pricing
            
            # 1. Non-Cached Input (TEXT) -> Always Standard Price
            if non_cached_prompt_count <= 200000:
                cost += (non_cached_prompt_count / 1_000_000) * 2.00
            else:
                cost += (non_cached_prompt_count / 1_000_000) * 4.00
            
            # 2. Cached Input (IMAGE from Prompt Details)
            if cached_count > 0:
                if is_cache_creation:
                    # Treat as Standard Input (Creation Cost)
                    if cached_count <= 200000:
                        cost += (cached_count / 1_000_000) * 2.00
                    else:
                        cost += (cached_count / 1_000_000) * 4.00
                else:
                    # Treat as Cache Hit
                    if cached_count <= 200000:
                        cost += (cached_count / 1_000_000) * 0.20
                    else:
                        cost += (cached_count / 1_000_000) * 0.40
                    
                # 3. Storage Cost -> Ignored

            # 4. Output
            if output_count is not None:
                if output_count <= 200000:
                    cost += (output_count / 1_000_000) * 12.00
                else:
                    cost += (output_count / 1_000_000) * 18.00
                
        elif "gemini-3-flash-preview" in model_name:
            # Flash Pricing
            
            # 1. Cached Input (IMAGE from Prompt Details)
            if cached_count > 0:
                if is_cache_creation:
                    # Treat as Standard Input (Creation Cost)
                    # Note: Flash Standard Input is $0.50
                    cost += (cached_count / 1_000_000) * 0.50
                else:
                    # Treat as Cache Hit
                    cost += (cached_count / 1_000_000) * 0.05
                
                # 2. Storage Cost -> Ignored
            
            # 3. Non-Cached Input (TEXT only) -> Standard Price
            cost += (non_cached_prompt_count / 1_000_000) * 0.50
            
            # 4. Output
            if output_count is not None:
                cost += (output_count / 1_000_000) * 3.00
            
        return cost

    def chat(self, pdf: Union[str, List[str], None], text: str, max_tokens: int = 4096, history: Dict = None) -> tuple[str, Dict, float, float]:
        """
        Interacts with the Gemini model, managing PDF caching and chat history.
        
        Args:
            pdf: Path to a PDF file to cache and use as context. 
                 Only allowed if no cache exists in history.
            text: The user's message.
            max_tokens: Maximum output tokens.
            history: Chat history (dict with 'cache' and 'turns' keys, or empty list).

        Returns:
            Tuple of (response_text, updated_history, cost, time_cost).
        """
        # 0. Normalize History Structure
        t0 = time.time()
        if not history:
            history = {"cache": None, "turns": []}
        
        # Ensure active_cache attribute exists/refreshed
        try:
            active_cache_list = list(self.client.caches.list()) # Convert generator to list
        except Exception as e:
            logger.warning(f"Failed to list caches: {e}")
            active_cache_list = []

        active_cache_displayname_list = [cache.display_name for cache in active_cache_list]
        active_cache_name_list = [cache.name for cache in active_cache_list]
        
        # Flag to track if we created a cache in this turn
        cache_created_this_turn = False
        
        # 1. Handle PDF and Cache Strategy
        cache_item = history.get("cache")
        
        # New PDF provided
        if pdf and not (cache_item and cache_item.get('display_name')):
            pdf_path_obj = Path(pdf)
            pdf_name = pdf_path_obj.name
            
            # Check if we need to create a new cache or use existing one
            # Try to find existing cache first
            found_cache = None
            for cache in active_cache_list:
                if cache.display_name == pdf_name:
                    found_cache = cache
                    print(f"Using existing cache for: {pdf_name}")
                    break
            
            if found_cache:
                cache_item = {
                    "cache_name": found_cache.name,
                    "display_name": found_cache.display_name
                }
            else:
                # Create new cache
                print(f"Caching PDF: {pdf}")
                new_cache = self._create_pdf_cache(str(pdf_path_obj.absolute()))
                cache_created_this_turn = True # Mark as created
                cache_item = {
                    "cache_name": new_cache.name,
                    "display_name": new_cache.display_name
                }
                # Update local lists
                active_cache_name_list.append(new_cache.name)
            
            # Update history with the selected cache
            history["cache"] = cache_item
            
        # 2. Validate and Reload History Caches (if no new PDF provided, check existing history cache)
        elif cache_item:
            his_name = cache_item.get('cache_name')
            his_display_name = cache_item.get('display_name')
            
            # Check if cache is active
            if his_name and his_name not in active_cache_name_list:
                # Cache expired or missing
                print(f"Cache {his_name} ({his_display_name}) expired or missing.")
                
                # Try to find the file to reload
                pdf_to_reload = None
                
                # 1. Try provided pdf path (Primary Source)
                if pdf and os.path.exists(pdf):
                    pdf_to_reload = pdf
                
                # 2. Try default location (Fallback - Removed as it relies on legacy config)
                # In new architecture, we rely on the caller providing the correct pdf path
                
                if pdf_to_reload:
                    print(f"Reloading expired cache from: {pdf_to_reload}")
                    try:
                        new_cache = self._create_pdf_cache(pdf_to_reload)
                        cache_created_this_turn = True # Mark as created (reloaded)
                        cache_item['cache_name'] = new_cache.name
                        cache_item['display_name'] = new_cache.display_name # Update in case it changed
                        # Update the set of active caches (local var only)
                        active_cache_name_list.append(new_cache.name)
                        history["cache"] = cache_item # Ensure history is updated
                    except Exception as e:
                        print(f"Failed to reload cache for {his_display_name}: {e}")
                        # If reload failed, we must clear the cache from history to avoid 403
                        history["cache"] = None
                        cache_item = None
                else:
                    error_msg = f"Cache expired and source file '{his_display_name}' not found. Cannot reload context."
                    print(f"Error: {error_msg}")
                    # Raise error to be shown in UI instead of silent fail
                    raise ValueError(error_msg)

        # 3. Prepare Chat Contents (Flatten turns to API format)
        chat_contents = []
        if history.get("turns"):
            for turn in history["turns"]:
                # Process user part
                user_item = turn.get("user")
                if user_item:
                    # Filter keys to only those accepted by API
                    content_item = {k: v for k, v in user_item.items() if k in ['role', 'parts']}
                    # Convert parts to compatible format
                    new_parts = []
                    for part in content_item.get('parts', []):
                        if isinstance(part, str):
                            new_parts.append({'text': part})
                        else:
                            new_parts.append(part)
                    content_item['parts'] = new_parts
                    chat_contents.append(content_item)

                # Process model part
                model_item = turn.get("model")
                if model_item:
                    # Filter keys to only those accepted by API
                    content_item = {k: v for k, v in model_item.items() if k in ['role', 'parts']}
                    # Convert parts to compatible format
                    new_parts = []
                    for part in content_item.get('parts', []):
                        if isinstance(part, str):
                            new_parts.append({'text': part})
                        else:
                            new_parts.append(part)
                    content_item['parts'] = new_parts
                    chat_contents.append(content_item)
            
        user_msg_api = {'role': 'user', 'parts': [{'text': text}]}
        chat_contents.append(user_msg_api)
        
        # 4. Generate Content
        config_params = {}
        if cache_item and cache_item.get('cache_name'):
            config_params['cached_content'] = cache_item['cache_name']
            
        # Add max_tokens
        # config_params['response_mime_type'] = 'text/plain' # Default
        
        # Create generation config
        gen_config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            **config_params
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=chat_contents,
            config=gen_config
        )
        
        # 5. Process Response and Update History
        response_text = response.text
        
        cost = self._calculate_cost(response.usage_metadata, self.model_name, is_cache_creation=cache_created_this_turn)
        time_cost = time.time() - t0
        
        # Construct Turn Data
        user_msg = {'role': 'user', 'parts': [{'text': text}]}
        model_msg = {'role': 'model', 'parts': [{'text': response_text}]}
        
        turn_meta = {
            "timestamp": datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
            "cost": cost,
            "time_cost": time_cost,
            "model_name": self.model_name
        }
        
        new_turn = {
            "user": user_msg,
            "model": model_msg,
            "meta": turn_meta
        }
        
        # Append new turn to history
        history["turns"].append(new_turn)
        
        # Ensure cache state is preserved
        history["cache"] = cache_item
        
        return response_text, history, cost, time_cost



def _convert_frontend_history_to_interface(history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Convert frontend flat history list to Gemini_interface nested history dict.
    Frontend: [{'role': 'user', 'content': 'A'}, {'role': 'assistant', 'content': 'B'}, ...]
    Interface: {'turns': [{'user': {'role': 'user', 'parts': [{'text': 'A'}]}, 'model': {'role': 'model', 'parts': [{'text': 'B'}]}}, ...]}
    """
    interface_history = {"cache": None, "turns": []}
    
    current_turn = {}
    
    for msg in history:
        role = msg.get("role")
        content = msg.get("content")
        
        if role == "user":
            # If we already have a user message in current_turn, it means the previous turn was incomplete or user sent multiple messages.
            # Gemini expects strictly User -> Model.
            # We'll reset current_turn if it has a user message already.
            if "user" in current_turn:
                # Skip incomplete turn or handle it? For now, let's just start new.
                current_turn = {}
                
            current_turn["user"] = {"role": "user", "parts": [{"text": content}]}
            
        elif role == "assistant" or role == "model":
            if "user" in current_turn:
                current_turn["model"] = {"role": "model", "parts": [{"text": content}]}
                interface_history["turns"].append(current_turn)
                current_turn = {}
            else:
                # Model message without preceding user message? Skip.
                pass
                
    # Handle trailing user message (incomplete turn)
    if "user" in current_turn:
        interface_history["turns"].append(current_turn)
        
    return interface_history

def chat_with_paper(pdf_path: str, history: Union[List[Dict], Dict], message: str, model_name: str = "gemini-3-flash-preview") -> tuple[str, Dict, float, float]:
    """
    Chat with paper using Gemini.
    Unified function for both interactive chat and automated interpretation.
    
    Args:
        pdf_path: Path to PDF file.
        history: Chat history. Can be:
                 - List[Dict]: Frontend format [{'role': 'user', ...}, ...]
                 - Dict: Interface format {'turns': [...], 'cache': ...}
        message: User message.
        model_name: Gemini model name.
        
    Returns:
        (response_text, updated_history_dict, cost, time_cost)
    """
    gemini = Gemini_interface(model_name=model_name)
    
    # Handle history format
    if isinstance(history, list):
        interface_history = _convert_frontend_history_to_interface(history)
    else:
        interface_history = history if history else {"cache": None, "turns": []}
    
    # We pass pdf_path every time. 
    # Gemini_interface.chat will check if a cache exists for this file (by name) and reuse it,
    # or create a new one if missing.
    response_text, updated_history, cost, time_cost = gemini.chat(
        pdf=pdf_path,
        text=message,
        history=interface_history
    )
    
    return response_text, updated_history, cost, time_cost

def interpret_paper(pdf_path: str, template_prompts: List[str], model_name: str = "gemini-3-flash-preview") -> tuple[str, List[Dict]]:
    """
    Interpret paper using Gemini with the given list of prompts (multi-turn).
    Now defined as automated calls to chat_with_paper.
    Returns (full_response_text, history_turns)
    """
    full_response = ""
    # Initialize empty history (interface format)
    history = {"cache": None, "turns": []}
    
    for i, prompt_text in enumerate(template_prompts):
        logger.info(f"Processing turn {i+1}/{len(template_prompts)}...")
        
        response_text, updated_history, cost, time_cost = chat_with_paper(
            pdf_path=pdf_path,
            history=history,
            message=prompt_text,
            model_name=model_name
        )
        
        # Accumulate response with formatting
        full_response += f"## Step {i+1}\n\n**Prompt:** {prompt_text}\n\n**Response:**\n{response_text}\n\n---\n\n"
        
        # Update history for next turn
        history = updated_history
        
    return full_response, history["turns"]
