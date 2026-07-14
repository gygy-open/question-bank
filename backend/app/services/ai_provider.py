from abc import ABC, abstractmethod
from typing import List, Dict, Optional, AsyncGenerator, Any, Union
import json
import logging
import asyncio
from pydantic import BaseModel
from app.schemas.ai import AIQuestion, QuestionList

logger = logging.getLogger(__name__)

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str
    metadata: Optional[Dict[str, Any]] = None

class BatchRerankItem(BaseModel):
    id: str
    points: List[str]

class AIProvider(ABC):
    @abstractmethod
    async def chat_stream(
        self, 
        messages: List[Dict[str, Any]], 
        config: Dict[str, str],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Union[str, ToolCall], None]:
        """
        Stream chat response.
        
        Args:
            messages: List of message dicts (role, content, images)
            config: Provider configuration
            tools: Optional list of tool definitions
            
        Yields:
            Chunks of response text or ToolCall objects
        """
        pass

    @abstractmethod
    async def extract_questions(self, content: str, image_data: bytes = None, config: Dict[str, str] = None) -> List[AIQuestion]:
        """
        Extract questions from text content or image.
        
        Args:
            content: Text content to process
            image_data: Optional image bytes
            config: Dictionary containing provider-specific configuration (API keys, models, etc.)
            
        Returns:
            List of AIQuestion objects
        """
        pass

    @abstractmethod
    async def get_embeddings(self, texts: List[str], config: Dict[str, str] = None) -> List[List[float]]:
        """
        Get embeddings for a list of texts.
        
        Args:
            texts: List of strings to embed
            config: Provider configuration
            
        Returns:
            List of embedding vectors (list of floats)
        """
        pass

    async def rerank_knowledge_points(self, question_content: str, candidates: List[str], config: Dict[str, str] = None) -> List[str]:
        """
        Rerank or filter knowledge points based on relevance to the question.
        Default implementation returns candidates as is.
        """
        return candidates

    async def batch_rerank_knowledge_points(self, items: List[Dict[str, Any]], config: Dict[str, str] = None) -> Dict[str, List[str]]:
        """
        Batch rerank knowledge points for multiple questions.
        
        Args:
            items: List of dicts, each containing 'id' (str/int), 'content', and 'candidates'.
            config: Provider configuration.
            
        Returns:
            Dict mapping id (as string) to list of verified knowledge points.
        """
        results = {}
        for item in items:
            verified = await self.rerank_knowledge_points(item['content'], item['candidates'], config)
            results[str(item['id'])] = verified
        return results

class GeminiProvider(AIProvider):
    async def chat_stream(
        self, 
        messages: List[Dict[str, Any]], 
        config: Dict[str, str],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Union[str, ToolCall], None]:
        try:
            from google import genai
            from google.genai import types
            import base64
        except ImportError:
            yield "Error: google-genai package not installed"
            return

        config = config or {}
        api_key = config.get("API_KEY")
        if not api_key:
            yield "Error: API_KEY not configured for Gemini"
            return

        # Note: google-genai client is synchronous. For high concurrency, this should be run in a thread pool.
        # For now, we run it directly which might block the event loop briefly.
        client_kwargs = {"api_key": api_key}
        base_url = config.get("BASE_URL")
        if base_url:
            client_kwargs["http_options"] = {"base_url": base_url}

        client = genai.Client(**client_kwargs)
        model_name = config.get("MODEL_NAME", "gemini-2.0-flash-exp")

        # Convert OpenAI tools format to Gemini format
        gemini_tools = None
        if tools:
            function_declarations = []
            for tool in tools:
                if tool.get("type") == "function":
                    func = tool.get("function", {})
                    function_declarations.append(types.FunctionDeclaration(
                        name=func.get("name"),
                        description=func.get("description"),
                        parameters=func.get("parameters")
                    ))
            if function_declarations:
                gemini_tools = [types.Tool(function_declarations=function_declarations)]

        gemini_contents = []
        system_instruction = None
        
        # Helper to find function name by tool_call_id from previous messages
        # This is needed because Gemini requires function name in the response, but OpenAI tool messages only have ID
        tool_id_name_map = {}

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            
            if role == "system":
                system_instruction = content
            elif role == "user":
                parts = [types.Part.from_text(text=content)]
                images = msg.get("images")
                if images:
                    for img_b64 in images:
                        try:
                            # Remove header if present (e.g. "data:image/png;base64,")
                            if "," in img_b64:
                                header, data = img_b64.split(",", 1)
                                mime_type = header.split(":")[1].split(";")[0]
                            else:
                                data = img_b64
                                mime_type = "image/png" # Default fallback
                            
                            img_bytes = base64.b64decode(data)
                            parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))
                        except Exception as e:
                            logger.error(f"Error processing image for Gemini: {e}")
                            
                gemini_contents.append(types.Content(role="user", parts=parts))
            elif role == "assistant":
                parts = []
                if content:
                    parts.append(types.Part.from_text(text=content))
                
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        if "function" in tc:
                            func_name = tc["function"]["name"]
                            func_args = json.loads(tc["function"]["arguments"])
                        else:
                            # Handle flat ToolCall format
                            func_name = tc.get("name")
                            func_args = json.loads(tc.get("arguments", "{}"))
                            
                        tool_id_name_map[tc["id"]] = func_name
                        
                        # Try to reconstruct with metadata
                        metadata = tc.get("metadata") or {}
                        # We construct the FunctionCall object manually to include potential metadata
                        # Note: The SDK might not expose thought_signature in constructor, but we try.
                        # If not, we fallback to standard from_function_call
                        try:
                            # Attempt to use internal structure if needed or just pass args if supported
                            # Since we don't know if types.FunctionCall supports thought_signature in init,
                            # we will try to set it after creation if possible, or pass it.
                            # However, google-genai types are usually Pydantic-like or dataclasses.
                            
                            # Let's try to create a FunctionCall and see if we can inject it.
                            # But safer is to just use what we have.
                            # If the error persists, it means we MUST provide it.
                            
                            # Assuming types.FunctionCall has these fields.
                            fc = types.FunctionCall(name=func_name, args=func_args)
                            if "id" in metadata:
                                fc.id = metadata["id"]
                            
                            part_kwargs = {"function_call": fc}
                            if "thought_signature" in metadata:
                                ts = metadata["thought_signature"]
                                if metadata.get("thought_signature_is_base64"):
                                    import base64
                                    ts = base64.b64decode(ts)
                                part_kwargs["thought_signature"] = ts
                                
                            parts.append(types.Part(**part_kwargs))
                        except Exception as e:
                            logger.warning(f"Error constructing Gemini part: {e}")
                            # Fallback
                            parts.append(types.Part.from_function_call(name=func_name, args=func_args))
                
                gemini_contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                # Map OpenAI tool response to Gemini function response
                tool_call_id = msg.get("tool_call_id")
                func_name = tool_id_name_map.get(tool_call_id)
                
                if func_name:
                    # Gemini expects the response as a dict/json
                    try:
                        response_content = json.loads(content)
                    except:
                        response_content = {"result": content}
                        
                    gemini_contents.append(types.Content(
                        role="user", 
                        parts=[types.Part.from_function_response(name=func_name, response=response_content)]
                    ))

        try:
            # Run synchronous Gemini stream in a thread to avoid blocking event loop
            def create_stream():
                return client.models.generate_content_stream(
                    model=model_name,
                    contents=gemini_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=gemini_tools
                    ) if system_instruction or gemini_tools else None
                )

            response = await asyncio.to_thread(create_stream)
            
            # Iterate through the stream in a thread
            iterator = iter(response)
            while True:
                def get_next_chunk():
                    try:
                        return next(iterator)
                    except StopIteration:
                        return None

                chunk = await asyncio.to_thread(get_next_chunk)
                if chunk is None:
                    break
                
                # Handle function calls
                # In streaming, function calls might appear in candidates
                if chunk.candidates and chunk.candidates[0].content.parts:
                    for part in chunk.candidates[0].content.parts:
                        if part.function_call:
                            # Gemini function call to standard ToolCall
                            metadata = {}
                            # Try to capture id and thought_signature
                            if hasattr(part.function_call, 'id'):
                                metadata['id'] = part.function_call.id
                            
                            # thought_signature is on the Part object, not FunctionCall
                            if hasattr(part, 'thought_signature') and part.thought_signature:
                                ts = part.thought_signature
                                if isinstance(ts, bytes):
                                    import base64
                                    metadata['thought_signature'] = base64.b64encode(ts).decode('utf-8')
                                    metadata['thought_signature_is_base64'] = True
                                else:
                                    metadata['thought_signature'] = ts
                            
                            yield ToolCall(
                                id=getattr(part.function_call, 'id', None) or "gemini_call", 
                                name=part.function_call.name,
                                arguments=json.dumps(part.function_call.args),
                                metadata=metadata
                            )
                        if part.text:
                            yield part.text
        except Exception as e:
            logger.error(f"Gemini chat error: {e}")
            yield f"Error: {str(e)}"

    async def extract_questions(self, content: str, image_data: bytes = None, config: Dict[str, str] = None) -> List[AIQuestion]:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            logger.error("google-genai package not installed")
            return []

        config = config or {}
        api_key = config.get("API_KEY")
        if not api_key:
            logger.warning("API_KEY not configured for Gemini")
            return []

        client_kwargs = {"api_key": api_key}
        base_url = config.get("BASE_URL")
        if base_url:
            client_kwargs["http_options"] = {"base_url": base_url}

        client = genai.Client(**client_kwargs)
        
        default_prompt = """请从以下内容中提取题目。
对于每个题目，请在 'knowledge_points' 字段中提取 3-5 个核心知识点。
请在 'thinking' 字段中提供对题目的分析思路。
注意：
1. 知识点应使用标准的学科术语（例如："勾股定理"、"二次函数性质"）。
2. 包含题目涉及的所有关键概念、公式或解题方法。如果题目综合性强，请确保覆盖各个维度。
3. 避免使用口语化描述或过长的句子。
4. 这些知识点将用于在数据库中检索相似的标准知识点，因此准确性至关重要。

内容：

{content}"""
        prompt_template = config.get("AI_EXTRACT_PROMPT", default_prompt)
        
        if image_data:
            model_name = config.get("MODEL_NAME", "gemini-2.0-flash-exp") # Updated default or keep existing
            prompt_text = prompt_template.replace("{content}", "")
            contents = [
                prompt_text,
                types.Part.from_bytes(data=image_data, mime_type="image/png")
            ]
        else:
            model_name = config.get("MODEL_NAME", "gemini-2.0-flash-exp")
            prompt = prompt_template.replace("{content}", content)
            contents = prompt

        try:
            def generate_content():
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=list[AIQuestion]
                    )
                )

            response = await asyncio.to_thread(generate_content)
            
            if response.text:
                logger.debug(f"Gemini response: {response.text}")
                cleaned_text = self._clean_json_response(response.text)
                try:
                    return [AIQuestion(**q) for q in json.loads(cleaned_text)]
                except json.JSONDecodeError as e:
                    logger.error(f"JSON Decode Error: {e}. Text: {cleaned_text}")
                    # Try to repair common JSON errors if needed, or just fail gracefully
                    raise e
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise e
        return []

    def _clean_json_response(self, text: str) -> str:
        text = text.strip()
        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    async def rerank_knowledge_points(self, question_content: str, candidates: List[str], config: Dict[str, str] = None) -> List[str]:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            logger.error("google-genai package not installed")
            return candidates

        config = config or {}
        api_key = config.get("API_KEY")
        if not api_key:
            return candidates

        client_kwargs = {"api_key": api_key}
        base_url = config.get("BASE_URL")
        if base_url:
            client_kwargs["http_options"] = {"base_url": base_url}

        client = genai.Client(**client_kwargs)
        model_name = config.get("MODEL_NAME", "gemini-2.0-flash-exp")

        prompt = f"""
请判断以下候选知识点中，哪些与给定的题目真正相关。
题目内容：
{question_content[:500]}... (截断)

候选知识点：
{json.dumps(candidates, ensure_ascii=False, indent=2)}

请返回一个 JSON 列表，仅包含你认为最相关的知识点字符串。如果都不相关，返回空列表。
"""
        try:
            def generate_content():
                return client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=list[str]
                    )
                )

            response = await asyncio.to_thread(generate_content)
            
            if response.text:
                return json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini Rerank error: {e}")
            return candidates
        return candidates

    async def batch_rerank_knowledge_points(self, items: List[Dict[str, Any]], config: Dict[str, str] = None) -> Dict[str, List[str]]:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            logger.error("google-genai package not installed")
            return {}

        config = config or {}
        api_key = config.get("API_KEY")
        if not api_key:
            return {}

        client_kwargs = {"api_key": api_key}
        base_url = config.get("BASE_URL")
        if base_url:
            client_kwargs["http_options"] = {"base_url": base_url}

        client = genai.Client(**client_kwargs)
        model_name = config.get("MODEL_NAME", "gemini-2.0-flash-exp")

        prompt = "请批量判断以下题目与候选知识点的相关性。\n\n"
        for item in items:
            prompt += f"题目ID: {item['id']}\n"
            prompt += f"题目内容: {item['content'][:200]}...\n"
            prompt += f"候选知识点: {json.dumps(item['candidates'], ensure_ascii=False)}\n\n"
            
        prompt += """
请返回一个 JSON 列表，每个元素包含 "id" 和 "points" 字段。
注意：
如果候选知识点中存在层级关系（例如 "A > B" 和 "A > B > C"），请优先选择更具体的子级知识点（"A > B > C"），并排除父级知识点，除非题目内容仅涉及父级概念。
"""
        try:
            def generate_content():
                return client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=list[BatchRerankItem]
                    )
                )

            response = await asyncio.to_thread(generate_content)
            
            if response.text:
                items = json.loads(response.text)
                # Convert list of dicts to dict map
                return {item['id']: item['points'] for item in items}
        except Exception as e:
            logger.error(f"Gemini Batch Rerank error: {e}")
            return {}
        return {}

    async def get_embeddings(self, texts: List[str], config: Dict[str, str] = None) -> List[List[float]]:
        try:
            from google import genai
        except ImportError:
            logger.error("google-genai package not installed")
            return []

        config = config or {}
        api_key = config.get("API_KEY")
        if not api_key:
            logger.warning("API_KEY not configured for Gemini")
            return []

        client_kwargs = {"api_key": api_key}
        base_url = config.get("BASE_URL")
        if base_url:
            client_kwargs["http_options"] = {"base_url": base_url}

        client = genai.Client(**client_kwargs)
        # Default to text-embedding-004 or similar if not specified
        model_name = config.get("EMBEDDING_MODEL_NAME", "text-embedding-004")

        try:
            # Gemini batch embedding might need loop or specific batch call
            # google-genai SDK supports batch_embed_contents?
            # Let's check docs or assume loop for safety if unsure, but batch is better.
            # client.models.embed_content is for single?
            # client.models.batch_embed_contents exists in some versions.
            # Let's try to use a loop for now to be safe, or check if we can find usage.
            # Actually, let's use asyncio.gather for concurrency.
            
            async def embed_one(text):
                def _call():
                    return client.models.embed_content(
                        model=model_name,
                        contents=text
                    )
                resp = await asyncio.to_thread(_call)
                return resp.embedding.values

            tasks = [embed_one(text) for text in texts]
            embeddings = await asyncio.gather(*tasks)
            return list(embeddings)

        except Exception as e:
            logger.error(f"Gemini embedding error: {e}")
            return []

class OpenAIProvider(AIProvider):
    async def chat_stream(
        self, 
        messages: List[Dict[str, Any]], 
        config: Dict[str, str],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Union[str, ToolCall], None]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            yield "Error: openai package not installed"
            return

        config = config or {}
        api_key = config.get("API_KEY")
        base_url = config.get("BASE_URL")
        
        if not api_key:
            yield "Error: API_KEY not configured for OpenAI"
            return

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        model_name = config.get("MODEL_NAME", "gpt-4o")

        # Prepare messages with image support
        openai_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            images = msg.get("images")
            
            if images and role == "user":
                content_parts = [{"type": "text", "text": content}]
                for img_b64 in images:
                    # Ensure header is present for OpenAI
                    if not img_b64.startswith("data:"):
                        # Assume png if no header, though ideally frontend sends full data URI
                        img_b64 = f"data:image/png;base64,{img_b64}"
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img_b64}
                    })
                openai_messages.append({"role": role, "content": content_parts})
            else:
                # Filter out internal fields like 'images' if they exist but weren't processed (e.g. for assistant)
                # OpenAI strict validation might complain about unknown fields
                clean_msg = {k: v for k, v in msg.items() if k in ["role", "content", "tool_calls", "tool_call_id", "name"]}
                
                # Ensure tool_calls are in the correct format for OpenAI
                if "tool_calls" in clean_msg and isinstance(clean_msg["tool_calls"], list):
                    formatted_tool_calls = []
                    for tc in clean_msg["tool_calls"]:
                        if isinstance(tc, dict) and "function" not in tc and "name" in tc:
                            # Convert flat ToolCall format to OpenAI format
                            formatted_tool_calls.append({
                                "id": tc.get("id", "call_unknown"),
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"]
                                }
                            })
                        else:
                            formatted_tool_calls.append(tc)
                    clean_msg["tool_calls"] = formatted_tool_calls

                openai_messages.append(clean_msg)

        try:
            stream = await client.chat.completions.create(
                model=model_name,
                messages=openai_messages,
                tools=tools if tools else None,
                stream=True
            )
            
            tool_calls_buffer = []
            
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                
                if delta and delta.content:
                    yield delta.content
                
                if delta and delta.tool_calls:
                    for tool_call_chunk in delta.tool_calls:
                        index = tool_call_chunk.index
                        if len(tool_calls_buffer) <= index:
                            tool_calls_buffer.append({
                                "id": "",
                                "name": "",
                                "arguments": ""
                            })
                        
                        if tool_call_chunk.id:
                            tool_calls_buffer[index]["id"] += tool_call_chunk.id
                        if tool_call_chunk.function and tool_call_chunk.function.name:
                            tool_calls_buffer[index]["name"] += tool_call_chunk.function.name
                        if tool_call_chunk.function and tool_call_chunk.function.arguments:
                            tool_calls_buffer[index]["arguments"] += tool_call_chunk.function.arguments
            
            # Yield accumulated tool calls
            for tc in tool_calls_buffer:
                yield ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc["arguments"]
                )
                    
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            yield f"Error: {str(e)}"

    async def extract_questions(self, content: str, image_data: bytes = None, config: Dict[str, str] = None) -> List[AIQuestion]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai package not installed")
            return []

        try:
            config = config or {}
            api_key = config.get("API_KEY")
            base_url = config.get("BASE_URL") # Optional, for compatible APIs
            
            if not api_key:
                logger.warning("API_KEY not configured for OpenAI")
                return []

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            
            model_name = config.get("MODEL_NAME", "gpt-4o")
            prompt_template = config.get("AI_EXTRACT_PROMPT", "请从以下内容中提取题目:\n\n{content}")

            messages = []
            
            # System prompt to enforce JSON output
            schema_json = json.dumps(QuestionList.model_json_schema(), ensure_ascii=False)
            system_prompt = f"""你是一个帮助从文本或图像中提取考试题目的助手。
请在 'thinking' 字段中提供对题目的分析思路。
在提取 'knowledge_points'（知识点）时，请遵循以下规则：
1. 提取 3-5 个核心知识点。如果题目涉及多个概念，请确保全部列出。
2. 使用标准的学科术语（例如：“勾股定理”、“二次函数性质”）。
3. 保持简洁具体。避免使用模糊的术语（如“数学”）或过长的句子。
4. 这些知识点将用于向量检索，因此准确性至关重要。

请严格输出符合以下模式的有效 JSON：
{schema_json}"""
            messages.append({"role": "system", "content": system_prompt})

            if image_data:
                logger.debug(f"Preparing OpenAI request with image ({len(image_data)} bytes)")
                import base64
                
                # Simple mime type detection
                mime_type = "image/png"
                if image_data.startswith(b'\xff\xd8'):
                    mime_type = "image/jpeg"
                elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
                    mime_type = "image/png"
                elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
                    mime_type = "image/gif"
                elif image_data.startswith(b'RIFF') and image_data[8:12] == b'WEBP':
                    mime_type = "image/webp"

                base64_image = base64.b64encode(image_data).decode('utf-8')
                
                # Improve prompt for image context
                if "{content}" in prompt_template:
                    prompt_text = prompt_template.replace("{content}", "这张图片")
                else:
                    prompt_text = prompt_template
                
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                })
            else:
                logger.debug("Preparing OpenAI request with text only")
                prompt = prompt_template.replace("{content}", content)
                messages.append({"role": "user", "content": prompt})

            # Use standard create method for better compatibility with non-OpenAI providers
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            logger.debug(f"OpenAI raw response content: {content}")
            if not content:
                logger.warning("OpenAI returned empty content")
                return []
            
            try:
                return QuestionList.model_validate_json(content).questions
            except Exception as e:
                logger.warning(f"Failed to parse as QuestionList, trying raw list: {e}")
                # Fallback: try to parse as list directly if model returned list instead of object
                data = json.loads(content)
                if isinstance(data, list):
                    return [AIQuestion(**q) for q in data]
                raise e
            
        except Exception as e:
            logger.exception(f"OpenAI API error: {e}")
            return []

    async def rerank_knowledge_points(self, question_content: str, candidates: List[str], config: Dict[str, str] = None) -> List[str]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return candidates

        try:
            config = config or {}
            api_key = config.get("API_KEY")
            base_url = config.get("BASE_URL")
            
            if not api_key:
                return candidates

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            model_name = config.get("MODEL_NAME", "gpt-4o")

            prompt = f"""
请判断以下候选知识点中，哪些与给定的题目真正相关。
题目内容：
{question_content[:500]}... (截断)

候选知识点：
{json.dumps(candidates, ensure_ascii=False, indent=2)}

请返回一个 JSON 对象，格式为 {{"points": ["知识点1", "知识点2"]}}。仅包含你认为最相关的知识点字符串。如果都不相关，返回 {{"points": []}}。
"""
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            if not content:
                return []
                
            data = json.loads(content)
            if isinstance(data, dict):
                return data.get("points", [])
            if isinstance(data, list):
                return data
            
            return []
        except Exception as e:
            logger.error(f"Rerank error: {e}")
            return candidates

    async def batch_rerank_knowledge_points(self, items: List[Dict[str, Any]], config: Dict[str, str] = None) -> Dict[str, List[str]]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return {}

        try:
            config = config or {}
            api_key = config.get("API_KEY")
            base_url = config.get("BASE_URL")
            
            if not api_key:
                return {}

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            model_name = config.get("MODEL_NAME", "gpt-4o")

            prompt = "请批量判断以下题目与候选知识点的相关性。\n\n"
            for item in items:
                prompt += f"题目ID: {item['id']}\n"
                prompt += f"题目内容: {item['content'][:200]}...\n"
                prompt += f"候选知识点: {json.dumps(item['candidates'], ensure_ascii=False)}\n\n"

            prompt += """
请返回一个 JSON 对象，键为题目ID（字符串），值为该题目最相关的知识点列表。
注意：
如果候选知识点中存在层级关系（例如 "A > B" 和 "A > B > C"），请优先选择更具体的子级知识点（"A > B > C"），并排除父级知识点，除非题目内容仅涉及父级概念。

格式示例：
{
  "0": ["知识点A", "知识点B"],
  "1": []
}
"""
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            if not content:
                return {}
                
            data = json.loads(content)
            return data
        except Exception as e:
            logger.error(f"OpenAI Batch Rerank error: {e}")
            return {}

    async def get_embeddings(self, texts: List[str], config: Dict[str, str] = None) -> List[List[float]]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai package not installed")
            return []

        try:
            config = config or {}
            api_key = config.get("API_KEY")
            base_url = config.get("BASE_URL")
            
            if not api_key:
                logger.warning("API_KEY not configured for OpenAI")
                return []

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            model_name = config.get("EMBEDDING_MODEL_NAME", "text-embedding-3-small")

            # OpenAI supports batching natively
            # Replace newlines to avoid negative effects on some models
            clean_texts = [text.replace("\n", " ") for text in texts]
            
            response = await client.embeddings.create(
                input=clean_texts,
                model=model_name
            )
            
            return [data.embedding for data in response.data]
            
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            return []

def get_ai_provider(provider_name: str) -> AIProvider:
    if provider_name.lower() == "openai":
        return OpenAIProvider()
    return GeminiProvider()
